import argparse
import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.RGBD_CAM import RGBD
from src.ROBOT    import ROBOT
from src.CALIBRATION.teleoperation_recorder import load_teleoperation_poses

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


def calib_log(message):
    if tqdm is not None:
        tqdm.write(str(message))
        return

    print(message)


def main():
    args = parse_args()

    robot = ROBOT()
    rgbd_cam = RGBD()

    try:
        csv_path = collect_calibration_samples(
            robot               = robot,
            rgbd_cam            = rgbd_cam,
            output_dir          = args.output_dir,
            cycles              = args.cycles,
            move_duration       = args.move_duration,
            move_duration_scale = args.move_duration_scale,
            settle_time         = args.settle_time,
            warmup_frames       = args.warmup_frames,
            sample_hz           = args.sample_hz,
            max_samples_per_pose= args.max_samples_per_pose,
            max_attempts_per_pose=args.max_attempts_per_pose,
            min_uv_distance     = args.min_uv_distance,
            sample_while_moving = args.sample_while_moving,
            min_robot_conf      = args.min_robot_conf,
            require_valid_depth = not args.allow_empty_depth,
            save_rejected_every = args.save_rejected_every,
            return_home         = args.return_home,
            calibration_poses_path=args.calibration_poses_path,
        )
    finally:
        rgbd_cam.close()

    calib_log(f"[CALIB] dataset saved: {csv_path}")


def collect_calibration_samples(
    robot,
    rgbd_cam,
    output_dir            = "src/CALIBRATION/robot_camera_calibration_samples",
    cycles                = 1,
    move_duration         = 1.5,
    settle_time           = 1.0,
    warmup_frames         = 3,
    sample_hz             = 10.0,
    max_samples_per_pose  = None,
    max_attempts_per_pose = None,
    min_uv_distance       = 0.0,
    sample_while_moving   = True,
    min_robot_conf        = 0.45,
    require_valid_depth   = True,
    save_rejected_every   = 20,
    return_home           = False,
    capture_callback      = None,
    calibration_poses     = None,
    calibration_poses_path= None,
    move_duration_scale   = 1.0,
):
    sample_hz             = max(0.1, float(sample_hz))
    move_duration_scale   = max(0.05, float(move_duration_scale))
    save_rejected_every   = max(0, int(save_rejected_every))
    if max_samples_per_pose is not None:
        max_samples_per_pose = max(1, int(max_samples_per_pose))
    if max_attempts_per_pose is not None:
        max_attempts_per_pose = max(1, int(max_attempts_per_pose))
    min_uv_distance       = max(0.0, float(min_uv_distance))

    out_dir = Path(output_dir) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir = out_dir / "rejected"
    rejected_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "robot_camera_calibration_samples.csv"
    fieldnames = [
        "sample_idx",
        "cycle_idx",
        "pose_idx",
        "pose_name",
        "j1",
        "j2",
        "j3",
        "j4",
        "gripper",
        "robot_u",
        "robot_v",
        "robot_d",
        "robot_conf",
        "robot_bbox",
        "image_path",
    ]
    
    sample_idx         = 0
    attempt_idx        = 0
    accepted_count     = 0
    rejected_count     = 0
    skipped_pose_count = 0
    duplicate_count    = 0
    accepted_uvds      = []
    period = 1.0 / sample_hz

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        poses = resolve_calibration_poses(
            robot=robot,
            calibration_poses=calibration_poses,
            calibration_poses_path=calibration_poses_path,
        )

        progress = make_calibration_progress(cycles=cycles, pose_count=len(poses))

        try:
            for cycle_idx in range(1, cycles + 1):
                for pose_idx, pose in enumerate(poses, start=1):
                    pose_name = pose["name"]

                    progress_set_description(
                        progress,
                        f"cycle={cycle_idx}/{cycles} pose={pose_idx}/{len(poses)}",
                    )
                    progress_set_postfix(
                        progress,
                        accepted=accepted_count,
                        rejected=rejected_count,
                        duplicates=duplicate_count,
                        skipped=skipped_pose_count,
                    )

                    calib_log(f"[CALIB] cycle={cycle_idx} pose={pose_idx} {pose_name}")

                    if not is_reachable_pose(robot, pose):
                        skipped_pose_count += 1
                        calib_log(f"[CALIB] skip unreachable/invalid pose: {pose_name}")
                        progress_update(progress)
                        continue

                    move_result = {"ok": None}
                    pose_move_duration = (
                        float(pose.get("duration", move_duration))
                        * move_duration_scale
                    )
                    move_thread = threading.Thread(
                        target=_move_to_calibration_pose_worker,
                        args=(robot, pose, pose_move_duration, move_result),
                        daemon=True,
                    )
                    move_thread.start()

                    accepted_for_pose = 0
                    attempts_for_pose = 0
                    pose_start_time = time.time()
                    move_deadline = pose_start_time + pose_move_duration
                    capture_start = (
                        pose_start_time
                        if sample_while_moving
                        else move_deadline + settle_time
                    )
                    capture_until = move_deadline + settle_time + (
                        (max_attempts_per_pose * period)
                        if max_attempts_per_pose is not None
                        else 0.0
                    )
                    next_sample_time = pose_start_time

                    while move_thread.is_alive() or time.time() < capture_until:
                        if move_result["ok"] is False and not move_thread.is_alive():
                            calib_log(
                                "[CALIB] stopping samples for failed move: "
                                f"{pose_name}"
                            )
                            break

                        now = time.time()

                        if now < capture_start:
                            time.sleep(min(0.02, capture_start - now))
                            continue

                        if not sample_while_moving and move_thread.is_alive():
                            time.sleep(0.02)
                            continue

                        if (
                            max_samples_per_pose is not None
                            and accepted_for_pose >= max_samples_per_pose
                        ):
                            break

                        if now < next_sample_time:
                            time.sleep(min(0.01, next_sample_time - now))
                            continue

                        next_sample_time += period
                        attempt_idx += 1
                        attempts_for_pose += 1

                        if (
                            max_attempts_per_pose is not None
                            and attempts_for_pose > max_attempts_per_pose
                        ):
                            break

                        if capture_callback is None:
                            frame, depth, yolo_robot = capture_robot_detection(
                                rgbd_cam=rgbd_cam,
                                warmup_frames=warmup_frames,
                            )
                        else:
                            frame, depth, yolo_robot = capture_callback()

                        valid, validation_error = validate_robot_detection(
                            yolo_robot=yolo_robot,
                            min_robot_conf=min_robot_conf,
                            require_valid_depth=require_valid_depth,
                        )

                        if not valid:
                            rejected_count += 1
                            progress_set_postfix(
                                progress,
                                accepted=accepted_count,
                                rejected=rejected_count,
                                duplicates=duplicate_count,
                                skipped=skipped_pose_count,
                            )

                            if (
                                save_rejected_every > 0
                                and rejected_count % save_rejected_every == 0
                            ):
                                save_rejected_image(
                                    out_dir     = rejected_dir,
                                    attempt_idx = attempt_idx,
                                    cycle_idx   = cycle_idx,
                                    pose_idx    = pose_idx,
                                    pose_name   = pose_name,
                                    frame       = frame,
                                    yolo_robot  = yolo_robot,
                                    reason      = validation_error,
                                )

                            calib_log(
                                "[CALIB] rejected "
                                f"pose={pose_name} frame={attempt_idx}: "
                                f"{validation_error}"
                            )
                            continue

                        if is_duplicate_uvd(
                            yolo_robot=yolo_robot,
                            accepted_uvds=accepted_uvds,
                            min_uv_distance=min_uv_distance,
                        ):
                            duplicate_count += 1
                            progress_set_postfix(
                                progress,
                                accepted=accepted_count,
                                rejected=rejected_count,
                                duplicates=duplicate_count,
                                skipped=skipped_pose_count,
                            )
                            calib_log(
                                "[CALIB] duplicate "
                                f"pose={pose_name} frame={attempt_idx}: "
                                f"u={yolo_robot.get('u')} v={yolo_robot.get('v')}"
                            )
                            continue

                        actual_joints = robot.get_pose()
                        sample_idx += 1
                        accepted_for_pose += 1
                        accepted_count += 1
                        progress_set_postfix(
                            progress,
                            accepted=accepted_count,
                            rejected=rejected_count,
                            duplicates=duplicate_count,
                            skipped=skipped_pose_count,
                        )

                        image_path = save_sample_image(
                            out_dir    = out_dir,
                            sample_idx = sample_idx,
                            cycle_idx  = cycle_idx,
                            pose_idx   = pose_idx,
                            pose_name  = pose_name,
                            frame      = frame,
                            yolo_robot = yolo_robot,
                        )

                        row = make_csv_row(
                            sample_idx = sample_idx,
                            cycle_idx  = cycle_idx,
                            pose_idx   = pose_idx,
                            pose_name  = pose_name,
                            joints     = actual_joints,
                            yolo_robot = yolo_robot,
                            image_path = image_path,
                        )
                        writer.writerow(row)
                        csv_file.flush()
                        accepted_uvds.append(
                            (
                                float(row["robot_u"]),
                                float(row["robot_v"]),
                                parse_float(row["robot_d"]),
                            )
                        )

                        elapsed = time.time() - pose_start_time
                        calib_log(
                            "[CALIB] saved "
                            f"t={elapsed:.2f}s "
                            f"u={row['robot_u']} v={row['robot_v']} d={row['robot_d']} "
                            f"conf={row['robot_conf']} "
                            f"actual_joints={actual_joints}"
                        )

                    move_thread.join(timeout=0.1)

                    if move_result["ok"] is False:
                        calib_log(f"[CALIB] move failed: {pose_name}")

                    if accepted_for_pose == 0:
                        calib_log(f"[CALIB] no valid sample for pose: {pose_name}")

                    progress_update(progress)
                    progress_set_postfix(
                        progress,
                        accepted=accepted_count,
                        rejected=rejected_count,
                        duplicates=duplicate_count,
                        skipped=skipped_pose_count,
                    )
        finally:
            progress_close(progress)

        if return_home:
            robot.move_to_base_pose(duration=move_duration * move_duration_scale)

    calib_log(
        "[CALIB] summary "
        f"accepted={accepted_count} rejected={rejected_count} "
        f"duplicates={duplicate_count} skipped_poses={skipped_pose_count} "
        f"csv={csv_path}"
    )
    write_calibration_report(
        csv_path       = csv_path,
        out_dir        = out_dir,
        accepted_count = accepted_count,
        rejected_count = rejected_count,
    )

    return csv_path


def make_calibration_progress(cycles, pose_count):
    total = max(0, int(cycles) * int(pose_count))

    if tqdm is None:
        calib_log(f"[CALIB] progress: 0/{total} poses")
        return {
            "total": total,
            "current": 0,
            "description": "calibration",
        }

    return tqdm(
        total=total,
        desc="calibration",
        unit="pose",
        dynamic_ncols=True,
    )


def progress_set_description(progress, description):
    if progress is None:
        return

    if hasattr(progress, "set_description"):
        progress.set_description(description)
        return

    progress["description"] = description


def progress_set_postfix(progress, **kwargs):
    if progress is None:
        return

    if hasattr(progress, "set_postfix"):
        progress.set_postfix(kwargs)


def progress_update(progress, amount=1):
    if progress is None:
        return

    if hasattr(progress, "update"):
        progress.update(amount)
        return

    progress["current"] += amount
    calib_log(
        "[CALIB] progress: "
        f"{progress['current']}/{progress['total']} poses "
        f"({progress.get('description', 'calibration')})"
    )


def progress_close(progress):
    if progress is None:
        return

    if hasattr(progress, "close"):
        progress.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="src/CALIBRATION/robot_camera_calibration_samples")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--move-duration", type=float, default=1.5)
    parser.add_argument(
        "--move-duration-scale",
        type=float,
        default=1.0,
        help="Scale all calibration move durations. Values below 1.0 move faster.",
    )
    parser.add_argument("--settle-time", type=float, default=1.0)
    parser.add_argument("--warmup-frames", type=int, default=3)
    parser.add_argument("--sample-hz", type=float, default=10.0)
    parser.add_argument("--max-samples-per-pose", type=int, default=2)
    parser.add_argument("--max-attempts-per-pose", type=int, default=8)
    parser.add_argument("--min-uv-distance", type=float, default=24.0)
    parser.add_argument("--sample-while-moving", action="store_true")
    parser.add_argument("--min-robot-conf", type=float, default=0.45)
    parser.add_argument("--save-rejected-every", type=int, default=20)
    parser.add_argument("--allow-empty-depth", action="store_true")
    parser.add_argument("--return-home", action="store_true")
    parser.add_argument(
        "--calibration-poses-path",
        default=None,
        help="Use teleoperation-recorded calibration poses from this JSON file.",
    )
    return parser.parse_args()


def resolve_calibration_poses(
    robot,
    calibration_poses=None,
    calibration_poses_path=None,
):
    if calibration_poses is not None:
        poses = list(calibration_poses)
    elif calibration_poses_path is not None:
        poses = load_teleoperation_poses(calibration_poses_path)
    else:
        poses = robot.get_calibration_poses()

    normalized = []

    for index, pose in enumerate(poses, start=1):
        if isinstance(pose, dict):
            joints = pose.get("joints")
            name = pose.get("name", f"calib_{index:04d}")
            duration = pose.get("duration")
        else:
            joints = pose
            name = f"calib_{index:04d}"
            duration = None

        if joints is None or len(joints) != 5:
            raise ValueError(f"invalid calibration pose at index {index}: {pose}")

        item = {
            "name": str(name),
            "joints": tuple(float(value) for value in joints),
        }

        if duration is not None:
            item["duration"] = float(duration)

        normalized.append(item)

    if len(normalized) == 0:
        raise ValueError("calibration pose sequence is empty")

    return normalized


def capture_robot_detection(rgbd_cam, warmup_frames):
    frame = None
    depth = None
    yolo_robot = None

    for _ in range(max(1, warmup_frames)):
        frame, depth, yolo_robot, _ = rgbd_cam.get_frame()

    return frame, depth, yolo_robot


def _move_to_calibration_pose_worker(robot, pose, move_duration, result):
    try:
        result["ok"] = robot.move_to_calibration_pose(
            pose,
            duration=move_duration,
        )
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)


def is_reachable_pose(robot, pose):
    joints = pose.get("joints") if isinstance(pose, dict) else pose

    if joints is None or len(joints) != 5:
        return False

    try:
        values = [float(value) for value in joints]
    except Exception:
        return False

    if hasattr(robot, "_validate_pose"):
        try:
            return bool(robot._validate_pose(values))
        except Exception:
            return False

    return True


def is_duplicate_uvd(yolo_robot, accepted_uvds, min_uv_distance):
    if min_uv_distance <= 0:
        return False

    if not accepted_uvds:
        return False

    u = parse_float(yolo_robot.get("u"))
    v = parse_float(yolo_robot.get("v"))

    if u is None or v is None:
        return False

    for prev_u, prev_v, _prev_d in accepted_uvds:
        du = u - prev_u
        dv = v - prev_v

        if (du ** 2 + dv ** 2) ** 0.5 < min_uv_distance:
            return True

    return False


def validate_robot_detection(yolo_robot, min_robot_conf=0.45, require_valid_depth=True):
    if not isinstance(yolo_robot, dict):
        return False, "robot detection is None"

    u = yolo_robot.get("u")
    v = yolo_robot.get("v")
    d = yolo_robot.get("d")
    conf = yolo_robot.get("conf")
    bbox = yolo_robot.get("bbox")

    if u is None or v is None:
        return False, "robot u/v is None"

    if bbox is None:
        return False, "robot bbox is None"

    try:
        conf = float(conf)
    except Exception:
        return False, "robot conf is invalid"

    if conf < min_robot_conf:
        return False, f"robot conf too low: {conf:.3f} < {min_robot_conf:.3f}"

    if require_valid_depth:
        try:
            d = float(d)
        except Exception:
            return False, "robot depth is invalid"

        if d <= 0:
            return False, f"robot depth is not positive: {d}"

    return True, ""


def save_rejected_image(
    out_dir,
    attempt_idx,
    cycle_idx,
    pose_idx,
    pose_name,
    frame,
    yolo_robot,
    reason,
):
    if frame is None:
        return

    image_name = (
        f"rejected_{attempt_idx:04d}_cycle_{cycle_idx:02d}_"
        f"pose_{pose_idx:02d}_{pose_name}.jpg"
    )

    image_path = out_dir / image_name
    vis = draw_robot_detection(frame, yolo_robot)

    cv2.putText(
        vis,
        f"rejected: {reason}"[:100],
        (15, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.imwrite(str(image_path), vis)


def save_sample_image(
    out_dir,
    sample_idx,
    cycle_idx,
    pose_idx,
    pose_name,
    frame,
    yolo_robot,
):
    image_name = (
        f"sample_{sample_idx:04d}_cycle_{cycle_idx:02d}_"
        f"pose_{pose_idx:02d}_{pose_name}.jpg"
    )
    image_path = out_dir / image_name
    vis = draw_robot_detection(frame, yolo_robot)
    cv2.imwrite(str(image_path), vis)
    return image_path


def make_csv_row(sample_idx, cycle_idx, pose_idx, pose_name, joints, yolo_robot, image_path):
    row = {
        "sample_idx": sample_idx,
        "cycle_idx": cycle_idx,
        "pose_idx": pose_idx,
        "pose_name": pose_name,
        "j1": joints[0],
        "j2": joints[1],
        "j3": joints[2],
        "j4": joints[3],
        "gripper": joints[4],
        "robot_u": "",
        "robot_v": "",
        "robot_d": "",
        "robot_conf": "",
        "robot_bbox": "",
        "image_path": str(image_path),
    }

    if isinstance(yolo_robot, dict):
        row["robot_u"] = yolo_robot.get("u", "")
        row["robot_v"] = yolo_robot.get("v", "")
        row["robot_d"] = yolo_robot.get("d", "")
        row["robot_conf"] = yolo_robot.get("conf", "")
        row["robot_bbox"] = yolo_robot.get("bbox", "")

    return row


def draw_robot_detection(frame, yolo_robot):
    vis = frame.copy()

    if not isinstance(yolo_robot, dict):
        cv2.putText(
            vis,
            "end_effector: not detected",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return vis

    x1, y1, x2, y2 = map(int, yolo_robot["bbox"])
    u = int(yolo_robot["u"])
    v = int(yolo_robot["v"])
    d = yolo_robot.get("d")
    conf = float(yolo_robot.get("conf", 0.0))

    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.circle(vis, (u, v), 6, (0, 255, 0), -1)

    if d is None:
        label = f"end_effector u={u} v={v} d=None conf={conf:.2f}"
    else:
        label = f"end_effector u={u} v={v} d={float(d):.3f} conf={conf:.2f}"

    cv2.putText(
        vis,
        label,
        (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    return vis


def write_calibration_report(csv_path, out_dir, accepted_count, rejected_count):
    rows = load_calibration_rows(csv_path)
    report = make_calibration_report(
        rows=rows,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )

    report_json_path = out_dir / "calibration_report.json"
    report_txt_path = out_dir / "calibration_report.txt"
    coverage_path = out_dir / "uv_coverage.png"

    report_json_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    report_txt_path.write_text(
        format_calibration_report(report),
        encoding="utf-8",
    )
    save_uv_coverage_image(rows, coverage_path)

    calib_log(f"[CALIB] report json : {report_json_path}")
    calib_log(f"[CALIB] report text : {report_txt_path}")
    calib_log(f"[CALIB] uv coverage  : {coverage_path}")


def load_calibration_rows(csv_path):
    rows = []

    with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            rows.append(row)

    return rows


def make_calibration_report(rows, accepted_count, rejected_count):
    total_attempts = accepted_count + rejected_count
    valid_rows = []

    for row in rows:
        parsed = {
            "u": parse_float(row.get("robot_u")),
            "v": parse_float(row.get("robot_v")),
            "d": parse_float(row.get("robot_d")),
            "conf": parse_float(row.get("robot_conf")),
            "pose_name": row.get("pose_name", ""),
        }

        if parsed["u"] is None or parsed["v"] is None or parsed["d"] is None:
            continue

        valid_rows.append(parsed)

    u_values = [row["u"] for row in valid_rows]
    v_values = [row["v"] for row in valid_rows]
    d_values = [row["d"] for row in valid_rows]
    conf_values = [row["conf"] for row in valid_rows if row["conf"] is not None]

    pose_counts = {}

    for row in valid_rows:
        pose_name = row["pose_name"]
        pose_counts[pose_name] = pose_counts.get(pose_name, 0) + 1

    return {
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "total_attempts": total_attempts,
        "acceptance_rate": safe_ratio(accepted_count, total_attempts),
        "valid_csv_rows": len(valid_rows),
        "u": summarize_values(u_values),
        "v": summarize_values(v_values),
        "d": summarize_values(d_values),
        "conf": summarize_values(conf_values),
        "pose_counts": pose_counts,
        "pose_count_min": min(pose_counts.values()) if pose_counts else 0,
        "pose_count_max": max(pose_counts.values()) if pose_counts else 0,
        "pose_count_mean": (
            sum(pose_counts.values()) / len(pose_counts) if pose_counts else 0.0
        ),
    }


def format_calibration_report(report):
    lines = [
        "Calibration Report",
        "==================",
        "",
        f"accepted_count: {report['accepted_count']}",
        f"rejected_count: {report['rejected_count']}",
        f"total_attempts: {report['total_attempts']}",
        f"acceptance_rate: {report['acceptance_rate']:.3f}",
        f"valid_csv_rows: {report['valid_csv_rows']}",
        "",
        f"u: {format_summary(report['u'])}",
        f"v: {format_summary(report['v'])}",
        f"d: {format_summary(report['d'])}",
        f"conf: {format_summary(report['conf'])}",
        "",
        "Pose Counts",
        "-----------",
    ]

    for pose_name, count in sorted(report["pose_counts"].items()):
        lines.append(f"{pose_name}: {count}")

    lines.append("")
    lines.append(
        "pose_count "
        f"min={report['pose_count_min']} "
        f"mean={report['pose_count_mean']:.2f} "
        f"max={report['pose_count_max']}"
    )

    return "\n".join(lines) + "\n"


def save_uv_coverage_image(rows, path, width=640, height=480):
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    for row in rows:
        u = parse_float(row.get("robot_u"))
        v = parse_float(row.get("robot_v"))
        d = parse_float(row.get("robot_d"))

        if u is None or v is None:
            continue

        u = int(np.clip(round(u), 0, width - 1))
        v = int(np.clip(round(v), 0, height - 1))

        color = depth_to_color(d)
        cv2.circle(canvas, (u, v), 4, color, -1)

    cv2.putText(
        canvas,
        "calibration u/v coverage",
        (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), canvas)


def depth_to_color(depth):
    if depth is None:
        return (180, 180, 180)

    normalized = float(np.clip((depth - 0.2) / 0.8, 0.0, 1.0))
    blue = int(255 * (1.0 - normalized))
    red = int(255 * normalized)
    green = 120
    return (blue, green, red)


def summarize_values(values):
    if len(values) == 0:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "max": None,
            "std": None,
        }

    arr = np.array(values, dtype=np.float32)

    return {
        "count": int(len(values)),
        "min": float(arr.min()),
        "mean": float(arr.mean()),
        "max": float(arr.max()),
        "std": float(arr.std()),
    }


def format_summary(summary):
    if summary["count"] == 0:
        return "count=0"

    return (
        f"count={summary['count']} "
        f"min={summary['min']:.3f} "
        f"mean={summary['mean']:.3f} "
        f"max={summary['max']:.3f} "
        f"std={summary['std']:.3f}"
    )


def parse_float(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "" or text.lower() == "none":
        return None

    try:
        return float(text)
    except ValueError:
        return None


def safe_ratio(numerator, denominator):
    if denominator == 0:
        return 0.0

    return float(numerator) / float(denominator)


if __name__ == "__main__":
    main()
