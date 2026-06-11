import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path

from src.MotionTrajectory import (
    MOTION_FIELDNAMES,
    load_motion_csv,
    replay_motion_csv,
    sanitize_motion_name,
)
from src.RobotManager import ROBOT


def main():
    args = parse_args()
    robot = ROBOT()

    if args.replay is not None:
        replay_recorded_motion(
            robot=robot,
            csv_path=args.replay,
            speed=args.speed,
            dry_run=args.dry_run,
        )
        return

    record_motion(
        robot=robot,
        name=args.name,
        output_root=args.output_root,
        hz=args.hz,
        duration=args.duration,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record or replay OpenManipulatorX teleoperation joint trajectories."
    )
    parser.add_argument(
        "--name",
        default="heart",
        help="Motion name, e.g. heart, dance, wave_hand.",
    )
    parser.add_argument(
        "--output-root",
        default="robot_motion_records",
        help="Root directory for saved motion recordings.",
    )
    parser.add_argument(
        "--hz",
        type=float,
        default=5.0,
        help="Sampling rate for get_pose during recording.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Recording duration in seconds. If omitted, stop with Ctrl+C.",
    )
    parser.add_argument(
        "--replay",
        default=None,
        help="Path to a recorded motion.csv file to replay.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier. 2.0 is twice as fast.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print replay commands without moving the robot.",
    )
    return parser.parse_args()


def record_motion(robot, name, output_root, hz, duration=None):
    if hz <= 0:
        raise ValueError("hz must be positive")

    output_dir = make_output_dir(output_root, name)
    csv_path = output_dir / "motion.csv"
    metadata_path = output_dir / "metadata.json"

    metadata = {
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "hz": hz,
        "duration": duration,
        "columns": MOTION_FIELDNAMES,
        "notes": "Recorded from ROBOT.get_pose() while user teleoperates the robot.",
    }

    print(f"[record] motion name : {name}")
    print(f"[record] output dir  : {output_dir}")
    print(f"[record] sample hz   : {hz}")
    print("[record] Teleoperate the robot after pressing Enter.")

    input("[record] Press Enter to start recording > ")

    rows = []
    start_time = time.time()
    next_sample_time = start_time
    sample_index = 0
    period = 1.0 / hz

    try:
        while True:
            now = time.time()

            if duration is not None and now - start_time >= duration:
                break

            if now < next_sample_time:
                time.sleep(min(0.01, next_sample_time - now))
                continue

            pose = robot.get_pose()
            elapsed = time.time() - start_time

            row = make_motion_row(
                index=sample_index,
                elapsed=elapsed,
                wall_time=time.time(),
                pose=pose,
            )
            rows.append(row)

            print(
                "[record] "
                f"{sample_index:04d} "
                f"t={elapsed:6.3f} "
                f"pose=({pose[0]: .3f}, {pose[1]: .3f}, {pose[2]: .3f}, "
                f"{pose[3]: .3f}, {pose[4]: .3f})"
            )

            sample_index += 1
            next_sample_time += period

    except KeyboardInterrupt:
        print("\n[record] stopped by user")

    save_motion(csv_path, rows)

    metadata["sample_count"] = len(rows)
    metadata["actual_duration"] = rows[-1]["elapsed"] if rows else 0.0

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"[record] saved csv      : {csv_path}")
    print(f"[record] saved metadata : {metadata_path}")
    print(f"[record] sample count   : {len(rows)}")


def replay_recorded_motion(robot, csv_path, speed=1.0, dry_run=False):
    if speed <= 0:
        raise ValueError("speed must be positive")

    rows = load_motion_csv(csv_path)

    if len(rows) == 0:
        print(f"[replay] no samples: {csv_path}")
        return

    print(f"[replay] file     : {csv_path}")
    print(f"[replay] samples  : {len(rows)}")
    print(f"[replay] speed    : {speed}")
    print(f"[replay] dry_run  : {dry_run}")

    input("[replay] Press Enter to start replay > ")

    result = replay_motion_csv(
        robot=robot,
        csv_path=csv_path,
        speed=speed,
        dry_run=dry_run,
        verbose=True,
    )
    print(f"[replay] {result}")


def make_output_dir(output_root, name):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = sanitize_motion_name(name)
    output_dir = Path(output_root) / safe_name / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def make_motion_row(index, elapsed, wall_time, pose):
    return {
        "index": index,
        "elapsed": elapsed,
        "wall_time": wall_time,
        "j1": pose[0],
        "j2": pose[1],
        "j3": pose[2],
        "j4": pose[3],
        "gripper": pose[4],
    }


def save_motion(csv_path, rows):
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MOTION_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
