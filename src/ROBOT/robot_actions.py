import csv
import time
from pathlib import Path

from .MotionTrajectory import find_latest_motion_csv, replay_motion_csv

"""
DNC : dance
MOV : move to object
MVA : move above object
GRB : grab object
REL : release
LFT : lift from current pose
THR : throw object
HRT : draw heart
HND : hand over to camera/person
PRN : prone / lie down
STD : stand up straight
GRT : greet / wave hello
BAS : return to default pose
"""

MOVE_ABOVE_ANGLE_OFFSET = [0.0, -0.24, 0.21, -0.07]
HAND_OVER_POSE = [0.0, -0.55, 0.85, -0.45, 0.0]
DEFAULT_POSE = [0.0, 0.0, 0.0, 0.0, 0.0]
PRONE_POSE = [
    -0.06289321184158325,
    1.2486603260040283,
    -0.9495341181755066,
    -0.04601942375302315,
    -3.5252818634035066e-05,
]
STAND_POSE = [
    -0.07209710031747818,
    0.1089126393198967,
    -1.509437084197998,
    -0.13038836419582367,
    -3.5252818634035066e-05,
]


class RobotActions:
    """
    Robot action registry.

    ROBOT owns low-level movement primitives. RobotActions owns named actions
    and maps LLM/planner action names such as DNC, GRB, MOV to those primitives.
    """

    descriptions = {
        "DNC": "dance",
        "MOV": "move to object",
        "MVA": "move above object",
        "GRB": "grab object",
        "REL": "release",
        "LFT": "lift",
        "THR": "throw",
        "HRT": "draw heart",
        "HND": "hand over to camera or person",
        "PRN": "lie down",
        "STD": "stand up straight",
        "GRT": "greet or wave hello",
        "BAS": "return to default pose",
    }

    def __init__(self, robot):
        self.robot = robot
        self.registry = {
            "DNC": self.dance,
            "MOV": self.move_to_object,
            "MVA": self.move_above_object,
            "GRB": self.grab,
            "REL": self.release,
            "LFT": self.lift,
            "THR": self.throw,
            "HRT": self.draw_heart,
            "HND": self.hand_over,
            "PRN": self.lie_down,
            "STD": self.stand_up,
            "GRT": self.greet,
            "BAS": self.return_to_default,
        }

    def run(self, action_name, obj=None, rgbd_cam=None):
        action_name = str(action_name).strip().upper()
        action = self.registry.get(action_name)

        if action is None:
            print(f"[RobotActions] unknown action: {action_name}")
            return "failed"

        return action(obj=obj, rgbd_cam=rgbd_cam)

    def get_available_actions(self):
        return self.descriptions.copy()

    def get_action(self, action_name):
        action_name = str(action_name).strip().upper()
        return self.registry.get(action_name)

    def dance(self, obj=None, rgbd_cam=None):
        result = self._run_recorded_motion(
            "dance",
            speed=3.0,
            preserve_gripper=True,
        )

        if result is not None:
            return result

        gripper = self._current_gripper()
        poses = [
            [0.30, -0.95, 0.95, -0.15, gripper],
            [-0.30, -0.95, 0.95, -0.15, gripper],
            [0.30, -0.80, 1.05, -0.35, gripper],
            [-0.30, -0.80, 1.05, -0.35, gripper],
            self._with_gripper(self.robot.base_pose, gripper),
        ]

        return self._run_pose_sequence(poses, duration=0.8, sleep=0.15)

    def move_to_object(self, obj=None, rgbd_cam=None):
        if obj is None:
            return "failed"

        target_pose = self.robot._extract_target_pose(obj)

        if target_pose is None:
            return "failed"

        target_pose = self._with_current_gripper(target_pose)
        ok = self.robot._move_joint(*target_pose, duration=1.0)
        return "success" if ok else "failed"

    def move_above_object(self, obj=None, rgbd_cam=None):
        if obj is None:
            return "failed"

        ok = self.robot.move_to_uvd_offset(
            obj,
            angle_offset=MOVE_ABOVE_ANGLE_OFFSET,
            gripper=self._current_gripper(),
            duration=1.2,
        )

        return "success" if ok else "failed"

    def grab(self, obj=None, rgbd_cam=None):
        result = self.stand_up()

        if result != "success":
            return result

        time.sleep(0.15)
        ok = self.robot._open_gripper()

        if not ok:
            return "failed"

        time.sleep(0.15)

        if obj is None:
            ok = self.robot._close_gripper()
            return "success" if ok else "failed"

        target_obj = obj

        if not isinstance(obj, dict):
            target_obj = self.robot._get_move_target(obj, rgbd_cam)

        if target_obj is None:
            return "failed"

        steps = [
            (self.move_to_object, (target_obj,), {}),
            (self.robot._close_gripper, (), {}),
            (self.robot.lift_current_pose, (), {}),
        ]

        for func, args, kwargs in steps:
            ok = func(*args, **kwargs)

            if not ok:
                return "failed"

            time.sleep(0.15)

        return "success"

    def release(self, obj=None, rgbd_cam=None):
        ok = self.robot._open_gripper()
        return "success" if ok else "failed"

    def lift(self, obj=None, rgbd_cam=None):
        ok = self.robot.lift_current_pose()
        return "success" if ok else "failed"

    def throw(self, obj=None, rgbd_cam=None):
        ok = self.robot._close_gripper()

        if not ok:
            return "failed"

        time.sleep(0.1)
        result = self.return_to_default(duration=0.6)

        if result != "success":
            return result

        throw_pose = self._with_gripper(STAND_POSE, self.robot.gripper_open)
        ok = self.robot._move_joint(*throw_pose, duration=0.25)

        if not ok:
            return "failed"

        return "success"

    def draw_heart(self, obj=None, rgbd_cam=None):
        result = self._run_recorded_motion("heart", speed=2.0)

        if result is not None:
            return result

        poses = [
            [0.00, -0.85, 1.05, -0.35, self.robot.gripper_open],
            [-0.22, -0.78, 0.95, -0.30, self.robot.gripper_open],
            [-0.12, -0.66, 0.88, -0.25, self.robot.gripper_open],
            [0.00, -0.76, 0.98, -0.32, self.robot.gripper_open],
            [0.12, -0.66, 0.88, -0.25, self.robot.gripper_open],
            [0.22, -0.78, 0.95, -0.30, self.robot.gripper_open],
            [0.00, -0.95, 1.10, -0.42, self.robot.gripper_open],
            self.robot.base_pose,
        ]

        return self._run_pose_sequence(poses, duration=0.55, sleep=0.06)

    def greet(self, obj=None, rgbd_cam=None):
        result = self._run_recorded_motion(
            "greeting",
            speed=2.0,
            preserve_gripper=True,
        )

        if result is not None:
            return result

        gripper = self._current_gripper()
        poses = [
            [0.0, -0.70, 1.05, -0.35, gripper],
            [0.35, -0.70, 1.05, -0.35, gripper],
            [-0.35, -0.70, 1.05, -0.35, gripper],
            [0.35, -0.70, 1.05, -0.35, gripper],
            [0.0, -0.70, 1.05, -0.35, gripper],
            self._with_gripper(self.robot.base_pose, gripper),
        ]

        return self._run_pose_sequence(poses, duration=0.28, sleep=0.04)

    def hand_over(self, obj=None, rgbd_cam=None):
        pose = self._find_nearest_calibration_pose()

        if pose is None:
            pose = HAND_OVER_POSE

        ok = self.robot._move_joint(
            *self._with_current_gripper(pose),
            duration=1.0,
        )
        return "success" if ok else "failed"

    def lie_down(self, obj=None, rgbd_cam=None):
        ok = self.robot._move_joint(
            *self._with_current_gripper(PRONE_POSE),
            duration=1.0,
        )
        time.sleep(1.0)
        return "success" if ok else "failed"

    def stand_up(self, obj=None, rgbd_cam=None):
        ok = self.robot._move_joint(
            *self._with_current_gripper(STAND_POSE),
            duration=1.0,
        )
        time.sleep(1.0)
        return "success" if ok else "failed"

    def return_to_default(self, obj=None, rgbd_cam=None, duration=1.0):
        ok = self.robot._move_joint(
            *self._with_current_gripper(DEFAULT_POSE),
            duration=duration,
        )
        return "success" if ok else "failed"

    def _run_pose_sequence(self, poses, duration=0.8, sleep=0.1):
        for pose in poses:
            ok = self.robot._move_joint(*pose, duration=duration)

            if not ok:
                return "failed"

            time.sleep(sleep)

        return "success"

    def _run_recorded_motion(self, name, speed=1.0, preserve_gripper=False):
        csv_path = find_latest_motion_csv(name)

        if csv_path is None:
            return None

        print(
            f"[RobotActions] replay recorded motion: "
            f"{name} ({csv_path}) speed={speed}"
        )
        gripper_override = self._current_gripper() if preserve_gripper else None
        return replay_motion_csv(
            self.robot,
            csv_path,
            speed=speed,
            gripper_override=gripper_override,
        )

    def _current_gripper(self):
        pose = self.robot.get_pose()
        return float(pose[4])

    def _with_current_gripper(self, pose):
        return self._with_gripper(pose, self._current_gripper())

    def _with_gripper(self, pose, gripper):
        pose = [float(value) for value in pose[:5]]
        pose[4] = float(gripper)
        return pose

    def _find_nearest_calibration_pose(
        self,
        root="src/CALIBRATION/robot_camera_calibration_samples",
    ):
        paths = sorted(Path(root).glob("*/robot_camera_calibration_samples.csv"))

        if len(paths) == 0:
            return None

        best_row = None
        best_depth = None

        for path in reversed(paths):
            try:
                with path.open("r", newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        depth = self._parse_float(row.get("robot_d"))

                        if depth is None:
                            continue

                        if best_depth is None or depth < best_depth:
                            best_row = row
                            best_depth = depth
            except OSError:
                continue

            if best_row is not None:
                break

        if best_row is None:
            return None

        pose = [
            self._parse_float(best_row.get(name))
            for name in ["j1", "j2", "j3", "j4", "gripper"]
        ]

        if any(value is None for value in pose):
            return None

        print(
            "[RobotActions] hand-over calibration pose: "
            f"depth={best_depth:.6f}"
        )
        return pose

    def _parse_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_target_pose(self, obj):
        if not isinstance(obj, dict):
            return None

        if "angle" in obj:
            angle = obj["angle"]

            if not isinstance(angle, (list, tuple)) or len(angle) < 5:
                return None

            return angle[:5]

        required_keys = ["j1", "j2", "j3", "j4", "gripper"]

        for key in required_keys:
            if key not in obj:
                return None

        return [
            obj["j1"],
            obj["j2"],
            obj["j3"],
            obj["j4"],
            obj["gripper"],
        ]


def dance(robot):
    return RobotActions(robot).dance()


def move_to_object(robot, obj):
    return RobotActions(robot).move_to_object(obj=obj)


def move_above_object(robot, obj):
    return RobotActions(robot).move_above_object(obj=obj)


def grab(robot, obj=None, rgbd_cam=None):
    return RobotActions(robot).grab(obj=obj, rgbd_cam=rgbd_cam)


def release(robot):
    return RobotActions(robot).release()


def lift(robot):
    return RobotActions(robot).lift()


def throw(robot):
    return RobotActions(robot).throw()


def draw_heart(robot):
    return RobotActions(robot).draw_heart()


def hand_over(robot):
    return RobotActions(robot).hand_over()


def lie_down(robot):
    return RobotActions(robot).lie_down()


def stand_up(robot):
    return RobotActions(robot).stand_up()


def greet(robot):
    return RobotActions(robot).greet()


def return_to_default(robot):
    return RobotActions(robot).return_to_default()


def _run_pose_sequence(robot, poses, duration=0.8, sleep=0.1):
    for pose in poses:
        ok = robot._move_joint(*pose, duration=duration)

        if not ok:
            return "failed"

        time.sleep(sleep)

    return "success"


def _run_recorded_motion(robot, name):
    csv_path = find_latest_motion_csv(name)

    if csv_path is None:
        return None

    print(f"[robot_actions] replay recorded motion: {name} ({csv_path})")
    return replay_motion_csv(robot, csv_path)


def _extract_target_pose(obj):
    if "angle" in obj:
        angle = obj["angle"]

        if not isinstance(angle, (list, tuple)) or len(angle) < 5:
            return None

        return angle[:5]

    required_keys = ["j1", "j2", "j3", "j4", "gripper"]

    for key in required_keys:
        if key not in obj:
            return None

    return [
        obj["j1"],
        obj["j2"],
        obj["j3"],
        obj["j4"],
        obj["gripper"],
    ]


def DNC(robot):
    return dance(robot)


def MOV(robot, obj):
    return move_to_object(robot, obj)


def MVA(robot, obj):
    return move_above_object(robot, obj)


def GRB(robot, obj=None, rgbd_cam=None):
    return grab(robot, obj=obj, rgbd_cam=rgbd_cam)


def REL(robot):
    return release(robot)


def LFT(robot):
    return lift(robot)


def THR(robot):
    return throw(robot)


def HRT(robot):
    return draw_heart(robot)


def HND(robot, obj=None, rgbd_cam=None):
    return RobotActions(robot).hand_over(obj=obj, rgbd_cam=rgbd_cam)


def PRN(robot):
    return lie_down(robot)


def STD(robot):
    return stand_up(robot)


def GRT(robot):
    return greet(robot)


def BAS(robot):
    return return_to_default(robot)


ACTION_DESCRIPTIONS = {
    "DNC": "dance",
    "MOV": "move to object",
    "MVA": "move above object",
    "GRB": "grab object",
    "REL": "release",
    "LFT": "lift",
    "THR": "throw",
    "HRT": "draw heart",
    "HND": "hand over to camera or person",
    "PRN": "lie down",
    "STD": "stand up straight",
    "GRT": "greet or wave hello",
    "BAS": "return to default pose",
}

ACTION_FUNCTIONS = {
    "DNC": DNC,
    "MOV": MOV,
    "MVA": MVA,
    "GRB": GRB,
    "REL": REL,
    "LFT": LFT,
    "THR": THR,
    "HRT": HRT,
    "HND": HND,
    "PRN": PRN,
    "STD": STD,
    "GRT": GRT,
    "BAS": BAS,
}


def get_available_actions():
    return RobotActions.descriptions.copy()


def get_action_function(action_name):
    action_name = str(action_name).strip().upper()
    return ACTION_FUNCTIONS.get(action_name)
