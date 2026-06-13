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
    ):
        self.weight_path         = Path(weight_path)
        self.conf_thres          = conf_thres
        self.imgsz               = imgsz
        self.device              = device
        self.robot_depth_offset  = float(robot_depth_offset)

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
        d = self._get_depth_at(depth, u, v)

        return {
            "name": name,
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
