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


def draw_detections(frame, yolo_robot, yolo_world):
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
