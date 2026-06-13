from src.process_service import ProcessService
from .LLM_planner import LLMPlanner


class LLMPlannerService(ProcessService):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._worker_args = args
        self._worker_kwargs = kwargs

    def _process_main(self):
        planner = LLMPlanner(*self._worker_args, **self._worker_kwargs)

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
                func = getattr(planner, method)
                result = func(*args, **kwargs)
                self._response_queue.put({"status": "ok", "result": result})
            except Exception as exc:
                self._response_queue.put(
                    {"status": "error", "error": str(exc)}
                )

    def inference(self, *args, **kwargs):
        return self.call("inference", *args, **kwargs)

    def close(self):
        super().close()
