from src.process_service import ProcessService
from .RobotManager import ROBOT


class RobotService(ProcessService):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._worker_args = args
        self._worker_kwargs = kwargs

    def _process_main(self):
        robot = ROBOT(*self._worker_args, **self._worker_kwargs)

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
                if method == "run_sequence":
                    action_sequence = args[0] if args else kwargs.get("action_sequence")
                    camera_data = kwargs.get("camera_data")
                    results = []

                    for action in action_sequence or []:
                        result = robot.action(action, rgbd_cam=camera_data)
                        results.append({"action": action, "result": result})

                        if result in ["failed", "unsafe"]:
                            break

                    result = results
                else:
                    func = getattr(robot, method)
                    result = func(*args, **kwargs)

                self._response_queue.put({"status": "ok", "result": result})
            except Exception as exc:
                self._response_queue.put(
                    {"status": "error", "error": str(exc)}
                )

    def run_sequence(self, action_sequence, camera_data=None):
        return self.call(
            "run_sequence",
            action_sequence,
            camera_data=camera_data,
        )

    def action(self, action, camera_data=None):
        return self.call("action", action, rgbd_cam=camera_data)

    def close(self):
        super().close()
