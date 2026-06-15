import multiprocessing as mp
import traceback


class ProcessService:
    def __init__(self):
        self._request_queue = mp.Queue()
        self._response_queue = mp.Queue()
        self._process = None

    def launch(self):
        if self._process is not None and self._process.is_alive():
            return

        self._process = mp.Process(
            target=self._process_main_wrapper,
            daemon=True,
        )
        self._process.start()

    def close(self):
        if self._process is None:
            return

        try:
            self._request_queue.put({"type": "shutdown"})
        except Exception:
            pass

        self._process.join(timeout=5.0)

        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)

        self._process = None

    def call(self, method, *args, **kwargs):
        if self._process is None or not self._process.is_alive():
            raise RuntimeError("service is not running")

        self._request_queue.put(
            {
                "type": "call",
                "method": method,
                "args": args,
                "kwargs": kwargs,
            }
        )

        response = self._response_queue.get()

        if response.get("status") == "ok":
            return response.get("result")

        raise RuntimeError(response.get("error", "unknown service error"))

    def _process_main_wrapper(self):
        try:
            self._process_main()
        except Exception:
            traceback.print_exc()

    def _process_main(self):
        raise NotImplementedError
