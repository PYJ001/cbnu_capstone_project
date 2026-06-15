import argparse
import json
import sys
from pathlib import Path

try:
    from src.ROBOT.robot_main import ROBOT
except ImportError:
    project_root = Path(__file__).resolve().parents[2]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.ROBOT.robot_main import ROBOT


DEFAULT_ACTIONS = [
    "DNC",
    "MOV",
    "MVA",
    "GRB",
    "REL",
    "TRW",
    "LFT",
    "THR",
    "HRT",
    "HND",
    "PRN",
    "STD",
]

OBJECT_ACTIONS = {"MOV", "MVA", "GRB", "TRW", "HND"}


class PseudoRGBD:
    def __init__(self, objects):
        self.objects = list(objects)

    def get_latest_camera_data(self):
        return {"yolo_world": self.objects}


def make_pseudo_object(name="cup"):
    return {
        "name": name,
        "u": 320,
        "v": 240,
        "d": 0.52,
        "joint": [0.0, -0.85, 1.05, -0.35, 0.0],
        "angle": [0.0, -0.85, 1.05, -0.35, 0.0],
        "qrst": {
            "q": 0.0,
            "r": -0.85,
            "s": 1.05,
            "t": -0.35,
            "gripper": 0.0,
        },
    }


def make_action_payload(action_name, object_name):
    action_name = str(action_name).strip().upper()

    if action_name in OBJECT_ACTIONS:
        return {"name": action_name, "obj": object_name}

    return {"name": action_name}


def run_robot_action_tests(actions=None, real=False, object_name="cup", verbose=True):
    robot = ROBOT(dry_run=not real)
    pseudo_object = make_pseudo_object(object_name)
    pseudo_rgbd = PseudoRGBD([pseudo_object])
    results = []

    robot.launch()

    try:
        for action_name in actions or DEFAULT_ACTIONS:
            action_name = str(action_name).strip().upper()
            before_count = len(robot.move_history)
            payload = make_action_payload(action_name, object_name)

            if verbose:
                mode = "real" if real else "dry-run"
                obj_text = (
                    f" object={payload['obj']}"
                    if "obj" in payload
                    else ""
                )
                print(f"[robot_test] {mode} action={action_name}{obj_text}")

            result = robot.action(payload, rgbd_cam=pseudo_rgbd)
            moves = robot.move_history[before_count:]

            if verbose:
                print(
                    f"[robot_test] result={result} "
                    f"moves={len(moves)} "
                    f"last_pose={robot.get_current_pose()}"
                )

            results.append(
                {
                    "action": payload,
                    "result": result,
                    "move_count": len(moves),
                    "last_pose": robot.get_current_pose(),
                    "moves": moves,
                }
            )
    finally:
        robot.close()

    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run ROBOT package action tests. By default this is a dry run "
            "and does not call ROS or move real hardware."
        )
    )
    parser.add_argument(
        "--action",
        action="append",
        dest="actions",
        help="Action code to test. Can be repeated. Default: all actions.",
    )
    parser.add_argument(
        "--object",
        default="cup",
        help="Pseudo object name for object-based actions.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Call the real ROS move_joint service. Omit for dry-run.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print compact JSON results instead of full move logs.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print per-action progress lines.",
    )

    args = parser.parse_args()
    results = run_robot_action_tests(
        actions=args.actions,
        real=args.real,
        object_name=args.object,
        verbose=not args.quiet,
    )

    if args.summary:
        compact = [
            {
                "action": item["action"]["name"],
                "result": item["result"],
                "move_count": item["move_count"],
                "last_pose": item["last_pose"],
            }
            for item in results
        ]
        print(json.dumps(compact, indent=2, ensure_ascii=False))
        return

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
