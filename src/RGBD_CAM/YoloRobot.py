from pathlib import Path

import numpy as np
from ultralytics import YOLO


class YoloRobotDetector:
    def __init__(
        self,
        weight_path="runs/end_effector_yolo12n_416_safe/weights/best.pt",
        conf_thres=0.35,
        imgsz=640,
        device=0,
        robot_depth_offset=0.05,
        robot_depth_center_radius=20,
    ):
        self.weight_path         = Path(weight_path)
        self.conf_thres          = conf_thres
        self.imgsz               = imgsz
        self.device              = device
        self.robot_depth_offset  = float(robot_depth_offset)
        self.robot_depth_center_radius = int(robot_depth_center_radius)

        print("[YoloRobotDetector] loading robot YOLO...")
        self.model = YOLO(str(self.weight_path))

    def inference(self, frame, depth):
        results = self.model.predict(
            source  = frame,
            conf    = self.conf_thres,
            imgsz   = self.imgsz,
            device  = self.device,
            verbose = False,
        )

        if len(results) == 0:
            return None

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            return None

        boxes    = result.boxes
        best_idx = int(boxes.conf.argmax().item())

        xyxy = boxes.xyxy[best_idx].detach().cpu().numpy()
        conf = float(boxes.conf[best_idx].detach().cpu().item())

        obj = self._make_object_dict(
            name  = "end_effector",
            xyxy  = xyxy,
            conf  = conf,
            depth = depth,
        )

        obj["d"] = self._apply_robot_depth_offset(obj["d"])

        return obj

    def _make_object_dict(self, name, xyxy, conf, depth):
        x1, y1, x2, y2 = xyxy

        u = int((x1 + x2) / 2)
        v = int((y1 + y2) / 2)
        d = self._get_nearest_depth_near_center(
            depth=depth,
            u=u,
            v=v,
            xyxy=xyxy,
        )

        return {
            "name": name,
            "u": u,
            "v": v,
            "d": d,
            "conf": conf,
            "bbox": [float(x1), float(y1), float(x2), float(y2)],
            "depth_radius": int(self.robot_depth_center_radius),
        }

    def _apply_robot_depth_offset(self, depth_value):
        if depth_value is None:
            return None

        return float(depth_value) + self.robot_depth_offset

    def _get_nearest_depth_near_center(self, depth, u, v, xyxy):
        if depth is None:
            return None

        h, w = depth.shape[:2]

        u = int(np.clip(u, 0, w - 1))
        v = int(np.clip(v, 0, h - 1))
        radius = max(1, int(self.robot_depth_center_radius))
        bx1, by1, bx2, by2 = xyxy

        x1 = max(0, int(np.floor(max(bx1, u - radius))))
        x2 = min(w, int(np.ceil(min(bx2, u + radius + 1))))
        y1 = max(0, int(np.floor(max(by1, v - radius))))
        y2 = min(h, int(np.ceil(min(by2, v + radius + 1))))

        if x1 >= x2 or y1 >= y2:
            return None

        patch = depth[y1:y2, x1:x2].astype(np.float32)

        valid = patch[np.isfinite(patch)]
        valid = valid[valid > 0]

        if len(valid) == 0:
            return None

        return float(np.min(valid))


class YoloRobot:
    def __init__(self, *args, **kwargs):
        self.enabled = True
        self.detector = YoloRobotDetector(*args, **kwargs)

    def inference(self, frame, depth):
        if not self.enabled:
            return None

        return self.detector.inference(frame, depth)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def is_enabled(self):
        return self.enabled
