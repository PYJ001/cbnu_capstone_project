import queue
import sys
import threading
import time
from pathlib import Path

try:
    from .interface_pyqt5 import InterfacePyQt5Process
except ImportError:
    project_root = Path(__file__).resolve().parents[2]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.INTERFACE.interface_pyqt5 import InterfacePyQt5Process


class Interface:
    """
    RobotApp-facing interface package entry point.

    This class defines the interface shape first. The methods are intentionally
    lightweight so they can be mapped to PyQt widgets and signals later.
    """

    def __init__(self, title="Robot Interface", show_window=True):
        self.title = ""
        self.running = False
        self.show_window = show_window
        self.rgbd_cam = None
        self.command_queue = queue.Queue()
        self.camera_running = False
        self.camera_thread = None
        self.pyqt = InterfacePyQt5Process(title=title, enabled=show_window)
        self.voice_manager = None
        self.tts_queue = queue.Queue()
        self.tts_thread = None
        self.tts_running = False
        self.last_spoken_text = ""

        self.state = {
            "user_command": "",
            "print_out": "",
            "vlm_summary": "",
            "action_sequence": [],
            "action_result": "",
        }

        self.rgbd_state = {
            "frame": None,
            "depth": None,
            "yolo_robot": None,
            "yolo_world": None,
            "inference_frame": None,
            "inference_yolo_robot": None,
            "inference_yolo_world": None,
            "inference_vlm_summary": "",
        }

        self._set_title(title)

    # init
    def _set_title(self, title):
        self.title = str(title)
        self.pyqt.call("set_title", title=self.title)
        return self.title

    # lifecycle
    def launch(self, rgbd_cam=None):
        self.running = True
        self.pyqt.launch()
        self._start_tts()

        if rgbd_cam is not None:
            self.start_camera_stream(rgbd_cam)

        self.update()
        return True

    def run(self):
        while self.running:
            time.sleep(0.1)

    def close(self):
        self.running = False
        self.stop_camera_stream()
        self._stop_tts()
        self.pyqt.close()
        return True

    # button
    def _send(self, command):
        return self._send_handler(command)

    def _send_handler(self, command, enqueue=True):
        command = self._make_user_command(command)

        if command == "":
            return None

        self._set_user_command(command)
        self._set_printOut(f"UserCommand: {command}")

        if enqueue:
            self.command_queue.put(command)

        self.update()
        return command

    def _voice(self):
        return self._voice_handler()

    def _voice_handler(self):
        self._set_printOut("Listening for voice command...")
        self.update()

        try:
            if self.voice_manager is None:
                self.voice_manager = self._make_voice_manager()

            command = self.voice_manager.listen()

        except Exception as exc:
            self._set_printOut(f"Voice command failed: {exc}")
            self.update()
            return None

        if self._make_user_command(command) == "":
            self._set_printOut(
                "Voice command was empty. Check microphone input device."
            )
            self.update()
            return None

        self._load_command_handler(command)
        return None

    def _make_voice_manager(self):
        try:
            from .VoiceManager import VoiceManager
        except ImportError:
            from src.INTERFACE.VoiceManager import VoiceManager

        return VoiceManager()

    def _load_command_handler(self, command):
        command = self._make_user_command(command)

        if command == "":
            return None

        self._set_user_command(command)
        self._set_printOut(f"UserCommand loaded: {command}")
        self.update()
        return command

    def _recalibrate(self):
        return self._recalibrate_handler()

    def _recalibrate_handler(self, enqueue=True):
        command = "recalibration"
        self._set_printOut("Calibration move requested.")

        if enqueue:
            self.command_queue.put(command)

        self.update()
        return command

    def _quit(self):
        return self._quit_handler()

    def _quit_handler(self, enqueue=True):
        if enqueue:
            self.command_queue.put("quit")

        self.close()
        return "quit"

    def _perception(self):
        return self._perception_handler()

    def _perception_handler(self, enqueue=True):
        return self._send_handler(
            self.get_current_user_command(),
            enqueue=enqueue,
        )

    # text_display_update
    def _set_printOut(self, print_out):
        self.state["print_out"] = "" if print_out is None else str(print_out)
        return self.state["print_out"]

    def _set_VLM_summary(self, vlm_summary):
        self.state["vlm_summary"] = "" if vlm_summary is None else str(vlm_summary)
        return self.state["vlm_summary"]

    def _set_action_seq(self, action_sequence):
        self.state["action_sequence"] = action_sequence or []
        return self.state["action_sequence"]

    def _set_user_command(self, user_command):
        self.state["user_command"] = "" if user_command is None else str(user_command)
        return self.state["user_command"]

    def get_current_user_command(self):
        return self.state.get("user_command", "")

    def _make_user_command(self, command):
        if command is None:
            return ""

        return " ".join(str(command).strip().split())

    def update(
        self,
        user_command    = None,
        vlm_summary     = None,
        print_out       = None,
        result_text     = None,
        action_sequence = None,
        action_result   = None,
        rgbd_data       = None,
        **kwargs,
    ):
        if user_command is not None:
            self._set_user_command(user_command)

        if vlm_summary is not None:
            self._set_VLM_summary(vlm_summary)

        if print_out is not None:
            self._set_printOut(print_out)

        if result_text is not None and print_out is None:
            self._set_printOut(result_text)

        if action_sequence is not None:
            self._set_action_seq(action_sequence)

        if action_result is not None:
            self.state["action_result"] = action_result

        if rgbd_data is not None:
            self._set_rgbd(rgbd_data)

        self.pyqt.call("set_state", state=self.state.copy())
        self._speak_result_text(
            result_text=result_text,
            action_result=action_result,
        )

        return {
            "state": self.state.copy(),
            "rgbd_state": self.rgbd_state.copy(),
        }

    # tts
    def _start_tts(self):
        if self.tts_running:
            return True

        self.tts_running = True
        self.tts_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True,
        )
        self.tts_thread.start()
        return True

    def _stop_tts(self):
        self.tts_running = False

        try:
            self.tts_queue.put_nowait(None)
        except Exception:
            pass

        if self.tts_thread is not None:
            self.tts_thread.join(timeout=1.0)
            self.tts_thread = None

        return True

    def _speak_result_text(self, result_text, action_result):
        if not self._should_speak_result_text(result_text, action_result):
            return False

        text = str(result_text).strip()

        if text == self.last_spoken_text:
            return False

        self.last_spoken_text = text

        try:
            while not self.tts_queue.empty():
                self.tts_queue.get_nowait()
        except Exception:
            pass

        try:
            self.tts_queue.put_nowait(text)
            return True
        except Exception:
            return False

    def _should_speak_result_text(self, result_text, action_result):
        if result_text is None:
            return False

        text = str(result_text).strip()

        if text == "":
            return False

        return action_result in ["ready", "success"]

    def _tts_loop(self):
        while self.tts_running:
            text = self.tts_queue.get()

            if text is None:
                break

            try:
                if self.voice_manager is None:
                    self.voice_manager = self._make_voice_manager()

                self.voice_manager.speak(text)

            except Exception as exc:
                print(f"[Interface TTS] failed: {exc}", flush=True)

    # rgbd_update
    def _set_rgbd(self, rgbd_data):
        if rgbd_data is None:
            return self.rgbd_state.copy()

        if isinstance(rgbd_data, tuple) and len(rgbd_data) >= 4:
            rgbd_data = {
                "frame": rgbd_data[0],
                "depth": rgbd_data[1],
                "yolo_robot": rgbd_data[2],
                "yolo_world": rgbd_data[3],
            }

        self._set_cam_rgb(rgbd_data.get("frame"))
        self._set_cam_d(rgbd_data.get("depth"))

        if self._is_inference_rgbd_data(rgbd_data):
            self._set_yolo_robot_result(rgbd_data.get("yolo_robot"))
            self._set_yolo_world_result(rgbd_data.get("yolo_world"))
            self._set_inference_rgbd(rgbd_data)

        self.pyqt.call("set_rgbd", rgbd_state=self.rgbd_state.copy())

        if self.rgbd_state["frame"] is None:
            return None

        return self.rgbd_state.copy()

    def _set_cam_rgb(self, frame):
        self.rgbd_state["frame"] = frame
        return frame

    def _set_cam_d(self, depth):
        self.rgbd_state["depth"] = depth
        return depth

    def _set_yolo_robot_result(self, yolo_robot):
        self.rgbd_state["yolo_robot"] = yolo_robot
        return yolo_robot

    def _set_yolo_world_result(self, yolo_world):
        self.rgbd_state["yolo_world"] = yolo_world
        return yolo_world

    def _set_inference_rgbd(self, rgbd_data):
        self.rgbd_state["inference_frame"] = rgbd_data.get("frame")
        self.rgbd_state["inference_yolo_robot"] = rgbd_data.get("yolo_robot")
        self.rgbd_state["inference_yolo_world"] = rgbd_data.get("yolo_world")
        self.rgbd_state["inference_vlm_summary"] = rgbd_data.get("vlm_summary", "")
        return self.rgbd_state.copy()

    def _is_inference_rgbd_data(self, rgbd_data):
        return any(
            key in rgbd_data
            for key in [
                "yolo_robot",
                "yolo_world",
                "vlm_summary",
                "vlm_objects",
            ]
        )

    # RobotApp compatibility
    def start_camera_stream(self, rgbd_cam):
        self.rgbd_cam = rgbd_cam
        if self.camera_running:
            return True

        self.camera_running = True
        self.camera_thread = threading.Thread(
            target=self._camera_stream_loop,
            daemon=True,
        )
        self.camera_thread.start()
        return True

    def stop_camera_stream(self):
        self.camera_running = False

        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None

        return True

    def _camera_stream_loop(self):
        while self.camera_running:
            try:
                rgbd_frame = None

                if self.rgbd_cam is not None:
                    if hasattr(self.rgbd_cam, "get_latest_rgbd_frame"):
                        rgbd_frame = self.rgbd_cam.get_latest_rgbd_frame()
                    elif hasattr(self.rgbd_cam, "get_latest_camera_data"):
                        rgbd_frame = self.rgbd_cam.get_latest_camera_data()

                if rgbd_frame is not None:
                    self._set_rgbd(rgbd_frame)

            except Exception as exc:
                print(f"[Interface] camera stream update failed: {exc}")

            time.sleep(0.1)

    def get_latest_camera_data(self):
        if self.rgbd_state["frame"] is None and self.rgbd_cam is not None:
            try:
                if hasattr(self.rgbd_cam, "get_latest_rgbd_frame"):
                    rgbd_frame = self.rgbd_cam.get_latest_rgbd_frame()
                else:
                    rgbd_frame = self.rgbd_cam.get_latest_camera_data()

                if rgbd_frame is not None:
                    self._set_rgbd(rgbd_frame)
            except Exception:
                pass

        if self.rgbd_state["frame"] is None:
            return None

        return self.rgbd_state.copy()

    def get_user_command(self, timeout=None):
        pyqt_command = self.pyqt.get_user_command(timeout=0)

        if pyqt_command is not None:
            if isinstance(pyqt_command, dict):
                return self._handle_pyqt_command(pyqt_command)

            if pyqt_command == "voice":
                return self._voice_handler()

            if pyqt_command == "recalibration":
                return self._recalibrate_handler(enqueue=False)

            if pyqt_command == "quit":
                return self._quit_handler(enqueue=False)

            if pyqt_command == "perception_inference":
                return self._perception_handler(enqueue=False)

            return self._send_handler(pyqt_command, enqueue=False)

        try:
            queued_command = self.command_queue.get(timeout=timeout)
        except queue.Empty:
            return None

        if isinstance(queued_command, dict):
            return self._handle_pyqt_command(queued_command)

        return queued_command

    def _handle_pyqt_command(self, pyqt_command):
        command_type = pyqt_command.get("type")

        if command_type == "send":
            command = self._make_user_command(pyqt_command.get("command", ""))

            if command == "":
                command = self.get_current_user_command()

            return self._send_handler(
                command,
                enqueue=False,
            )

        if command_type == "load_command":
            self._load_command_handler(pyqt_command.get("command", ""))
            return None

        if command_type == "voice":
            return self._voice_handler()

        if command_type == "recalibration":
            return self._recalibrate_handler(enqueue=False)

        if command_type == "quit":
            return self._quit_handler(enqueue=False)

        if command_type == "perception_inference":
            return self._perception_handler(enqueue=False)

        return None


def main():
    interface = Interface()
    interface.launch()
    started_at = time.time()
    duration = 60.0
    tick = 0

    try:
        while interface.running and time.time() - started_at < duration:
            tick += 1
            elapsed = time.time() - started_at
            command = f"interface test command {tick}"

            if tick % 15 == 0:
                interface._recalibrate()
            elif tick % 10 == 0:
                interface._voice()
            else:
                interface._send(command)

            interface.update(
                user_command=command,
                vlm_summary=f"test vlm summary tick={tick}",
                print_out=(
                    "interface_main functional test "
                    f"elapsed={elapsed:.1f}s / {duration:.0f}s"
                ),
                action_sequence=[
                    {
                        "name": "WAV",
                        "obj": None,
                    },
                    {
                        "name": "MOV",
                        "obj": "test_object",
                    },
                ],
                action_result="running",
                rgbd_data=_make_test_rgbd_data(tick),
            )

            print(
                "[INTERFACE TEST] "
                f"tick={tick} elapsed={elapsed:.1f}s command={command}"
            )
            time.sleep(1.0)

        interface.update(
            print_out="interface_main functional test complete",
            action_result="success",
        )
    finally:
        interface.close()


def _make_test_rgbd_data(tick):
    try:
        import numpy as np
    except ImportError:
        return None

    height = 480
    width = 640
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    depth = np.zeros((height, width), dtype=np.uint8)

    x = (tick * 17) % width
    y = (tick * 11) % height
    x1 = max(0, x - 40)
    y1 = max(0, y - 30)
    x2 = min(width - 1, x + 40)
    y2 = min(height - 1, y + 30)

    frame[:, :, 0] = (tick * 5) % 255
    frame[:, :, 1] = 80
    frame[:, :, 2] = 180
    frame[y1:y2, x1:x2, :] = [40, 220, 120]
    depth[:, :] = (tick * 4) % 255

    return {
        "frame": frame,
        "depth": depth,
        "yolo_robot": {
            "name": "end_effector",
            "u": x,
            "v": y,
            "d": 0.42,
            "conf": 0.9,
            "bbox": [x1, y1, x2, y2],
        },
        "yolo_world": [
            {
                "name": "test_object",
                "u": width - x,
                "v": height - y,
                "d": 0.55,
                "conf": 0.8,
                "bbox": [
                    max(0, width - x - 35),
                    max(0, height - y - 25),
                    min(width - 1, width - x + 35),
                    min(height - 1, height - y + 25),
                ],
            }
        ],
    }


if __name__ == "__main__":
    main()
