# src/INTERFACE/interface_pyqt5.py
#
# Main GUI interface for the robot application.
# Use this implementation from RobotApp, where Interface is aliased to InterfacePyQt5.

import os
import queue
import threading
import time

try:
    from PyQt5.QtCore import QLibraryInfo

    _PYQT_PLUGIN_PATH = QLibraryInfo.location(QLibraryInfo.PluginsPath)
    _PYQT_PLATFORM_PLUGIN_PATH = os.path.join(_PYQT_PLUGIN_PATH, "platforms")

    def _configure_qt_plugin_path():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _PYQT_PLUGIN_PATH
        os.environ["QT_PLUGIN_PATH"] = _PYQT_PLUGIN_PATH

    _configure_qt_plugin_path()

    from PyQt5.QtCore import QObject, Qt, pyqtSignal
    from PyQt5.QtGui import QImage, QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise ImportError(
        "PyQt5 is required for src.interface_pyqt5. "
        "Install it with: python3 -m pip install PyQt5"
    ) from exc

import cv2

_configure_qt_plugin_path()

from .interface_utils import draw_detections, make_depth_view
from .VoiceManager import TTS



_stt = None


class _Bridge(QObject):
    camera_packet   = pyqtSignal(dict)
    state_packet    = pyqtSignal(dict)
    error           = pyqtSignal(str)
    close_requested = pyqtSignal()


class InterfacePyQt5:
    def __init__(
        self,
        window_name="Robot Interface",
        camera_sleep=0.03,
        tts_enabled=True,
    ):
        _configure_qt_plugin_path()

        self.app = QApplication.instance()

        if self.app is None:
            self.app = QApplication([])

        self.window_name = window_name
        self.camera_sleep = camera_sleep

        self.latest_camera_data = None
        self.latest_lock = threading.Lock()

        self.camera_running = False
        self.camera_thread = None

        self.command_queue = queue.Queue()
        self.tts_enabled = tts_enabled
        self.tts_queue = queue.Queue(maxsize=1)
        self.tts_running = False
        self.tts_thread = None
        self.tts = None
        self.last_spoken_result_text = ""
        self.bridge = _Bridge()

        self.state = {
            "user_command": "",
            "vlm_summary": "",
            "print_out": "",
            "action_sequence": [],
            "action_result": "",
        }

        self.window = RobotInterfaceWindow(
            window_name=self.window_name,
            submit_callback=self._submit_command,
            voice_callback=self._submit_voice_command,
            quit_callback=self._submit_quit,
        )

        self.bridge.camera_packet.connect(self.window.update_camera)
        self.bridge.state_packet.connect(self.window.update_state)
        self.bridge.error.connect(self.window.show_status)
        self.bridge.close_requested.connect(self._close_window)

        self.window.show()
        self.app.processEvents()

        if self.tts_enabled:
            self.start_tts()

    def start_camera_stream(self, rgbd_cam):
        self.camera_running = True

        self.camera_thread = threading.Thread(
            target=self._camera_loop,
            args=(rgbd_cam,),
            daemon=True,
        )
        self.camera_thread.start()

    def stop_camera_stream(self):
        self.camera_running = False

        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None

    def start_tts(self):
        if self.tts_running:
            return

        self.tts_running = True
        self.tts_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True,
        )
        self.tts_thread.start()

    def stop_tts(self):
        self.tts_running = False

        try:
            while not self.tts_queue.empty():
                self.tts_queue.get_nowait()

            self.tts_queue.put_nowait(None)
        except queue.Full:
            pass

        if self.tts_thread is not None:
            self.tts_thread.join(timeout=1.0)
            self.tts_thread = None

    def _tts_loop(self):
        try:
            self.tts = TTS()
        except Exception as e:
            self.bridge.error.emit(f"TTS init failed: {e}")
            self.tts_running = False
            return

        while self.tts_running:
            text = self.tts_queue.get()

            if text is None:
                break

            try:
                self.tts.speak(text)
            except Exception as e:
                self.bridge.error.emit(f"TTS failed: {e}")

    def _camera_loop(self, rgbd_cam):
        while self.camera_running:
            try:
                frame, depth, yolo_robot, yolo_world = rgbd_cam.get_frame()

                camera_data = {
                    "frame": frame,
                    "depth": depth,
                    "yolo_robot": yolo_robot,
                    "yolo_world": yolo_world,
                }

                with self.latest_lock:
                    self.latest_camera_data = camera_data

                packet = {
                    "frame": frame,
                    "depth": depth,
                    "yolo_robot": yolo_robot,
                    "yolo_world": yolo_world,
                    "state": self.state.copy(),
                }
                self.bridge.camera_packet.emit(packet)

            except Exception as e:
                self.bridge.error.emit(f"camera loop error: {e}")
                time.sleep(0.2)

            time.sleep(self.camera_sleep)

    def get_latest_camera_data(self):
        with self.latest_lock:
            if self.latest_camera_data is None:
                return None

            return self.latest_camera_data.copy()

    def get_user_command(self, timeout=None):
        try:
            return self.command_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def update(
        self,
        user_command=None,
        vlm_summary=None,
        print_out=None,
        result_text=None,
        action_sequence=None,
        action_result=None,
    ):
        if user_command is not None:
            self.state["user_command"] = user_command

        if vlm_summary is not None:
            self.state["vlm_summary"] = vlm_summary

        if print_out is not None:
            self.state["print_out"] = print_out

        if result_text is not None:
            self._speak_result_text(result_text)

        if action_sequence is not None:
            self.state["action_sequence"] = action_sequence

        if action_result is not None:
            self.state["action_result"] = action_result

        self.bridge.state_packet.emit(self.state.copy())

    def run(self):
        return self.app.exec_()

    def close(self):
        self.stop_camera_stream()
        self.stop_tts()
        self.bridge.close_requested.emit()

    def _speak_result_text(self, result_text):
        if not self.tts_enabled:
            return

        text = str(result_text).strip()

        if text == "" or text == self.last_spoken_result_text:
            return

        self.last_spoken_result_text = text

        try:
            while not self.tts_queue.empty():
                self.tts_queue.get_nowait()
        except Exception:
            pass

        try:
            self.tts_queue.put_nowait(text)
        except queue.Full:
            pass

    def _close_window(self):
        if self.window is not None and self.window.isVisible():
            self.window.close()

        self.app.quit()

    def _submit_command(self, command):
        command = str(command).strip()

        if command == "":
            return

        self.command_queue.put(command)

    def _submit_voice_command(self):
        global _stt

        try:
            if _stt is None:
                try:
                    from .VoiceManager import WhisperSTT
                    _stt = WhisperSTT()
                except Exception as e:
                    self.bridge.error.emit(f"voice mode unavailable: {e}")
                    return

            command = _stt.listen()

            if command is None:
                self.bridge.error.emit("voice command is empty")
                return

            command = command.strip()
            self.window.set_command_text(command)
            self.command_queue.put(command)

        except Exception as e:
            self.bridge.error.emit(f"voice command failed: {e}")

    def _submit_quit(self):
        self.command_queue.put("quit")


class RobotInterfaceWindow(QMainWindow):
    def __init__(self, window_name, submit_callback, voice_callback, quit_callback):
        super().__init__()

        self.submit_callback = submit_callback
        self.voice_callback  = voice_callback
        self.quit_callback   = quit_callback

        self.setWindowTitle(window_name)
        self.resize(1500, 840)

        self.rgb_label   = ImageLabel("RGB")
        self.depth_label = ImageLabel("Depth")

        self.user_command_text    = make_readonly_text()
        self.vlm_summary_text     = make_readonly_text()
        self.action_sequence_text = make_readonly_text()
        self.print_out_text       = make_readonly_text()
        self.action_result_text   = make_readonly_text()

        self.status_label = QLabel("ready")
        self.status_label.setObjectName("statusLabel")

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Type a command, e.g. move to bottle")
        self.command_input.returnPressed.connect(self._send_text_command)

        send_button = QPushButton("Send")
        send_button.clicked.connect(self._send_text_command)

        voice_button = QPushButton("Voice")
        voice_button.clicked.connect(self.voice_callback)

        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(self.quit_callback)

        recalibration_button = QPushButton("Recalibration")
        recalibration_button.clicked.connect(
            lambda: self._send_shortcut("recalibration")
        )

        command_layout = QHBoxLayout()
        command_layout.addWidget(self.command_input, 1)
        command_layout.addWidget(send_button)
        command_layout.addWidget(voice_button)
        command_layout.addWidget(recalibration_button)
        command_layout.addWidget(quit_button)

        media_layout = QHBoxLayout()
        media_layout.addWidget(self.rgb_label, 1)
        media_layout.addWidget(self.depth_label, 1)

        info_layout = QGridLayout()
        info_layout.addWidget(make_group("User Command", self.user_command_text), 0, 0)
        info_layout.addWidget(make_group("VLM Summary", self.vlm_summary_text), 0, 1)
        info_layout.addWidget(make_group("Action Sequence", self.action_sequence_text), 1, 0)
        info_layout.addWidget(make_group("Print Out", self.print_out_text), 1, 1)
        info_layout.addWidget(make_group("Action Result", self.action_result_text), 2, 0, 1, 2)

        root_layout = QVBoxLayout()
        root_layout.addLayout(media_layout, 5)
        root_layout.addLayout(info_layout, 3)
        root_layout.addLayout(command_layout)
        root_layout.addWidget(self.status_label)

        root = QWidget()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        self.setStyleSheet(
            """
            QMainWindow {
                background: #111418;
            }
            QLabel {
                color: #e8edf2;
                font-size: 13px;
            }
            QGroupBox {
                color: #a9c7e8;
                border: 1px solid #343b44;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: 600;
            }
            QTextEdit, QLineEdit {
                background: #0b0d10;
                color: #f4f7fb;
                border: 1px solid #343b44;
                border-radius: 4px;
                padding: 6px;
                selection-background-color: #2b6cb0;
                font-size: 13px;
            }
            QPushButton {
                background: #26313d;
                color: #f4f7fb;
                border: 1px solid #465564;
                border-radius: 5px;
                padding: 7px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #324153;
            }
            QPushButton:pressed {
                background: #1f2933;
            }
            #statusLabel {
                color: #9fb3c8;
                padding: 3px;
            }
            """
        )

    def update_camera(self, packet):
        frame = packet.get("frame")
        depth = packet.get("depth")
        yolo_robot = packet.get("yolo_robot")
        yolo_world = packet.get("yolo_world")
        state = packet.get("state", {})

        if frame is None:
            return

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        rgb_vis   = draw_detections(frame, yolo_robot, yolo_world)
        depth_vis = make_depth_view(depth, rgb_vis.shape)

        self.rgb_label.set_cv_image(rgb_vis)
        self.depth_label.set_cv_image(depth_vis)
        self.update_state(state)

    def update_state(self, state):
        self.user_command_text    .setPlainText(  str(  state.get(  "user_command", ""    )  )  )
        self.vlm_summary_text     .setPlainText(  str(  state.get(  "vlm_summary", ""     )  )  )
        self.action_sequence_text .setPlainText(  str(  state.get(  "action_sequence", [] )  )  )
        self.print_out_text       .setPlainText(  str(  state.get(  "print_out", ""       )  )  )
        self.action_result_text   .setPlainText(  str(  state.get(  "action_result", ""   )  )  )

    def show_status(self, text):
        self.status_label.setText(str(text))

    def set_command_text(self, text):
        self.command_input.setText(str(text))

    def closeEvent(self, event):
        self.quit_callback()
        event.accept()

    def _send_text_command(self):
        command = self.command_input.text().strip()

        if command == "":
            return

        self.submit_callback(command)
        self.command_input.clear()

    def _send_shortcut(self, command):
        self.command_input.setText(command)
        self.submit_callback(command)


class ImageLabel(QLabel):
    def __init__(self, title):
        super().__init__(title)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setStyleSheet(
            "background: #050607; border: 1px solid #343b44; border-radius: 6px;"
        )
        self._pixmap = None

    def set_cv_image(self, frame):
        if frame is None:
            return

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        bytes_per_line = 3 * w

        image = QImage(
            rgb.data,
            w,
            h,
            bytes_per_line,
            QImage.Format_RGB888,
        ).copy()

        self._pixmap = QPixmap.fromImage(image)
        self._set_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_scaled_pixmap()

    def _set_scaled_pixmap(self):
        if self._pixmap is None:
            return

        scaled = self._pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)


def make_group(title, widget):
    group  = QGroupBox(title)
    layout = QVBoxLayout()
    layout.addWidget(widget)
    group .setLayout(layout)
    return group


def make_readonly_text():
    text = QTextEdit()
    text.setReadOnly(True)
    text.setMinimumHeight(86)
    text.setLineWrapMode(QTextEdit.WidgetWidth)
    return text

Interface = InterfacePyQt5
