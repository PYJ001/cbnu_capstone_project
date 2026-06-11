from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


class RGB:
    def __init__(
        self,
        rgb_camera_index=0,
        robot_weight_path="/home/thor/Projects/CAPSTONE/runs/end_effector_yolo12n_416_safe/weights/best.pt",
        yolo_world_weight_path="yolov8s-worldv2.pt",
        yolo_world_classes=None,
        conf_thres=0.35,
        imgsz=640,
        device=0,
        default_depth=1.0,
    ):
        self.rgb_camera_index = rgb_camera_index

        self.robot_weight_path = Path(robot_weight_path)
        self.yolo_world_weight_path = yolo_world_weight_path

        self.conf_thres = conf_thres
        self.imgsz = imgsz
        self.device = device

        self.default_depth = float(default_depth)

        if yolo_world_classes is None:
            yolo_world_classes = ["bottle", "cup", "box", "apple", "banana"]

        self.yolo_world_classes = yolo_world_classes

        print("[RGB] loading robot YOLO...")
        self.robot_model = YOLO(str(self.robot_weight_path))

        print("[RGB] loading YOLO-World...")
        self.world_model = YOLO(self.yolo_world_weight_path)

        try:
            self.world_model.set_classes(self.yolo_world_classes)
        except Exception as e:
            print(f"[RGB] set_classes failed: {e}")

        self.rgb_cap = None

        self._open_camera()

    def _open_camera(self):
        self.rgb_cap = cv2.VideoCapture(self.rgb_camera_index)

        if not self.rgb_cap.isOpened():
            raise RuntimeError(f"RGB camera open failed: index={self.rgb_camera_index}")

        self.rgb_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.rgb_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.rgb_cap.set(cv2.CAP_PROP_FPS, 30)

        print("[RGB] RGB camera opened")

    def get_frame(self):
        frame, depth = self._read_rgb()

        yolo_robot = self._yolo_robot_inference(frame, depth)
        yolo_world = self._yolo_world_inference(frame, depth)

        return frame, depth, yolo_robot, yolo_world

    def _read_rgb(self):
        ret, frame = self.rgb_cap.read()

        if not ret:
            raise RuntimeError("RGB frame read failed")

        h, w = frame.shape[:2]

        depth = np.full(
            (h, w),
            self.default_depth,
            dtype=np.float32,
        )

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

        return {
            "name": "end_effector",
            "u": u,
            "v": v,
            "d": d,
            "conf": conf,
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
        }

    def _yolo_world_inference(self, frame, depth):
        results = self.world_model.predict(
            source=frame,
            conf=self.conf_thres,
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

            name = names.get(cls_id, str(cls_id))

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
        if self.rgb_cap is not None:
            self.rgb_cap.release()