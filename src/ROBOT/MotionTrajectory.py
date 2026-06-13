import csv
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
):
    if speed <= 0:
        raise ValueError("speed must be positive")

    rows = load_motion_csv(csv_path)

    if len(rows) == 0:
        return "failed"

    previous_elapsed = rows[0]["elapsed"]

    for row in rows:
        elapsed = row["elapsed"]
        duration = max(min_duration, (elapsed - previous_elapsed) / speed)
        pose = [
            row["j1"],
            row["j2"],
            row["j3"],
            row["j4"],
            row["gripper"],
        ]

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

        previous_elapsed = elapsed

    return "success"


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
