import cv2
import numpy as np

# Shared visualization helpers for interface modules.
# - draw_detections: overlay object detections on RGB frames
# - make_depth_view: render a depth map as a colored image
# - draw_text_panel: render state text for OpenCV-based displays

def _cv2_text_width(text, font, font_scale, thickness):
    size, _ = cv2.getTextSize(str(text), font, font_scale, thickness)
    return size[0]


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


def draw_text_panel(frame, state):
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


def _iter_detection_objects(detections):
    if detections is None:
        return []

    if isinstance(detections, dict):
        return [detections]

    if isinstance(detections, list):
        return detections

    return []


class Canvas:
    def __init__(self):
        pass

    def rgb(self, frame):
        if frame is None:
            return None

        return frame.copy()

    def inference(self, frame, yolo_world=None, yolo_robot=None, vlm_summary=""):
        if frame is None:
            return None

        canvas = frame.copy()
        canvas = draw_robot_markers(canvas, yolo_robot)
        canvas = draw_yolo_world_boxes(canvas, yolo_world)

        return canvas

    def placeholder(self, target_shape, text="Inference image"):
        target_h, target_w = target_shape[:2]
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        self._draw_caption(canvas, text)
        return canvas

    def _draw_caption(self, canvas, text):
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        margin = 10
        max_w = canvas.shape[1] - margin * 2
        lines = _wrap_text_for_cv2(
            text=text,
            max_text_w=max_w,
            font=font,
            font_scale=font_scale,
            thickness=thickness,
        )
        lines = lines[:3]

        if not lines:
            return

        panel_h = 24 + 20 * len(lines)
        overlay = canvas.copy()
        cv2.rectangle(
            overlay,
            (0, 0),
            (canvas.shape[1], panel_h),
            (0, 0, 0),
            -1,
        )
        cv2.addWeighted(overlay, 0.55, canvas, 0.45, 0, canvas)

        y = 24
        for line in lines:
            cv2.putText(
                canvas,
                line,
                (margin, y),
                font,
                font_scale,
                (245, 248, 252),
                thickness,
                cv2.LINE_AA,
            )
            y += 20


def draw_yolo_world_boxes(frame, yolo_world):
    vis = frame.copy()

    for obj in _iter_detection_objects(yolo_world):
        if not isinstance(obj, dict):
            continue

        name = obj.get("name", "object")
        u = int(obj.get("u", 0))
        v = int(obj.get("v", 0))
        d = obj.get("d", None)
        bbox = _make_bbox(obj, vis.shape)

        _draw_object_marker(
            vis=vis,
            name=name,
            u=u,
            v=v,
            d=d,
            bbox=bbox,
            color=(0, 220, 255),
            text_offset=(8, 20),
            thickness=3,
        )

    return vis


def draw_robot_markers(frame, yolo_robot):
    vis = frame.copy()

    for obj in _iter_detection_objects(yolo_robot):
        if not isinstance(obj, dict):
            continue

        name = obj.get("name", "robot")
        u = int(obj.get("u", 0))
        v = int(obj.get("v", 0))
        d = obj.get("d", None)
        bbox = obj.get("bbox")

        _draw_object_marker(
            vis=vis,
            name=name,
            u=u,
            v=v,
            d=d,
            bbox=bbox,
            color=(0, 255, 0),
            text_offset=(8, -8),
            thickness=2,
        )

    return vis


def draw_detections(frame, yolo_robot, yolo_world):
    vis = draw_robot_markers(frame, yolo_robot)
    vis = draw_yolo_world_boxes(vis, yolo_world)
    return vis


def _make_bbox(obj, shape):
    bbox = obj.get("bbox")

    if bbox is not None and len(bbox) >= 4:
        return bbox

    h, w = shape[:2]
    u = int(obj.get("u", w // 2))
    v = int(obj.get("v", h // 2))
    half_w = max(20, w // 20)
    half_h = max(20, h // 20)
    return [
        max(0, u - half_w),
        max(0, v - half_h),
        min(w - 1, u + half_w),
        min(h - 1, v + half_h),
    ]


def _draw_object_marker(
    vis,
    name,
    u,
    v,
    d,
    bbox,
    color,
    text_offset,
    thickness=2,
):
    if bbox is not None and len(bbox) >= 4:
        x1, y1, x2, y2 = [int(float(value)) for value in bbox[:4]]
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, thickness)
        text_origin = (x1, max(18, y1 - 8))
    else:
        cv2.circle(vis, (u, v), 6, color, -1)
        text_origin = (u + text_offset[0], v + text_offset[1])

    text = f"{name} ({u},{v})"
    if d is not None:
        try:
            text += f" d={float(d):.3f}"
        except Exception:
            text += f" d={d}"

    cv2.putText(
        vis,
        text,
        text_origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        max(1, thickness),
        cv2.LINE_AA,
    )


def make_depth_view(depth, target_shape):
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
