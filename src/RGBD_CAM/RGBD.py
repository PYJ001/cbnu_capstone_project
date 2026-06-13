import glob

import cv2
import numpy as np

from src.CALIBRATION import CalibrationModel
from .YoloRobot import YoloRobotDetector
from .YoloWorld import YoloWorldDetector


# ===============================================================
# RGBD Camera

class RGBD:
    def __init__(
        self,
        camera_backend="realsense",
        rgb_camera_index=4,
        depth_camera_index=0,
        robot_weight_path="runs/end_effector_yolo12n_416_safe/weights/best.pt",
        yolo_world_weight_path="yolov8s-worldv2.pt",
        yolo_world_classes=None,
        conf_thres=0.35,
        imgsz=640,
        device=0,
        calibration_csv_path=None,
        calibration_search_dir="src/CALIBRATION/robot_camera_calibration_samples",
        calibration_k=4,
        robot_depth_offset=0.05,
    ):
        self.camera_backend                 = camera_backend
        self.rgb_camera_index               = rgb_camera_index
        self.depth_camera_index             = depth_camera_index

        self.conf_thres                     = conf_thres
        self.world_conf_thres               = min(conf_thres, 0.25)
        self.imgsz                          = imgsz
        self.device                         = device
        self.calibration_csv_path           = calibration_csv_path
        self.calibration_search_dir         = calibration_search_dir
        self.calibration_k                  = calibration_k
        self.robot_depth_offset             = float(robot_depth_offset)
        self.calibration_prediction_enabled = True

        self.pipeline                       = None
        self.align                          = None
        self.rgb_cap                        = None
        self.depth_cap                      = None
        self.rs                             = None

        self.yolo_robot = YoloRobotDetector(
            weight_path        = robot_weight_path,
            conf_thres         = self.conf_thres,
            imgsz              = self.imgsz,
            device             = self.device,
            robot_depth_offset = self.robot_depth_offset,
        )

        self.yolo_world = YoloWorldDetector(
            weight_path = yolo_world_weight_path,
            classes     = yolo_world_classes or [],
            conf_thres  = self.conf_thres,
            imgsz       = self.imgsz,
            device      = self.device,
        )

        self.calibration_model = self._load_calibration_model()

        self._open_camera()

    # -----------------------------------------------------------
    # Public API

    def get_frame(self):
        frame, depth = self._read_rgbd()

        yolo_robot = self.yolo_robot.inference(frame, depth)
        yolo_world = self.yolo_world.inference(frame, depth)

        if yolo_robot is not None:
            yolo_robot["joint"] = self._calibration(yolo_robot)

        for obj in yolo_world:
            obj["joint"] = self._calibration(obj)

        return frame, depth, yolo_robot, yolo_world

    def close(self):
        if self.pipeline is not None:
            self.pipeline.stop()

        if self.rgb_cap is not None:
            self.rgb_cap.release()

        if self.depth_cap is not None:
            self.depth_cap.release()

    # -----------------------------------------------------------
    # Camera open

    def _open_camera(self):
        if self.camera_backend == "realsense":
            try:
                import pyrealsense2 as rs

                print("[RGBD] opening RealSense camera")

                self.rs       = rs
                self.pipeline = rs.pipeline()

                config = rs.config()

                config.enable_stream(
                    rs.stream.color,
                    640,
                    480,
                    rs.format.bgr8,
                    30,
                )

                config.enable_stream(
                    rs.stream.depth,
                    640,
                    480,
                    rs.format.z16,
                    30,
                )

                self.pipeline.start(config)
                self.align = rs.align(rs.stream.color)

                print("[RGBD] RealSense opened")
                return

            except Exception as e:
                print(f"[RGBD] RealSense open failed: {e}")
                print("[RGBD] fallback to OpenCV camera")

        self.camera_backend = "opencv"
        self._open_opencv_camera()

    def _open_opencv_camera(self):
        self.rgb_cap = self._find_camera(self.rgb_camera_index)

        if self.rgb_cap is None:
            raise RuntimeError(
                "RGB camera open failed: unable to open any /dev/video* device. "
                "Check camera device, permissions, or set rgb_camera_index explicitly."
            )

        print(f"[RGBD] RGB camera found at {self.rgb_camera_index}")

        self.depth_cap = self._find_camera(
            self.depth_camera_index,
            exclude=self.rgb_camera_index,
        )

        if self.depth_cap is None:
            print("[RGBD] depth camera open failed. Depth will be zeros.")
        else:
            print(f"[RGBD] Depth camera found at {self.depth_camera_index}")

        self._setup_opencv_capture(self.rgb_cap)

        if self.depth_cap is not None:
            self._setup_opencv_capture(self.depth_cap)

        print("[RGBD] OpenCV camera opened")

    def _find_camera(self, first_candidate, exclude=None):
        candidates = self._make_camera_candidates(first_candidate)

        for candidate in candidates:
            if candidate == exclude:
                continue

            cap = self._try_open_camera(candidate)

            if cap is not None:
                return cap

        return None

    def _make_camera_candidates(self, first_candidate):
        candidates = []

        try:
            candidates.append(int(first_candidate))
        except Exception:
            candidates.append(str(first_candidate))

        candidates.extend(range(12))
        candidates.extend(sorted(glob.glob("/dev/video*")))

        result = []
        seen   = set()

        for candidate in candidates:
            key = str(candidate)

            if key in seen:
                continue

            seen.add(key)
            result.append(candidate)

        return result

    def _try_open_camera(self, candidate):
        cap = None

        try:
            cap = cv2.VideoCapture(candidate)

            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(candidate, cv2.CAP_V4L2)

            if cap is None or not cap.isOpened():
                return None

            ret, frame = cap.read()

            if not ret or frame is None or frame.size == 0:
                cap.release()
                return None

            return cap

        except Exception:
            if cap is not None:
                cap.release()

            return None

    def _setup_opencv_capture(self, cap):
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
        except Exception:
            pass

    # -----------------------------------------------------------
    # Camera read

    def _read_rgbd(self):
        if self.camera_backend == "realsense":
            return self._read_realsense()

        return self._read_opencv()

    def _read_realsense(self):
        frames         = self.pipeline.wait_for_frames()
        aligned_frames = self.align.process(frames)

        color_frame = aligned_frames.get_color_frame()
        depth_frame = aligned_frames.get_depth_frame()

        if not color_frame or not depth_frame:
            raise RuntimeError("RealSense frame read failed")

        frame     = np.asanyarray(color_frame.get_data())
        depth_raw = np.asanyarray(depth_frame.get_data())

        depth_scale = (
            self.pipeline
            .get_active_profile()
            .get_device()
            .first_depth_sensor()
            .get_depth_scale()
        )

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

    # -----------------------------------------------------------
    # YOLO-World control wrapper

    def set_yolo_world_classes(self, classes):
        self.yolo_world.set_classes(classes)

    def get_yolo_world_classes(self):
        return self.yolo_world.get_classes()

    def set_yolo_world_enabled(self, enabled):
        self.yolo_world.set_enabled(enabled)

    def is_yolo_world_enabled(self):
        return self.yolo_world.is_enabled()

    # -----------------------------------------------------------
    # Calibration

    def set_calibration_prediction_enabled(self, enabled):
        self.calibration_prediction_enabled = bool(enabled)

        state = "enabled" if self.calibration_prediction_enabled else "disabled"
        print(f"[RGBD] calibration prediction {state}")

    def is_calibration_prediction_enabled(self):
        return self.calibration_prediction_enabled

    def _load_calibration_model(self):
        try:
            model = CalibrationModel.from_latest_or_path(
                csv_path   = self.calibration_csv_path,
                search_dir = self.calibration_search_dir,
                k          = self.calibration_k,
            )

            print(f"[RGBD] calibration loaded: {model.csv_path}")
            return model

        except Exception as e:
            print(f"[RGBD] calibration disabled: {e}")
            return None

    def _calibration(self, obj):
        if not self.calibration_prediction_enabled:
            return None

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
