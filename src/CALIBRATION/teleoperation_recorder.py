import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from src.ROBOT import ROBOT
except ImportError:
    project_root = Path(__file__).resolve().parents[2]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.ROBOT import ROBOT


DEFAULT_TELEOP_DIR = "src/CALIBRATION/teleoperation_poses"


def record_teleoperation_poses(
    robot,
    output_dir=DEFAULT_TELEOP_DIR,
    name_prefix="teleop",
    prompt=True,
    sample_hz=None,
    min_joint_distance=0.0,
):
    """
    Record robot joint poses while the user moves the robot by teleoperation.

    prompt=True records one pose each time Enter is pressed.
    sample_hz records automatically at the requested rate until Ctrl+C.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    poses = []

    if sample_hz is not None:
        _record_automatic(
            robot=robot,
            poses=poses,
            name_prefix=name_prefix,
            started_at=started_at,
            sample_hz=sample_hz,
            min_joint_distance=min_joint_distance,
        )
    elif prompt:
        _record_prompted(
            robot=robot,
            poses=poses,
            name_prefix=name_prefix,
            started_at=started_at,
            min_joint_distance=min_joint_distance,
        )

    path = _make_output_path(output_dir)
    save_teleoperation_poses(path, poses, started_at)
    return path


def load_teleoperation_poses(path):
    path = Path(path)

    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    raw_poses = data.get("poses", data)
    poses = []

    previous_elapsed = None

    for index, item in enumerate(raw_poses, start=1):
        if isinstance(item, dict):
            joints = item.get("joints")
            name = item.get("name", f"teleop_{index:04d}")
            elapsed = item.get("elapsed")
            duration = item.get("duration")
        else:
            joints = item
            name = f"teleop_{index:04d}"
            elapsed = None
            duration = None

        joints = _normalize_joints(joints)

        if joints is None:
            raise ValueError(f"invalid teleoperation pose at index {index}: {item}")

        pose = {
            "name": str(name),
            "joints": tuple(joints),
        }

        duration = _resolve_pose_duration(duration, elapsed, previous_elapsed)

        if duration is not None:
            pose["duration"] = duration

        poses.append(pose)
        previous_elapsed = _parse_float(elapsed, previous_elapsed)

    if len(poses) == 0:
        raise ValueError(f"teleoperation pose file is empty: {path}")

    return poses


def save_teleoperation_poses(path, poses, started_at=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": started_at,
        "pose_count": len(poses),
        "poses": poses,
    }

    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
        fp.write("\n")

    print(f"[TELEOP] saved {len(poses)} poses: {path}")
    return path


def _record_prompted(robot, poses, name_prefix, started_at, min_joint_distance):
    print("[TELEOP] Move the robot with teleoperation.")
    print("[TELEOP] Press Enter to record a pose, type q then Enter to finish.")

    while True:
        command = input("[TELEOP] record> ").strip().lower()

        if command in ["q", "quit", "exit", "done"]:
            break

        pose = robot.get_pose()

        if not _should_accept_pose(poses, pose, min_joint_distance):
            print("[TELEOP] skipped duplicate/small movement")
            continue

        poses.append(_make_pose_record(name_prefix, len(poses) + 1, pose, started_at))
        print(f"[TELEOP] recorded #{len(poses)} joints={pose}")


def _record_automatic(
    robot,
    poses,
    name_prefix,
    started_at,
    sample_hz,
    min_joint_distance,
):
    sample_hz = max(0.1, float(sample_hz))
    period = 1.0 / sample_hz
    print("[TELEOP] automatic recording started. Press Ctrl+C to finish.")

    try:
        while True:
            pose = robot.get_pose()

            if _should_accept_pose(poses, pose, min_joint_distance):
                poses.append(
                    _make_pose_record(name_prefix, len(poses) + 1, pose, started_at)
                )
                print(f"[TELEOP] recorded #{len(poses)} joints={pose}")

            time.sleep(period)
    except KeyboardInterrupt:
        print("\n[TELEOP] recording stopped")


def _make_pose_record(name_prefix, index, pose, started_at):
    return {
        "name": f"{name_prefix}_{index:04d}",
        "joints": [float(value) for value in pose],
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed": round(time.time() - started_at, 4),
    }


def _should_accept_pose(poses, pose, min_joint_distance):
    joints = _normalize_joints(pose)

    if joints is None:
        return False

    if len(poses) == 0 or min_joint_distance <= 0:
        return True

    previous = poses[-1].get("joints")

    if previous is None:
        return True

    distance = sum(
        (float(a) - float(b)) ** 2
        for a, b in zip(joints, previous)
    ) ** 0.5
    return distance >= float(min_joint_distance)


def _normalize_joints(joints):
    if joints is None or len(joints) != 5:
        return None

    try:
        return [float(value) for value in joints]
    except Exception:
        return None


def _resolve_pose_duration(duration, elapsed, previous_elapsed):
    value = _parse_float(duration)

    if value is not None and value > 0:
        return value

    elapsed_value = _parse_float(elapsed)

    if elapsed_value is None or previous_elapsed is None:
        return None

    delta = elapsed_value - float(previous_elapsed)

    if delta <= 0:
        return None

    return float(delta)


def _parse_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _make_output_path(output_dir):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path(output_dir) / f"teleoperation_poses_{timestamp}.json"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_TELEOP_DIR)
    parser.add_argument("--name-prefix", default="teleop")
    parser.add_argument("--sample-hz", type=float, default=None)
    parser.add_argument("--min-joint-distance", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    robot = ROBOT(dry_run=args.dry_run)
    path = record_teleoperation_poses(
        robot=robot,
        output_dir=args.output_dir,
        name_prefix=args.name_prefix,
        sample_hz=args.sample_hz,
        min_joint_distance=args.min_joint_distance,
    )
    print(f"[TELEOP] pose file: {path}")


if __name__ == "__main__":
    main()
