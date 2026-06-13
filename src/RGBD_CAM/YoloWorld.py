import threading

import numpy as np
from ultralytics import YOLO


class YoloWorldDetector:
    def __init__(
        self,
        weight_path="yolov8s-worldv2.pt",
        classes=None,
        conf_thres=0.35,
        imgsz=640,
        device=0,
    ):
        self.weight_path       = weight_path
        self.conf_thres        = min(conf_thres, 0.25)
        self.imgsz             = imgsz
        self.device            = device
        self.enabled           = True
        self.classes           = []
        self.lock              = threading.Lock()

        print("[YoloWorldDetector] loading YOLO-World...")
        self.model = YOLO(self.weight_path)

        self.set_classes(classes or [])

    def inference(self, frame, depth):
        with self.lock:
            if not self.enabled:
                return []

            if len(self.classes) == 0:
                return []

            results = self.model.predict(
                source  = frame,
                conf    = self.conf_thres,
                imgsz   = self.imgsz,
                device  = self.device,
                verbose = False,
            )

        objs = []

        if len(results) == 0:
            return objs

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            return objs

        names = result.names

        for box in result.boxes:
            xyxy   = box.xyxy[0].detach().cpu().numpy()
            conf   = float(  box.conf[0].detach().cpu().item()  )
            cls_id = int(    box.cls[0] .detach().cpu().item()  )

            raw_name = names.get(cls_id, str(cls_id))
            name     = self._canonical_name(raw_name)

            obj = self._make_object_dict(
                name  = name,
                xyxy  = xyxy,
                conf  = conf,
                depth = depth,
            )

            objs.append(obj)

        return objs

    def set_classes(self, classes):
        clean_classes = self._clean_classes(classes)

        with self.lock:
            if clean_classes == self.classes:
                return

            try:
                self._set_model_classes(clean_classes)
                self.classes = clean_classes

                print(f"[YoloWorldDetector] classes: {self.classes}")

            except Exception as e:
                print(f"[YoloWorldDetector] set_classes failed: {e}")

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)

        state = "enabled" if self.enabled else "disabled"
        print(f"[YoloWorldDetector] {state}")

    def is_enabled(self):
        with self.lock:
            return self.enabled

    def get_classes(self):
        with self.lock:
            return self.classes.copy()

    def _set_model_classes(self, classes):
        try:
            self.model.to("cpu")
        except Exception:
            try:
                self.model.model.cpu()
            except Exception:
                pass

        self.model.predictor = None
        self.model.set_classes(classes)

    def _clean_classes(self, classes):
        if classes is None:
            return []

        if isinstance(classes, str):
            classes = [classes]

        result = []
        seen   = set()

        for item in classes:
            name = self._canonical_name(item)

            if name == "" or name in seen:
                continue

            for prompt_name in self._expand_class_prompt(name):
                if prompt_name in seen:
                    continue

                seen.add(prompt_name)
                result.append(prompt_name)

                if len(result) >= 10:
                    break

            if len(result) >= 10:
                break

        return result

    def _canonical_name(self, name):
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

    def _expand_class_prompt(self, name):
        if name == "hand":
            return ["hand", "human hand", "person hand"]

        return [name]

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
