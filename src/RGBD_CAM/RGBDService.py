from src.process_service import ProcessService
from .RGBD import RGBD


class RGBDService(ProcessService):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._worker_args = args
        self._worker_kwargs = kwargs

    def _process_main(self):
        rgbd = RGBD(*self._worker_args, **self._worker_kwargs)
        latest_camera_data = None

        try:
            while True:
                request = self._request_queue.get()

                if request is None:
                    break

                if request.get("type") == "shutdown":
                    break

                if request.get("type") != "call":
                    continue

                method = request.get("method")
                args = request.get("args", [])
                kwargs = request.get("kwargs", {})

                try:
                    if method == "get_frame":
                        frame, depth, yolo_robot, yolo_world = rgbd.get_frame()
                        latest_camera_data = {
                            "frame": frame,
                            "depth": depth,
                            "yolo_robot": yolo_robot,
                            "yolo_world": yolo_world,
                        }
                        result = (frame, depth, yolo_robot, yolo_world)
                    elif method == "get_latest_camera_data":
                        result = (
                            latest_camera_data.copy()
                            if latest_camera_data is not None
                            else None
                        )
                    else:
                        func = getattr(rgbd, method)
                        result = func(*args, **kwargs)

                    self._response_queue.put({"status": "ok", "result": result})
                except Exception as exc:
                    self._response_queue.put(
                        {"status": "error", "error": str(exc)}
                    )
        finally:
            try:
                rgbd.close()
            except Exception:
                pass

    def get_frame(self):
        return self.call("get_frame")

    def get_latest_camera_data(self):
        return self.call("get_latest_camera_data")

    def close(self):
        super().close()

    def is_yolo_world_enabled(self):
        return self.call("is_yolo_world_enabled")

    def set_yolo_world_enabled(self, enabled):
        return self.call("set_yolo_world_enabled", enabled)

    def is_calibration_prediction_enabled(self):
        return self.call("is_calibration_prediction_enabled")

    def set_calibration_prediction_enabled(self, enabled):
        return self.call("set_calibration_prediction_enabled", enabled)

    def _load_calibration_model(self):
        return self.call("_load_calibration_model")
