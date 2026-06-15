import csv
import time
from pathlib import Path


MOTION_FIELDNAMES = [
    "index",
    "elapsed",
    "wall_time",
    "j1",
    "j2",
    "j3",
    "j4",
    "gripper",
]


def find_latest_motion_csv(name, root="robot_motion_records"):
    motion_root = Path(root) / sanitize_motion_name(name)

    if not motion_root.exists():
        return None

    paths = sorted(motion_root.glob("*/motion.csv"))

    if len(paths) == 0:
        return None

    return paths[-1]


def load_motion_csv(csv_path):
    rows = []

    with Path(csv_path).open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append(
                {
                    "index": int(row["index"]),
                    "elapsed": float(row["elapsed"]),
                    "wall_time": float(row["wall_time"]),
                    "j1": float(row["j1"]),
                    "j2": float(row["j2"]),
                    "j3": float(row["j3"]),
                    "j4": float(row["j4"]),
                    "gripper": float(row["gripper"]),
                }
            )

    return rows


def replay_motion_csv(
    robot,
    csv_path,
    speed=1.0,
    min_duration=0.05,
    dry_run=False,
    verbose=False,
    clamp_gripper=True,
    skip_invalid=False,
):
    if speed <= 0:
        raise ValueError("speed must be positive")

    rows = load_motion_csv(csv_path)

    if len(rows) == 0:
        return "failed"

    previous_elapsed = None

    for row in rows:
        elapsed = row["elapsed"]
        duration = resolve_replay_duration(
            elapsed=elapsed,
            previous_elapsed=previous_elapsed,
            speed=speed,
            min_duration=min_duration,
        )
        pose = [
            row["j1"],
            row["j2"],
            row["j3"],
            row["j4"],
            row["gripper"],
        ]

        pose = sanitize_replay_pose(
            robot=robot,
            pose=pose,
            row_index=row["index"],
            clamp_gripper=clamp_gripper,
            skip_invalid=skip_invalid,
            verbose=verbose,
        )

        if pose is None:
            previous_elapsed = elapsed
            continue

        if verbose:
            print(
                "[motion] "
                f"{int(row['index']):04d} "
                f"duration={duration:.3f} "
                f"pose=({pose[0]:.3f}, {pose[1]:.3f}, {pose[2]:.3f}, "
                f"{pose[3]:.3f}, {pose[4]:.3f})"
            )

        if not dry_run:
            ok = robot._move_joint(*pose, duration=duration)

            if not ok:
                return "failed"

            time.sleep(duration)

        previous_elapsed = elapsed

    return "success"


def resolve_replay_duration(elapsed, previous_elapsed, speed=1.0, min_duration=0.05):
    if previous_elapsed is None:
        return max(1.0 / speed, min_duration)

    return max(min_duration, (elapsed - previous_elapsed) / speed)


def sanitize_replay_pose(
    robot,
    pose,
    row_index=None,
    clamp_gripper=True,
    skip_invalid=True,
    verbose=False,
):
    pose = [float(value) for value in pose]

    if clamp_gripper and hasattr(robot, "joint_limits"):
        low, high = robot.joint_limits.get("gripper", (None, None))

        if low is not None and high is not None:
            original = pose[4]
            pose[4] = min(max(pose[4], low), high)

            if verbose and pose[4] != original:
                print(
                    "[motion] "
                    f"row={row_index} clamp gripper "
                    f"{original:.4f}->{pose[4]:.4f}"
                )

    if hasattr(robot, "_validate_pose") and not robot._validate_pose(pose):
        if skip_invalid:
            print(f"[motion] skip invalid pose row={row_index}: {pose}")
            return None

    return pose


def sanitize_motion_name(name):
    result = []

    for char in str(name).strip().lower():
        if char.isalnum() or char in ["_", "-"]:
            result.append(char)
        elif char.isspace():
            result.append("_")

    safe_name = "".join(result).strip("_")

    if safe_name == "":
        return "motion"

    return safe_name
