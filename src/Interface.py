# src/Interface.py

import time
import threading
import multiprocessing as mp
from queue import Empty

import cv2
import numpy as np

from src.WhisperSTT import WhisperSTT


_stt = None


class Interface:
    def __init__(
        self,
        window_name="Robot Interface",
        show_window=True,
        camera_sleep=0.03,
    ):
        self.window_name = window_name
        self.show_window = show_window
        self.camera_sleep = camera_sleep

        self.latest_camera_data = None
        self.latest_lock = threading.Lock()

        self.camera_running = False
        self.camera_thread = None

        self.vis_queue = mp.Queue(maxsize=1)
        self.vis_stop_event = mp.Event()

        self.state = {
            "user_command": "",
            "vlm_summary": "",
            "print_out": "",
            "action_sequence": [],
            "action_result": "",
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
            target=self._camera_loop,
            args=(rgbd_cam,),
            daemon=True,
        )

        self.camera_thread.start()

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

    def get_user_command(self):
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
                    _stt = WhisperSTT()

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
        user_command=None,
        vlm_summary=None,
        print_out=None,
        action_sequence=None,
        action_result=None,
    ):
        if user_command is not None:
            self.state["user_command"] = user_command

        if vlm_summary is not None:
            self.state["vlm_summary"] = vlm_summary

        if print_out is not None:
            self.state["print_out"] = print_out

        if action_sequence is not None:
            self.state["action_sequence"] = action_sequence

        if action_result is not None:
            self.state["action_result"] = action_result

        with self.latest_lock:
            camera_data = self.latest_camera_data

        if camera_data is None:
            return

        packet = {
            "frame": camera_data["frame"],
            "depth": camera_data["depth"],
            "yolo_robot": camera_data["yolo_robot"],
            "yolo_world": camera_data["yolo_world"],
            "state": self.state.copy(),
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

def _draw_text_panel(frame, state):
    h, w = frame.shape[:2]

    panel_w = 520
    panel = np.zeros((h, panel_w, 3), dtype=np.uint8)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.45
    thickness = 1
    margin_x = 15
    max_text_w = panel_w - (margin_x * 2)
    line_h = 20
    section_gap = 12
    text_color = (255, 255, 255)
    title_color = (180, 220, 255)

    sections = [
        ("User command:", str(state.get("user_command", ""))),
        ("VLM summary:", str(state.get("vlm_summary", ""))),
        ("Action sequence:", str(state.get("action_sequence", []))),
        ("Print out:", str(state.get("print_out", ""))),
        ("Action result:", str(state.get("action_result", ""))),
    ]

    y = 26
    for title, value in sections:
        if y > h - line_h:
            break

        cv2.putText(
            panel,
            title,
            (margin_x, y),
            font,
            font_scale,
            title_color,
            thickness,
            cv2.LINE_AA,
        )
        y += line_h

        wrapped_lines = _wrap_text_for_cv2(
            value,
            max_text_w=max_text_w,
            font=font,
            font_scale=font_scale,
            thickness=thickness,
        )

        if len(wrapped_lines) == 0:
            wrapped_lines = [""]

        for line in wrapped_lines:
            if y > h - line_h:
                cv2.putText(
                    panel,
                    "...",
                    (margin_x, y),
                    font,
                    font_scale,
                    text_color,
                    thickness,
                    cv2.LINE_AA,
                )
                return panel

            cv2.putText(
                panel,
                line,
                (margin_x, y),
                font,
                font_scale,
                text_color,
                thickness,
                cv2.LINE_AA,
            )
            y += line_h

        y += section_gap

    return panel


def _wrap_text_for_cv2(text, max_text_w, font, font_scale, thickness):
    wrapped = []

    for raw_line in str(text).splitlines() or [""]:
        words = raw_line.split()

        if len(words) == 0:
            wrapped.append("")
            continue

        line = ""

        for word in words:
            candidate = word if line == "" else f"{line} {word}"

            if _cv2_text_width(candidate, font, font_scale, thickness) <= max_text_w:
                line = candidate
                continue

            if line != "":
                wrapped.append(line)

            if _cv2_text_width(word, font, font_scale, thickness) <= max_text_w:
                line = word
            else:
                pieces = _split_long_word_for_cv2(
                    word,
                    max_text_w=max_text_w,
                    font=font,
                    font_scale=font_scale,
                    thickness=thickness,
                )
                wrapped.extend(pieces[:-1])
                line = pieces[-1] if pieces else ""

        if line != "":
            wrapped.append(line)

    return wrapped


def _split_long_word_for_cv2(word, max_text_w, font, font_scale, thickness):
    pieces = []
    piece = ""

    for char in word:
        candidate = piece + char

        if _cv2_text_width(candidate, font, font_scale, thickness) <= max_text_w:
            piece = candidate
            continue

        if piece != "":
            pieces.append(piece)

        piece = char

    if piece != "":
        pieces.append(piece)

    return pieces


def _cv2_text_width(text, font, font_scale, thickness):
    size, _ = cv2.getTextSize(str(text), font, font_scale, thickness)
    return size[0]


def _draw_detections(frame, yolo_robot, yolo_world):
    vis = frame.copy()

    for obj in _iter_detection_objects(yolo_robot):
        if not isinstance(obj, dict):
            continue

        name = obj.get("name", "robot")
        u = int(obj.get("u", 0))
        v = int(obj.get("v", 0))
        d = obj.get("d", None)

        cv2.circle(vis, (u, v), 6, (0, 255, 0), -1)

        text = f"{name} ({u},{v})"
        if d is not None:
            text += f" d={d:.3f}"

        cv2.putText(
            vis,
            text,
            (u + 8, v - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    for obj in _iter_detection_objects(yolo_world):
        if not isinstance(obj, dict):
            continue

        name = obj.get("name", "object")
        u = int(obj.get("u", 0))
        v = int(obj.get("v", 0))
        d = obj.get("d", None)

        cv2.circle(vis, (u, v), 6, (0, 200, 255), -1)

        text = f"{name} ({u},{v})"
        if d is not None:
            text += f" d={d:.3f}"

        cv2.putText(
            vis,
            text,
            (u + 8, v + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 200, 255),
            2,
            cv2.LINE_AA,
        )

    return vis


def _make_depth_view(depth, target_shape):
    target_h, target_w = target_shape[:2]

    if depth is None:
        depth_view = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        cv2.putText(
            depth_view,
            "Depth: None",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return depth_view

    depth_arr = np.asarray(depth)

    if depth_arr.ndim == 3:
        depth_arr = cv2.cvtColor(depth_arr, cv2.COLOR_BGR2GRAY)

    depth_arr = depth_arr.astype(np.float32)

    valid = np.isfinite(depth_arr) & (depth_arr > 0)

    if np.any(valid):
        min_d = float(np.percentile(depth_arr[valid], 5))
        max_d = float(np.percentile(depth_arr[valid], 95))

        if max_d <= min_d:
            max_d = min_d + 1.0

        depth_norm = np.clip((depth_arr - min_d) / (max_d - min_d), 0.0, 1.0)
        depth_norm = (depth_norm * 255).astype(np.uint8)
        depth_view = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        depth_view[~valid] = (0, 0, 0)

        label = f"Depth {min_d:.3f}-{max_d:.3f}"
    else:
        depth_view = np.zeros(depth_arr.shape[:2] + (3,), dtype=np.uint8)
        label = "Depth: no valid data"

    if depth_view.shape[:2] != (target_h, target_w):
        depth_view = cv2.resize(depth_view, (target_w, target_h))

    cv2.putText(
        depth_view,
        label,
        (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    return depth_view


def _iter_detection_objects(detections):
    if detections is None:
        return []

    if isinstance(detections, dict):
        return [detections]

    if isinstance(detections, list):
        return detections

    return []


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

        vis_frame = _draw_detections(frame, yolo_robot, yolo_world)
        depth_view = _make_depth_view(depth, vis_frame.shape)
        text_panel = _draw_text_panel(vis_frame, state)

        display = np.hstack([vis_frame, depth_view, text_panel])

        cv2.imshow(window_name, display)

        key = cv2.waitKey(1)
        if key == ord("q"):
            break

    cv2.destroyWindow(window_name)

    
