import glob
import threading
import time

import cv2
import numpy as np


class RGBD:
    def __init__(
        self,
        camera_backend="realsense",
        rgb_camera_index=4,
        depth_camera_index=0,
        frame_timeout_ms=2000,
        max_realsense_restarts=0,
        max_realsense_hardware_resets=1,
        realsense_width=640,
        realsense_height=480,
        realsense_fps=6,
    ):
        self.camera_backend     = camera_backend
        self.rgb_camera_index   = rgb_camera_index
        self.depth_camera_index = depth_camera_index
        self.frame_timeout_ms   = int(frame_timeout_ms)
        self.max_realsense_restarts = int(max_realsense_restarts)
        self.max_realsense_hardware_resets = int(max_realsense_hardware_resets)
        self.realsense_width = int(realsense_width)
        self.realsense_height = int(realsense_height)
        self.realsense_fps = int(realsense_fps)

        self.pipeline  = None
        self.align     = None
        self.rgb_cap   = None
        self.depth_cap = None
        self.rs        = None

        self.latest_rgbd_frame = None
        self.latest_lock       = threading.Lock()
        self.read_lock         = threading.Lock()
        self.camera_running    = False
        self.camera_thread     = None
        self.camera_error_count = 0
        self.realsense_restart_count = 0
        self.realsense_hardware_reset_count = 0
        self.placeholder_reported = False

    # lifecycle
    def launch(self):
        self._open_camera()
        self._start_camera_stream()
        return True

    def run(self):
        return self.capture_rgbd_frame()

    def close(self):
        self.camera_running = False

        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None

        self._close_camera()
        return True

    # init
    def _start_camera_stream(self):
        if self.camera_running:
            return True

        self.camera_running = True
        self.camera_thread = threading.Thread(
            target=self.camera_loop,
            daemon=True,
        )
        self.camera_thread.start()
        return True

    def _open_camera(self):
        if self.pipeline is not None or self.rgb_cap is not None:
            return True

        if self.camera_backend == "placeholder":
            if not self.placeholder_reported:
                print("[RGBD] using placeholder camera")
                self.placeholder_reported = True
            return True

        if self.camera_backend == "realsense":
            try:
                import pyrealsense2 as rs

                print("[RGBD] opening RealSense camera")
                self.rs = rs
                self.pipeline = rs.pipeline()

                config = rs.config()
                config.enable_stream(
                    rs.stream.color,
                    self.realsense_width,
                    self.realsense_height,
                    rs.format.bgr8,
                    self.realsense_fps,
                )
                config.enable_stream(
                    rs.stream.depth,
                    self.realsense_width,
                    self.realsense_height,
                    rs.format.z16,
                    self.realsense_fps,
                )

                self.pipeline.start(config)
                self.align = rs.align(rs.stream.color)
                print(
                    "[RGBD] RealSense opened "
                    f"{self.realsense_width}x{self.realsense_height}"
                    f"@{self.realsense_fps}"
                )
                return True

            except Exception as exc:
                print(f"[RGBD] RealSense open failed: {exc}")
                print("[RGBD] fallback to OpenCV camera")

        self.camera_backend = "opencv"
        self.rgb_cap = self._find_camera(self.rgb_camera_index)

        if self.rgb_cap is None:
            print(
                "[RGBD] OpenCV camera open failed. "
                "Using placeholder camera."
            )
            self.camera_backend = "placeholder"
            return True

        self.depth_cap = self._find_camera(
            self.depth_camera_index,
            exclude=self.rgb_camera_index,
        )

        self._setup_opencv_capture(self.rgb_cap)

        if self.depth_cap is not None:
            self._setup_opencv_capture(self.depth_cap)

        print("[RGBD] OpenCV camera opened")
        return True

    def _close_camera(self):
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass
            self.pipeline = None
            self.align = None

        if self.rgb_cap is not None:
            self.rgb_cap.release()
            self.rgb_cap = None

        if self.depth_cap is not None:
            self.depth_cap.release()
            self.depth_cap = None

    # get
    def get_rgb(self):
        return self.capture_rgbd_frame()["frame"]

    def get_depth(self):
        return self.capture_rgbd_frame()["depth"]

    def get_rgbd(self):
        rgbd_frame = self.capture_rgbd_frame()
        return rgbd_frame["frame"], rgbd_frame["depth"]

    def get_frame(self):
        return self.get_rgbd()

    def get_latest_rgbd_frame(self):
        with self.latest_lock:
            if self.latest_rgbd_frame is None:
                return None

            return self.latest_rgbd_frame.copy()

    def get_latest_camera_data(self):
        return self.get_latest_rgbd_frame()

    def capture_rgbd_frame(self):
        with self.read_lock:
            frame, depth = self._read_camera_once()

        rgbd_frame = self._make_rgbd_frame(frame, depth)

        with self.latest_lock:
            self.latest_rgbd_frame = rgbd_frame

        return rgbd_frame

    def get_camera_data(self):
        return self.capture_rgbd_frame()

    # loop
    def camera_loop(self):
        while self.camera_running:
            try:
                self.capture_rgbd_frame()
                self.camera_error_count = 0
            except Exception as exc:
                self.camera_error_count += 1
                print(f"[RGBD] camera_loop error: {exc}")
                self._recover_camera_after_error()
                time.sleep(0.2)

            time.sleep(0.03)

    def _read_camera_once(self):
        self._open_camera()

        if self.camera_backend == "realsense":
            return self._read_realsense()

        if self.camera_backend == "placeholder":
            return self._read_placeholder()

        return self._read_opencv()

    def _make_rgbd_frame(self, frame, depth):
        return {
            "frame": frame,
            "depth": depth,
        }

    # camera implementation helpers
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
        seen = set()

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

    def _read_realsense(self):
        frames = self.pipeline.wait_for_frames(self.frame_timeout_ms)
        aligned_frames = self.align.process(frames)

        color_frame = aligned_frames.get_color_frame()
        depth_frame = aligned_frames.get_depth_frame()

        if not color_frame or not depth_frame:
            raise RuntimeError("RealSense frame read failed")

        frame = np.asanyarray(color_frame.get_data())
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

    def _recover_camera_after_error(self):
        if self.camera_error_count < 3:
            return False

        if self.camera_backend != "realsense":
            print("[RGBD] camera failed repeatedly. Using placeholder camera.")
            self.camera_error_count = 0
            self._close_camera()
            self.camera_backend = "placeholder"
            return False

        self.camera_error_count = 0

        if (
            self.realsense_hardware_reset_count
            < self.max_realsense_hardware_resets
        ):
            self.realsense_hardware_reset_count += 1
            print(
                "[RGBD] RealSense frame timeout persists. "
                "Running hardware reset "
                f"({self.realsense_hardware_reset_count}/"
                f"{self.max_realsense_hardware_resets})"
            )
            return self._hardware_reset_realsense()

        if self.realsense_restart_count >= self.max_realsense_restarts:
            print(
                "[RGBD] RealSense frame timeout persists. "
                "Using placeholder camera."
            )
            self._close_camera()
            self.camera_backend = "placeholder"
            return self._open_camera()

        self.realsense_restart_count += 1
        print(
            "[RGBD] restarting RealSense after repeated frame timeouts "
            f"({self.realsense_restart_count}/{self.max_realsense_restarts})"
        )

        try:
            self._close_camera()
            time.sleep(0.2)
            return self._open_camera()
        except Exception as exc:
            print(f"[RGBD] RealSense restart failed: {exc}")
            return False

    def _hardware_reset_realsense(self):
        try:
            rs = self.rs

            if rs is None:
                import pyrealsense2 as rs

            self._close_camera()
            ctx = rs.context()
            devices = ctx.query_devices()

            if len(devices) == 0:
                print("[RGBD] RealSense hardware reset skipped: no device")
                self.camera_backend = "placeholder"
                return self._open_camera()

            devices[0].hardware_reset()
            time.sleep(3.0)
            self.camera_backend = "realsense"
            return self._open_camera()

        except Exception as exc:
            print(f"[RGBD] RealSense hardware reset failed: {exc}")
            self.camera_backend = "placeholder"
            return self._open_camera()

    def _read_placeholder(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        depth = np.zeros((480, 640), dtype=np.float32)

        cv2.putText(
            frame,
            "Camera unavailable",
            (150, 220),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "Check RealSense connection / realsense-viewer",
            (70, 265),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (180, 180, 180),
            2,
            cv2.LINE_AA,
        )
        return frame, depth

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

    # test
    def test(self, duration=60.0, sleep=1.0):
        self.launch()
        started_at = time.time()
        tick = 0

        try:
            while time.time() - started_at < duration:
                tick += 1
                rgbd_frame = self.get_latest_rgbd_frame()

                if rgbd_frame is None:
                    rgbd_frame = self.capture_rgbd_frame()

                print(
                    "[RGBD TEST] "
                    f"tick={tick} "
                    f"frame={getattr(rgbd_frame['frame'], 'shape', None)} "
                    f"depth={getattr(rgbd_frame['depth'], 'shape', None)}"
                )
                time.sleep(sleep)

        finally:
            self.close()


def main():
    rgbd = RGBD()
    rgbd.test(duration=60.0, sleep=1.0)


if __name__ == "__main__":
    main()
