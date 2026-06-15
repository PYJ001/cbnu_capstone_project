import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from src.ROBOT import ROBOT
from src.ROBOT.MotionTrajectory import (
    MOTION_FIELDNAMES,
    replay_motion_csv,
    sanitize_motion_name,
)


def record_motion(name, hz=5.0, output_root="robot_motion_records", auto=False):
    robot = ROBOT()
    hz = max(0.1, float(hz))
    period = 1.0 / hz
    motion_name = sanitize_motion_name(name)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = Path(output_root) / motion_name / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "motion.csv"

    print(f"[record_motion] name={motion_name}")
    print("[record_motion] move the robot by teleoperation")

    if auto:
        print(f"[record_motion] auto mode hz={hz}")
        print("[record_motion] press Ctrl+C to stop and save")
    else:
        print("[record_motion] press Enter to save a pose")
        print("[record_motion] type q then Enter to stop and save")

    started_at = time.time()
    index = 0

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MOTION_FIELDNAMES)
        writer.writeheader()

        while True:
            try:
                if auto:
                    loop_started_at = time.time()
                else:
                    command = input("[record_motion] save> ").strip().lower()

                    if command in ["q", "quit", "exit", "done"]:
                        break

                now = time.time()
                pose = robot.get_pose()
                index = write_motion_row(
                    writer=writer,
                    csv_file=csv_file,
                    index=index,
                    started_at=started_at,
                    wall_time=now,
                    pose=pose,
                )

                if auto:
                    elapsed = time.time() - loop_started_at
                    time.sleep(max(0.0, period - elapsed))

            except KeyboardInterrupt:
                print()
                break

    print(f"[record_motion] saved: {csv_path}")
    return csv_path


def write_motion_row(writer, csv_file, index, started_at, wall_time, pose):
    index += 1
    writer.writerow(
        {
            "index": index,
            "elapsed": wall_time - started_at,
            "wall_time": wall_time,
            "j1": pose[0],
            "j2": pose[1],
            "j3": pose[2],
            "j4": pose[3],
            "gripper": pose[4],
        }
    )
    csv_file.flush()

    print(
        "[record_motion] "
        f"{index:04d} "
        f"pose=({pose[0]:.4f}, {pose[1]:.4f}, {pose[2]:.4f}, "
        f"{pose[3]:.4f}, {pose[4]:.4f})"
    )
    return index


def replay_motion(path, speed=1.0, dry_run=False, verbose=True):
    robot = ROBOT(dry_run=dry_run)
    result = replay_motion_csv(
        robot=robot,
        csv_path=path,
        speed=speed,
        dry_run=dry_run,
        verbose=verbose,
    )
    print(f"[record_motion] replay result: {result}")
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default=None, help="Motion name to record.")
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Record continuously at --hz. Default records one pose per Enter.",
    )
    parser.add_argument("--output-root", default="robot_motion_records")
    parser.add_argument("--replay", default=None, help="Replay a motion.csv file.")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.replay is not None:
        replay_motion(args.replay, speed=args.speed, dry_run=args.dry_run)
        return

    if args.name is None:
        raise SystemExit("record mode needs --name")

    record_motion(
        name=args.name,
        hz=args.hz,
        output_root=args.output_root,
        auto=args.auto,
    )


if __name__ == "__main__":
    main()
