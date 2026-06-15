import multiprocessing as mp
import queue
from importlib.util import find_spec


class InterfacePyQt5Process:
    """
    PyQt5 UI process client.

    Importing this module does not import PyQt5. PyQt5 is imported only inside
    the child process started by launch().
    """

    def __init__(self, title="Robot Interface", enabled=True):
        self.title = title
        self.enabled = enabled
        self.request_queue = mp.Queue()
        self.command_queue = mp.Queue()
        self.process = None
        self.available = find_spec("PyQt5") is not None
        self._reported_process_exit = False

    def launch(self):
        if not self.enabled:
            return False

        if not self.available:
            print(
                "[InterfacePyQt5] PyQt5 is not installed. "
                "Install requirements or run: python3 -m pip install PyQt5",
                flush=True,
            )
            return False

        if self.process is not None and self.process.is_alive():
            return True

        self.process = mp.Process(
            target=_pyqt5_process_main,
            args=(self.title, self.request_queue, self.command_queue),
            daemon=True,
        )
        self.process.start()
        print(
            f"[InterfacePyQt5] process started pid={self.process.pid}",
            flush=True,
        )
        return True

    def close(self):
        self.call("close")

        if self.process is not None:
            self.process.join(timeout=1.0)

            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1.0)

            self.process = None

        self._close_queue(self.request_queue)
        self._close_queue(self.command_queue)

    def call(self, method, **payload):
        if not self.enabled:
            return False

        if not self.available:
            return False

        if self.process is None or not self.process.is_alive():
            self._report_process_exit_once()
            return False

        try:
            self.request_queue.put_nowait(
                {
                    "method": method,
                    "payload": payload,
                }
            )
            return True
        except Exception:
            return False

    def _close_queue(self, target_queue):
        try:
            target_queue.cancel_join_thread()
        except Exception:
            pass

        try:
            target_queue.close()
        except Exception:
            pass

    def get_user_command(self, timeout=None):
        try:
            return self.command_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _report_process_exit_once(self):
        if self.process is None:
            return

        if self.process.exitcode is None:
            return

        if self._reported_process_exit:
            return

        self._reported_process_exit = True
        print(
            "[InterfacePyQt5] process is not running "
            f"(exitcode={self.process.exitcode}).",
            flush=True,
        )


def _pyqt5_process_main(title, request_queue, command_queue):
    import signal

    signal.signal(signal.SIGINT, signal.SIG_IGN)

    pyqt = _load_pyqt5()
    cv2 = pyqt["cv2"]
    Canvas = pyqt["Canvas"]
    draw_detections = pyqt["draw_detections"]
    make_depth_view = pyqt["make_depth_view"]

    QApplication = pyqt["QApplication"]
    QGridLayout  = pyqt["QGridLayout"]
    QGroupBox    = pyqt["QGroupBox"]
    QHBoxLayout  = pyqt["QHBoxLayout"]
    QLabel       = pyqt["QLabel"]
    QLineEdit    = pyqt["QLineEdit"]
    QMainWindow  = pyqt["QMainWindow"]
    QPushButton  = pyqt["QPushButton"]
    QTextEdit    = pyqt["QTextEdit"]
    QVBoxLayout  = pyqt["QVBoxLayout"]
    QWidget      = pyqt["QWidget"]
    QImage       = pyqt["QImage"]
    QPixmap      = pyqt["QPixmap"]
    Qt           = pyqt["Qt"]
    QTimer       = pyqt["QTimer"]   
    plugin_path  = pyqt["plugin_path"]

    class RobotInterfaceWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(title)
            self.resize(1500, 840)

            self.canvas = Canvas()
            self.rgb_label       = ImageLabel("RGB")
            self.inference_label = ImageLabel("Inference")

            self.user_command_text    = make_readonly_text()
            self.vlm_summary_text     = make_readonly_text()
            self.action_sequence_text = make_readonly_text()
            self.print_out_text       = make_readonly_text()
            self.action_result_text   = make_readonly_text()

            self.status_label = QLabel("ready")
            self.status_label.setObjectName("statusLabel")

            self.command_input = QLineEdit()
            self.command_input.setPlaceholderText("Type a command")
            self.command_input.returnPressed.connect(self._send_text_command)

            send_button = QPushButton("Send")
            send_button.clicked.connect(self._send_text_command)

            voice_button = QPushButton("Voice")
            voice_button.clicked.connect(
                lambda: command_queue.put({"type": "voice"})
            )

            recalibration_button = QPushButton("Recalibration")
            recalibration_button.clicked.connect(
                lambda: command_queue.put({"type": "recalibration"})
            )

            perception_button = QPushButton("Inference")
            perception_button.clicked.connect(self._send_text_command)

            quit_button = QPushButton("Quit")
            quit_button.clicked.connect(
                lambda: command_queue.put({"type": "quit"})
            )

            command_layout = QHBoxLayout()
            command_layout.addWidget(self.command_input, 1)
            command_layout.addWidget(send_button)
            command_layout.addWidget(voice_button)
            command_layout.addWidget(recalibration_button)
            command_layout.addWidget(perception_button)
            command_layout.addWidget(quit_button)

            media_layout = QHBoxLayout()
            media_layout.addWidget(self.rgb_label, 1)
            media_layout.addWidget(self.inference_label, 1)

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

        def set_title(self, value):
            self.setWindowTitle(str(value))

        def set_state(self, state):
            self.user_command_text.setPlainText(str(state.get("user_command", "")))
            self.vlm_summary_text.setPlainText(str(state.get("vlm_summary", "")))
            self.action_sequence_text.setPlainText(str(state.get("action_sequence", [])))
            self.print_out_text.setPlainText(str(state.get("print_out", "")))
            self.action_result_text.setPlainText(str(state.get("action_result", "")))

        def set_rgbd(self, rgbd_state):
            frame = rgbd_state.get("frame")
            depth = rgbd_state.get("depth")
            yolo_robot = rgbd_state.get("yolo_robot")
            yolo_world = rgbd_state.get("yolo_world")
            inference_frame = rgbd_state.get("inference_frame")
            inference_yolo_robot = rgbd_state.get("inference_yolo_robot")
            inference_yolo_world = rgbd_state.get("inference_yolo_world")
            inference_vlm_summary = rgbd_state.get("inference_vlm_summary", "")

            if frame is None:
                return

            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            rgb_vis = self.canvas.rgb(frame)

            if inference_frame is not None:
                inference_vis = self.canvas.inference(
                    frame=inference_frame,
                    yolo_world=inference_yolo_world,
                    yolo_robot=inference_yolo_robot,
                )
            else:
                inference_vis = self.canvas.placeholder(
                    target_shape=rgb_vis.shape,
                    text="Press Inference or Send",
                )

            self.rgb_label.set_cv_image(rgb_vis)
            self.inference_label.set_cv_image(inference_vis)

        def show_status(self, text):
            self.status_label.setText(str(text))

        def closeEvent(self, event):
            command_queue.put({"type": "quit"})
            event.accept()

        def _send_text_command(self):
            command = self.command_input.text().strip()

            command_queue.put(
                {
                    "type": "send",
                    "command": command,
                }
            )

            if command != "":
                self.command_input.clear()

        def _load_text_command(self):
            command = self.command_input.text().strip()

            if command == "":
                return

            command_queue.put(
                {
                    "type": "load_command",
                    "command": command,
                }
            )
            self.command_input.clear()

    class ImageLabel(QLabel):
        def __init__(self, label):
            super().__init__(label)
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

            self.setPixmap(
                self._pixmap.scaled(
                    self.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def make_group(label, widget):
        group = QGroupBox(label)
        layout = QVBoxLayout()
        layout.addWidget(widget)
        group.setLayout(layout)
        return group

    def make_readonly_text():
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(86)
        text.setLineWrapMode(QTextEdit.WidgetWidth)
        return text

    QApplication.setLibraryPaths([plugin_path])
    app = QApplication.instance() or QApplication([])
    window = RobotInterfaceWindow()
    window.show()

    def drain_requests():
        while True:
            try:
                request = request_queue.get_nowait()
            except queue.Empty:
                break

            method = request.get("method")
            payload = request.get("payload", {})

            if method == "close":
                app.quit()
            elif method == "set_title":
                window.set_title(payload.get("title", "Robot Interface"))
            elif method == "set_state":
                window.set_state(payload.get("state", {}))
            elif method == "set_rgbd":
                window.set_rgbd(payload.get("rgbd_state", {}))
            elif method == "show_status":
                window.show_status(payload.get("text", ""))

    timer = QTimer()
    timer.timeout.connect(drain_requests)
    timer.start(30)

    app.exec_()


def _load_pyqt5():
    import os

    from PyQt5.QtCore import QLibraryInfo

    def configure_qt_plugin_path():
        pyqt_plugin_path = QLibraryInfo.location(QLibraryInfo.PluginsPath)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
            pyqt_plugin_path,
            "platforms",
        )
        os.environ["QT_PLUGIN_PATH"] = pyqt_plugin_path

    configure_qt_plugin_path()

    import cv2
    configure_qt_plugin_path()

    from PyQt5.QtCore import Qt, QTimer
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

    from .interface_utils import Canvas, draw_detections, make_depth_view
    configure_qt_plugin_path()

    return {
        "plugin_path"     : QLibraryInfo.location(QLibraryInfo.PluginsPath),
        "Canvas"          : Canvas,
        "cv2"             : cv2,
        "draw_detections" : draw_detections,
        "make_depth_view" : make_depth_view,
        "QApplication"    : QApplication,
        "QGridLayout"     : QGridLayout,
        "QGroupBox"       : QGroupBox,
        "QHBoxLayout"     : QHBoxLayout,
        "QLabel"          : QLabel,
        "QLineEdit"       : QLineEdit,
        "QMainWindow"     : QMainWindow,
        "QPushButton"     : QPushButton,
        "QTextEdit"       : QTextEdit,
        "QVBoxLayout"     : QVBoxLayout,
        "QWidget"         : QWidget,
        "QImage"          : QImage,
        "QPixmap"         : QPixmap,
        "Qt"              : Qt,
        "QTimer"          : QTimer,
    }


InterfacePyQt5 = InterfacePyQt5Process
