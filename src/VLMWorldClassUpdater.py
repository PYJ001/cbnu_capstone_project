import multiprocessing as mp
import time
from queue import Empty

from src.VLM import VLM


class VLMWorldClassUpdater:
    def __init__(
        self,
        interval=3.0,
        model_name="qwen2.5vl:3b",
        max_size=384,
        jpeg_quality=70,
    ):
        self.interval = interval
        self.model_name = model_name
        self.max_size = max_size
        self.jpeg_quality = jpeg_quality

        self.input_queue = mp.Queue(maxsize=1)
        self.output_queue = mp.Queue(maxsize=1)
        self.stop_event = mp.Event()
        self.process = None
        self.last_submit_time = 0.0
        self.paused = False

    def start(self):
        if self.process is not None and self.process.is_alive():
            return

        self.process = mp.Process(
            target=_vlm_worker_loop,
            args=(
                self.input_queue,
                self.output_queue,
                self.stop_event,
                self.model_name,
                self.max_size,
                self.jpeg_quality,
            ),
            daemon=True,
        )
        self.process.start()

    def submit_frame(self, frame):
        if self.paused:
            return False

        now = time.time()

        if now - self.last_submit_time < self.interval:
            return False

        self.last_submit_time = now

        try:
            while not self.input_queue.empty():
                self.input_queue.get_nowait()
        except Exception:
            pass

        try:
            self.input_queue.put_nowait(frame.copy())
            return True
        except Exception:
            return False

    def get_latest_result(self):
        if self.paused:
            self.clear_queues()
            return None

        latest_result = None

        try:
            while True:
                latest_result = self.output_queue.get_nowait()
        except Empty:
            pass
        except Exception:
            pass

        return latest_result

    def pause(self):
        self.paused = True
        self.clear_queues()

    def resume(self):
        self.paused = False
        self.last_submit_time = 0.0

    def clear_queues(self):
        self._clear_queue(self.input_queue)
        self._clear_queue(self.output_queue)

    def _clear_queue(self, target_queue):
        try:
            while not target_queue.empty():
                target_queue.get_nowait()
        except Exception:
            pass

    def close(self):
        self.stop_event.set()

        if self.process is not None:
            self.process.join(timeout=1.0)

            if self.process.is_alive():
                self.process.terminate()

            self.process = None


class VLMWorldClassLoop:
    def __init__(
        self,
        interface,
        rgbd_cam,
        vlm_updater,
        latest_vlm,
        latest_vlm_lock,
        stop_event,
    ):
        self.interface = interface
        self.rgbd_cam = rgbd_cam
        self.vlm_updater = vlm_updater
        self.latest_vlm = latest_vlm
        self.latest_vlm_lock = latest_vlm_lock
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            if self.vlm_updater.paused:
                time.sleep(0.2)
                continue

            camera_data = self.interface.get_latest_camera_data()

            if camera_data is None:
                time.sleep(0.1)
                continue

            self.vlm_updater.submit_frame(camera_data["frame"])
            result = self.vlm_updater.get_latest_result()

            if result is not None:
                self._apply_result(result)

            time.sleep(0.1)

    def _apply_result(self, result):
        summary = result.get("summary", "")
        objects = result.get("objects", [])

        with self.latest_vlm_lock:
            self.latest_vlm["summary"] = summary
            self.latest_vlm["objects"] = objects

        print(f"[VLMWorldClassLoop] VLM world classes: {objects}")
        self.rgbd_cam.set_yolo_world_classes(objects)
        self.interface.update(vlm_summary=summary)


def _vlm_worker_loop(
    input_queue,
    output_queue,
    stop_event,
    model_name,
    max_size,
    jpeg_quality,
):
    vlm = VLM(
        model_name=model_name,
        max_size=max_size,
        jpeg_quality=jpeg_quality,
    )

    while not stop_event.is_set():
        try:
            frame = input_queue.get(timeout=0.1)
        except Empty:
            continue

        try:
            result = vlm.infer_scene_and_objects(frame)
            result["timestamp"] = time.time()
        except Exception as e:
            result = {
                "summary": f"VLM failed to describe the image: {e}",
                "objects": [],
                "timestamp": time.time(),
            }

        try:
            while not output_queue.empty():
                output_queue.get_nowait()
        except Exception:
            pass

        try:
            output_queue.put_nowait(result)
        except Exception:
            pass
