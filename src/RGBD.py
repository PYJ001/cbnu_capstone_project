from pathlib import Path
import threading

import cv2
import numpy as np
from ultralytics import YOLO

from .Calibration import CalibrationModel


class RGBD:
    def __init__(
        self,
        camera_backend="realsense",
        rgb_camera_index=1,
        depth_camera_index=0,
        robot_weight_path="runs/end_effector_yolo12n_416_safe/weights/best.pt",
        yolo_world_weight_path="yolov8s-worldv2.pt",
        yolo_world_classes=None,
        conf_thres=0.35,
        imgsz=640,
        device=0,
        calibration_csv_path=None,
        calibration_search_dir="robot_camera_calibration_samples",
        calibration_k=4,
        robot_depth_offset=0.05,
    ):
        self.camera_backend = camera_backend
        self.rgb_camera_index = rgb_camera_index
        self.depth_camera_index = depth_camera_index

        self.robot_weight_path = Path(robot_weight_path)
        self.yolo_world_weight_path = yolo_world_weight_path

        self.conf_thres = conf_thres
        self.world_conf_thres = min(conf_thres, 0.25)
        self.imgsz = imgsz
        self.device = device
        self.calibration_csv_path = calibration_csv_path
        self.calibration_search_dir = calibration_search_dir
        self.calibration_k = calibration_k
        self.robot_depth_offset = float(robot_depth_offset)
        self.calibration_prediction_enabled = True

        self.yolo_world_classes = []
        self.yolo_world_lock = threading.Lock()
        self.yolo_world_enabled = True

        print("[RGBD] loading robot YOLO...")
        self.robot_model = YOLO(str(self.robot_weight_path))

        print("[RGBD] loading YOLO-World...")
        self.world_model = YOLO(self.yolo_world_weight_path)

        self.set_yolo_world_classes(yolo_world_classes or [])

        self.calibration_model = self._load_calibration_model()

        self.pipeline  = None
        self.align     = None
        self.rgb_cap   = None
        self.depth_cap = None

        self._open_camera()

    def _open_camera(self):
        if self.camera_backend == "realsense":
            try:
                import pyrealsense2 as rs

                print("[RGBD] opening RealSense camera")

                self.rs = rs
                self.pipeline = rs.pipeline()
                config = rs.config()

                config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
                config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

                self.pipeline.start(config)
                self.align = rs.align(rs.stream.color)

                print("[RGBD] RealSense opened")
                return

            except Exception as e:
                print(f"[RGBD] RealSense open failed: {e}")
                print("[RGBD] fallback to OpenCV camera")

        self.camera_backend = "opencv"

        self.rgb_cap = cv2.VideoCapture(self.rgb_camera_index)
        self.depth_cap = cv2.VideoCapture(self.depth_camera_index)

        if not self.rgb_cap.isOpened():
            raise RuntimeError(f"RGB camera open failed: index={self.rgb_camera_index}")

        if not self.depth_cap.isOpened():
            print("[RGBD] depth camera open failed. Depth will be zeros.")
            self.depth_cap = None

        self.rgb_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.rgb_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.rgb_cap.set(cv2.CAP_PROP_FPS, 30)

        if self.depth_cap is not None:
            self.depth_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.depth_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.depth_cap.set(cv2.CAP_PROP_FPS, 30)

        print("[RGBD] OpenCV camera opened")

    def get_frame(self):
        frame, depth = self._read_rgbd()

        yolo_robot = self._yolo_robot_inference(frame, depth)
        yolo_world = self._yolo_world_inference(frame, depth)

        if self.calibration_prediction_enabled:
            for obj in yolo_world or []:
                angle = self._calibration(obj)

                if angle is not None:
                    obj["angle"] = angle

        if self.calibration_prediction_enabled and yolo_robot is not None:
            angle = self._calibration(yolo_robot)

            if angle is not None:
                yolo_robot["angle"] = angle

        return frame, depth, yolo_robot, yolo_world

    def _read_rgbd(self):
        if self.camera_backend == "realsense":
            return self._read_realsense()

        return self._read_opencv()

    def _read_realsense(self):
        frames = self.pipeline.wait_for_frames()
        aligned_frames = self.align.process(frames)

        color_frame = aligned_frames.get_color_frame()
        depth_frame = aligned_frames.get_depth_frame()

        if not color_frame or not depth_frame:
            raise RuntimeError("RealSense frame read failed")

        frame = np.asanyarray(color_frame.get_data())
        depth_raw = np.asanyarray(depth_frame.get_data())

        depth_scale = self.pipeline.get_active_profile().get_device().first_depth_sensor().get_depth_scale()
        depth_meter = depth_raw.astype(np.float32) * depth_scale

        return frame, depth_meter

    def _read_opencv(self):
        ret, frame = self.rgb_cap.read()

        if not ret:
            raise RuntimeError("RGB frame read failed")

        if self.depth_cap is None:
            depth = np.zeros(frame.shape[:2], dtype=np.float32)
            return frame, depth

        ret_d, depth_raw = self.depth_cap.read()

        if not ret_d:
            depth = np.zeros(frame.shape[:2], dtype=np.float32)
            return frame, depth

        if depth_raw.ndim == 3:
            depth_raw = cv2.cvtColor(depth_raw, cv2.COLOR_BGR2GRAY)

        depth = depth_raw.astype(np.float32)

        return frame, depth

    def _yolo_robot_inference(self, frame, depth):
        results = self.robot_model.predict(
            source=frame,
            conf=self.conf_thres,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )

        if len(results) == 0:
            return None

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            return None

        boxes = result.boxes

        best_idx = int(boxes.conf.argmax().item())

        xyxy = boxes.xyxy[best_idx].detach().cpu().numpy()
        conf = float(boxes.conf[best_idx].detach().cpu().item())

        x1, y1, x2, y2 = xyxy
        u = int((x1 + x2) / 2)
        v = int((y1 + y2) / 2)
        d = self._get_depth_at(depth, u, v)
        d = self._apply_robot_depth_offset(d)

        return {
            "name": "end_effector",
            "u": u,
            "v": v,
            "d": d,
            "conf": conf,
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
        }

    def _apply_robot_depth_offset(self, depth_value):
        if depth_value is None:
            return None

        return float(depth_value) + self.robot_depth_offset

    def _yolo_world_inference(self, frame, depth):
        with self.yolo_world_lock:
            if not self.yolo_world_enabled:
                return []

            classes = self.yolo_world_classes.copy()

            if len(classes) == 0:
                return []

            results = self.world_model.predict(
                source=frame,
                conf=self.world_conf_thres,
                imgsz=self.imgsz,
                device=self.device,
                verbose=False,
            )

        objs = []

        if len(results) == 0:
            return objs

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            return objs

        names = result.names

        for box in result.boxes:
            xyxy = box.xyxy[0].detach().cpu().numpy()
            conf = float(box.conf[0].detach().cpu().item())
            cls_id = int(box.cls[0].detach().cpu().item())

            raw_name = names.get(cls_id, str(cls_id))
            name = self._canonical_world_name(raw_name)

            x1, y1, x2, y2 = xyxy
            u = int((x1 + x2) / 2)
            v = int((y1 + y2) / 2)
            d = self._get_depth_at(depth, u, v)

            objs.append(
                {
                    "name": name,
                    "u": u,
                    "v": v,
                    "d": d,
                    "conf": conf,
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                }
            )

        return objs

    def set_yolo_world_classes(self, classes):
        clean_classes = self._clean_yolo_world_classes(classes)

        with self.yolo_world_lock:
            if clean_classes == self.yolo_world_classes:
                return

            try:
                self._set_world_model_classes(clean_classes)
                self.yolo_world_classes = clean_classes
                print(f"[RGBD] YOLO-World classes: {self.yolo_world_classes}")
            except Exception as e:
                print(f"[RGBD] set_classes failed: {e}")

    def set_yolo_world_enabled(self, enabled):
        with self.yolo_world_lock:
            self.yolo_world_enabled = bool(enabled)
            state = "enabled" if self.yolo_world_enabled else "disabled"
            print(f"[RGBD] YOLO-World {state}")

    def is_yolo_world_enabled(self):
        with self.yolo_world_lock:
            return self.yolo_world_enabled

    def set_calibration_prediction_enabled(self, enabled):
        self.calibration_prediction_enabled = bool(enabled)
        state = "enabled" if self.calibration_prediction_enabled else "disabled"
        print(f"[RGBD] calibration prediction {state}")

    def is_calibration_prediction_enabled(self):
        return self.calibration_prediction_enabled

    def get_yolo_world_classes(self):
        with self.yolo_world_lock:
            return self.yolo_world_classes.copy()

    def _clean_yolo_world_classes(self, classes):
        if classes is None:
            return []

        if isinstance(classes, str):
            classes = [classes]

        result = []
        seen = set()

        for item in classes:
            name = self._canonical_world_name(item)

            if name == "" or name in seen:
                continue

            for prompt_name in self._expand_world_class_prompt(name):
                if prompt_name in seen:
                    continue

                seen.add(prompt_name)
                result.append(prompt_name)

                if len(result) >= 10:
                    break

            if len(result) >= 10:
                break

        return result

    def _set_world_model_classes(self, classes):
        try:
            self.world_model.to("cpu")
        except Exception:
            try:
                self.world_model.model.cpu()
            except Exception:
                pass

        self.world_model.predictor = None
        self.world_model.set_classes(classes)

    def _canonical_world_name(self, name):
        name = str(name).strip().lower()

        if "hand" in name:
            return "hand"

        if "bottle" in name:
            return "bottle"

        if "cup" in name or "mug" in name:
            return "cup"

        if "box" in name:
            return "box"

        if "basket" in name or "container" in name or name == "bin":
            return "basket"

        return " ".join(name.split())

    def _expand_world_class_prompt(self, name):
        if name == "hand":
            return ["hand", "human hand", "person hand"]

        return [name]

    def _load_calibration_model(self):
        try:
            model = CalibrationModel.from_latest_or_path(
                csv_path=self.calibration_csv_path,
                search_dir=self.calibration_search_dir,
                k=self.calibration_k,
            )
            print(f"[RGBD] calibration loaded: {model.csv_path}")
            return model
        except Exception as e:
            print(f"[RGBD] calibration disabled: {e}")
            return None

    def _calibration(self, obj):
        if self.calibration_model is None:
            return None

        if not isinstance(obj, dict):
            return None

        u = obj.get("u")
        v = obj.get("v")
        d = obj.get("d")

        if u is None or v is None:
            return None

        try:
            return self.calibration_model.predict(u, v, d)
        except Exception as e:
            print(f"[RGBD] calibration predict failed: {e}")
            return None

    def _get_depth_at(self, depth, u, v, kernel=5):
        if depth is None:
            return None

        h, w = depth.shape[:2]

        u = int(np.clip(u, 0, w - 1))
        v = int(np.clip(v, 0, h - 1))

        x1 = max(0, u - kernel)
        x2 = min(w, u + kernel + 1)
        y1 = max(0, v - kernel)
        y2 = min(h, v + kernel + 1)

        patch = depth[y1:y2, x1:x2].astype(np.float32)

        valid = patch[np.isfinite(patch)]
        valid = valid[valid > 0]

        if len(valid) == 0:
            return None

        return float(np.median(valid))

    def close(self):
        if self.pipeline is not None:
            self.pipeline.stop()

        if self.rgb_cap is not None:
            self.rgb_cap.release()

        if self.depth_cap is not None:
            self.depth_cap.release()


# ===============================================================
# test code

def draw_detection(frame, obj, color, label_prefix=""):
    if obj is None:
        return frame

    x1, y1, x2, y2 = obj["bbox"]
    u = obj["u"]
    v = obj["v"]
    d = obj["d"]
    conf = obj["conf"]
    name = obj["name"]

    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.circle(frame, (u, v), 5, color, -1)

    if d is None:
        depth_text = "d=None"
    else:
        depth_text = f"d={d:.3f}"

    text = f"{label_prefix}{name} conf={conf:.2f} u={u} v={v} {depth_text}"

    cv2.putText(
        frame,
        text,
        (x1, max(20, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
        cv2.LINE_AA,
    )

    return frame


def make_depth_view(depth):
    if depth is None:
        return None

    depth_vis = depth.copy().astype(np.float32)

    valid = np.isfinite(depth_vis) & (depth_vis > 0)

    if not np.any(valid):
        return np.zeros((depth.shape[0], depth.shape[1], 3), dtype=np.uint8)

    min_d = np.percentile(depth_vis[valid], 5)
    max_d = np.percentile(depth_vis[valid], 95)

    if max_d <= min_d:
        max_d = min_d + 1.0

    depth_norm = np.clip((depth_vis - min_d) / (max_d - min_d), 0, 1)
    depth_norm = (depth_norm * 255).astype(np.uint8)

    depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

    depth_color[~valid] = (0, 0, 0)

    return depth_color


def main():
    rgbd = None

    try:
        rgbd = RGBD(
            camera_backend         = "realsense",
            rgb_camera_index       = 4,
            depth_camera_index     = 0,
            robot_weight_path      = "/home/thor/Projects/CAPSTONE/runs/end_effector_yolo12n_416_safe/weights/best.pt",
            yolo_world_weight_path = "yolov8s-worldv2.pt",
            conf_thres             = 0.35,
            imgsz                  = 640,
            device                 = 0,
        )

        print("[TEST] RGBD test started")
        print("[TEST] press q or ESC to quit")

        frame_count = 0

        while True:
            frame, depth, yolo_robot, yolo_world = rgbd.get_frame()

            frame_count += 1

            vis = frame.copy()

            # 로봇 end-effector 표시
            draw_detection(
                vis,
                yolo_robot,
                color=(0, 255, 0),
                label_prefix="ROBOT: ",
            )

            # YOLO-World 객체 표시
            for obj in yolo_world:
                draw_detection(
                    vis,
                    obj,
                    color=(0, 128, 255),
                    label_prefix="WORLD: ",
                )

            # 상태 출력
            status_text = f"frame={frame_count} robot={yolo_robot is not None} world_objs={len(yolo_world)}"
            cv2.putText(
                vis,
                status_text,
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("RGBD Detection Test", vis)

            # Depth 화면도 같이 확인
            depth_view = make_depth_view(depth)
            if depth_view is not None:
                cv2.imshow("Depth Test", depth_view)

            # 터미널 출력
            print("=" * 60)
            print(f"[FRAME] {frame_count}")

            if yolo_robot is None:
                print("[ROBOT] None")
            else:
                print("[ROBOT]", yolo_robot)

            if len(yolo_world) == 0:
                print("[WORLD] []")
            else:
                for obj in yolo_world:
                    print("[WORLD]", obj)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == 27:
                print("[TEST] quit")
                break

    except KeyboardInterrupt:
        print("\n[TEST] KeyboardInterrupt")

    except Exception as e:
        print(f"[TEST] ERROR: {e}")

    finally:
        if rgbd is not None:
            rgbd.close()

        cv2.destroyAllWindows()
        print("[TEST] closed")


if __name__ == "__main__":
    main()
