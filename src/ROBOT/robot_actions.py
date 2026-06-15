import time

from .MotionTrajectory import find_latest_motion_csv, replay_motion_csv

"""
DNC : dance
WAV : wave hand
SKH : wave hand alias
MOV : move to object
MVA : move above object
GRB : grab object
REL : release
TRW : release alias
LFT : lift from current pose
THR : throw object
HRT : draw heart
HND : hand over to camera/person
"""

MOVE_ABOVE_ANGLE_OFFSET     = [0.0, -0.24, 0.21, -0.07]
GRASP_PRE_ANGLE_OFFSET      = [0.0, -0.28, 0.25, -0.08]
GRASP_APPROACH_ANGLE_OFFSET = [0.0, -0.04, 0.04, -0.01]


class RobotActions:
    """
    Robot action registry.

    ROBOT owns low-level movement primitives. RobotActions owns named actions
    and maps LLM/planner action names such as DNC, GRB, MOV to those primitives.
    """

    descriptions = {
        "DNC": "dance",
        "WAV": "wave hand",
        "SKH": "wave hand",
        "MOV": "move to object",
        "MVA": "move above object",
        "GRB": "grab object",
        "REL": "release",
        "TRW": "release",
        "LFT": "lift",
        "THR": "throw",
        "HRT": "draw heart",
        "HND": "hand over to camera or person",
    }

    def __init__(self, robot):
        self.robot = robot
        self.registry = {
            "DNC": self.dance,
            "WAV": self.wave_hand,
            "SKH": self.shake_hand,
            "MOV": self.move_to_object,
            "MVA": self.move_above_object,
            "GRB": self.grab,
            "REL": self.release,
            "TRW": self.release,
            "LFT": self.lift,
            "THR": self.throw,
            "HRT": self.draw_heart,
            "HND": self.hand_over,
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
        result = self._run_recorded_motion("dance")

        if result is not None:
            return result

        poses = [
            [0.30, -0.95, 0.95, -0.15, 0.0],
            [-0.30, -0.95, 0.95, -0.15, 0.0],
            [0.30, -0.80, 1.05, -0.35, 0.0],
            [-0.30, -0.80, 1.05, -0.35, 0.0],
            self.robot.base_pose,
        ]

        return self._run_pose_sequence(poses, duration=0.8, sleep=0.15)

    def wave_hand(self, obj=None, rgbd_cam=None):
        result = self._run_recorded_motion("wave_hand")

        if result is not None:
            return result

        poses = [
            [0.0, -0.85, 1.05, -0.25, 0.0],
            [0.0, -0.75, 1.00, -0.35, 0.0],
            [0.0, -0.85, 1.05, -0.25, 0.0],
            [0.0, -0.75, 1.00, -0.35, 0.0],
            self.robot.base_pose,
        ]

        return self._run_pose_sequence(poses, duration=0.8, sleep=0.15)

    def shake_hand(self, obj=None, rgbd_cam=None):
        return self.wave_hand(obj=obj, rgbd_cam=rgbd_cam)

    def move_to_object(self, obj=None, rgbd_cam=None):
        if obj is None:
            return "failed"

        target_pose = self.robot._extract_target_pose(obj)

        if target_pose is None:
            return "failed"

        ok = self.robot._move_joint(*target_pose, duration=1.0)
        return "success" if ok else "failed"

    def move_above_object(self, obj=None, rgbd_cam=None):
        if obj is None:
            return "failed"

        ok = self.robot.move_to_uvd_offset(
            obj,
            angle_offset=MOVE_ABOVE_ANGLE_OFFSET,
            gripper=self.robot.gripper_open,
            duration=1.2,
        )

        return "success" if ok else "failed"

    def grab(self, obj=None, rgbd_cam=None):
        if obj is None:
            ok = self.robot._close_gripper()
            return "success" if ok else "failed"

        target_obj = obj

        if not isinstance(obj, dict):
            target_obj = self.robot._get_move_target(obj, rgbd_cam)

        if target_obj is None:
            return "failed"

        steps = [
            (self.robot._open_gripper, (), {}),
            (
                self.robot.move_to_uvd_offset,
                (target_obj,),
                {
                    "angle_offset": GRASP_PRE_ANGLE_OFFSET,
                    "gripper": self.robot.gripper_open,
                    "duration": 1.2,
                },
            ),
            (
                self.robot.move_to_uvd_offset,
                (target_obj,),
                {
                    "angle_offset": GRASP_APPROACH_ANGLE_OFFSET,
                    "gripper": self.robot.gripper_open,
                    "duration": 1.2,
                },
            ),
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
        poses = [
            [0.0, -0.65, 0.85, -0.40, 0.0],
            [0.35, -0.55, 0.70, -0.35, 0.0],
        ]

        result = self._run_pose_sequence(poses, duration=0.45, sleep=0.08)

        if result != "success":
            return result

        ok = self.robot._open_gripper()

        if not ok:
            return "failed"

        time.sleep(0.15)

        ok = self.robot.move_to_base_pose(duration=1.0)
        return "success" if ok else "failed"

    def draw_heart(self, obj=None, rgbd_cam=None):
        result = self._run_recorded_motion("heart")

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

    def hand_over(self, obj=None, rgbd_cam=None):
        ok = self.robot._move_joint(
            0.0,
            -0.55,
            0.85,
            -0.45,
            0.0,
            duration=1.0,
        )

        return "success" if ok else "failed"

    def _run_pose_sequence(self, poses, duration=0.8, sleep=0.1):
        for pose in poses:
            ok = self.robot._move_joint(*pose, duration=duration)

            if not ok:
                return "failed"

            time.sleep(sleep)

        return "success"

    def _run_recorded_motion(self, name):
        csv_path = find_latest_motion_csv(name)

        if csv_path is None:
            return None

        print(f"[RobotActions] replay recorded motion: {name} ({csv_path})")
        return replay_motion_csv(self.robot, csv_path)

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


def wave_hand(robot):
    return RobotActions(robot).wave_hand()


def shake_hand(robot):
    return RobotActions(robot).shake_hand()


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


def WAV(robot):
    return wave_hand(robot)


def SKH(robot):
    return shake_hand(robot)


def MOV(robot, obj):
    return move_to_object(robot, obj)


def MVA(robot, obj):
    return move_above_object(robot, obj)


def GRB(robot, obj=None, rgbd_cam=None):
    return grab(robot, obj=obj, rgbd_cam=rgbd_cam)


def REL(robot):
    return release(robot)


def TRW(robot):
    return release(robot)


def LFT(robot):
    return lift(robot)


def THR(robot):
    return throw(robot)


def HRT(robot):
    return draw_heart(robot)


def HND(robot):
    return hand_over(robot)


ACTION_DESCRIPTIONS = {
    "DNC": "dance",
    "WAV": "wave hand",
    "SKH": "wave hand",
    "MOV": "move to object",
    "MVA": "move above object",
    "GRB": "grab object",
    "REL": "release",
    "TRW": "release",
    "LFT": "lift",
    "THR": "throw",
    "HRT": "draw heart",
    "HND": "hand over to camera or person",
}

ACTION_FUNCTIONS = {
    "DNC": DNC,
    "WAV": WAV,
    "SKH": SKH,
    "MOV": MOV,
    "MVA": MVA,
    "GRB": GRB,
    "REL": REL,
    "TRW": TRW,
    "LFT": LFT,
    "THR": THR,
    "HRT": HRT,
    "HND": HND,
}


def get_available_actions():
    return RobotActions.descriptions.copy()


def get_action_function(action_name):
    action_name = str(action_name).strip().upper()
    return ACTION_FUNCTIONS.get(action_name)
