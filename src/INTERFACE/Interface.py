# src/INTERFACE/Interface.py
#
# Optional OpenCV-based interface and visualizer.
# The main application uses src/INTERFACE/interface_pyqt5.py instead.
# Shared drawing utilities are provided by src/INTERFACE/interface_utils.py.

import time
import threading
import multiprocessing as mp
from queue import Empty

import cv2
import numpy as np

from .interface_utils import draw_detections, make_depth_view, draw_text_panel


_stt = None


class Interface:
    def __init__(
        self,
        window_name             = "Robot Interface",
        show_window             = True,
        camera_sleep            = 0.03,
    ):
        self.window_name        = window_name
        self.show_window        = show_window
        self.camera_sleep       = camera_sleep

        self.latest_camera_data = None
        self.latest_lock        = threading.Lock()

        self.camera_running     = False
        self.camera_thread      = None

        self.vis_queue          = mp.Queue(maxsize=1)
        self.vis_stop_event     = mp.Event()

        self.state = {
            "user_command"    : "",
            "vlm_summary"     : "",
            "print_out"       : "",
            "action_sequence" : [],
            "action_result"   : "",
        }

        if self.show_window:
            self.vis_process = mp.Process(
                target=_visualizer_loop,
                args=(
                    self.window_name,
                    self.vis_queue,
                    self.vis_stop_event,
                ),
                daemon=True,
            )
            self.vis_process.start()
        else:
            self.vis_process = None

    def start_camera_stream(self, rgbd_cam):
        self.camera_running = True

        self.camera_thread = threading.Thread(
            target = self._camera_loop,
            args   = (rgbd_cam,),
            daemon = True,
        )

        self.camera_thread.start()

    def _camera_loop(self, rgbd_cam):
        while self.camera_running:
            try:
                frame, depth, yolo_robot, yolo_world = rgbd_cam.get_frame()

                camera_data = {
                    "frame"      : frame,
                    "depth"      : depth,
                    "yolo_robot" : yolo_robot,
                    "yolo_world" : yolo_world,
                }

                with self.latest_lock:
                    self.latest_camera_data = camera_data

                packet = {
                    "frame"      : frame,
                    "depth"      : depth,
                    "yolo_robot" : yolo_robot,
                    "yolo_world" : yolo_world,
                    "state"      : self.state.copy(),
                }

                self._send_to_visualizer(packet)

            except Exception as e:
                print(f"[Interface] camera loop error: {e}")
                time.sleep(0.2)

            time.sleep(self.camera_sleep)

    def get_latest_camera_data(self):
        with self.latest_lock:
            if self.latest_camera_data is None:
                return None

            return self.latest_camera_data.copy()

    def get_user_command(self, timeout=None):
        global _stt

        while True:
            mode = input("\nInput mode [t=text, v=voice, q=quit] > ").strip().lower()

            if mode in ["q", "quit", "exit"]:
                return "quit"

            if mode in ["t", "text"]:
                command = input("User command > ")
                return command.strip()

            if mode in ["v", "voice"]:
                if _stt is None:
                    try:
                        from .VoiceManager import WhisperSTT
                        _stt = WhisperSTT()
                    except Exception as e:
                        print(f"[Interface] voice mode unavailable: {e}")
                        return ""

                command = _stt.listen()

                if command is None:
                    print("[Interface] voice command is empty")
                    return ""

                command = command.strip()
                print(f"[Interface] voice command: {command}")

                return command

            print("[Interface] invalid mode. Please enter t, v, or q.")

    def update(
        self,
        user_command    = None,
        vlm_summary     = None,
        print_out       = None,
        result_text     = None,
        action_sequence = None,
        action_result   = None,
    ):
        if user_command is not None:
            self.state["user_command"] = user_command

        if vlm_summary is not None:
            self.state["vlm_summary"] = vlm_summary

        if print_out is not None:
            self.state["print_out"] = print_out

        if result_text is not None and print_out is None:
            self.state["print_out"] = result_text

        if action_sequence is not None:
            self.state["action_sequence"] = action_sequence

        if action_result is not None:
            self.state["action_result"] = action_result

        with self.latest_lock:
            camera_data = self.latest_camera_data

        if camera_data is None:
            return

        packet = {
            "frame"      : camera_data["frame"],
            "depth"      : camera_data["depth"],
            "yolo_robot" : camera_data["yolo_robot"],
            "yolo_world" : camera_data["yolo_world"],
            "state"      : self.state.copy(),
        }

        self._send_to_visualizer(packet)

    def _send_to_visualizer(self, packet):
        if not self.show_window:
            return

        try:
            while not self.vis_queue.empty():
                self.vis_queue.get_nowait()
        except Exception:
            pass

        try:
            self.vis_queue.put_nowait(packet)
        except Exception:
            pass

    def run(self):
        try:
            while self.camera_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

    def close(self):
        self.camera_running = False

        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)

        if self.show_window:
            self.vis_stop_event.set()

            if self.vis_process is not None:
                self.vis_process.join(timeout=1.0)

                if self.vis_process.is_alive():
                    self.vis_process.terminate()

def _visualizer_loop(window_name, vis_queue, stop_event):
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    latest_packet = None

    while not stop_event.is_set():
        try:
            latest_packet = vis_queue.get(timeout=0.03)
        except Empty:
            pass

        if latest_packet is None:
            key = cv2.waitKey(1)
            if key == ord("q"):
                break
            continue

        frame = latest_packet.get("frame", None)
        depth = latest_packet.get("depth", None)
        yolo_robot = latest_packet.get("yolo_robot", [])
        yolo_world = latest_packet.get("yolo_world", [])
        state = latest_packet.get("state", {})

        if frame is None:
            continue

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        vis_frame = draw_detections(frame, yolo_robot, yolo_world)
        depth_view = make_depth_view(depth, vis_frame.shape)
        text_panel = draw_text_panel(vis_frame, state)

        display = np.hstack([vis_frame, depth_view, text_panel])

        cv2.imshow(window_name, display)

        key = cv2.waitKey(1)
        if key == ord("q"):
            break

    cv2.destroyWindow(window_name)

    
