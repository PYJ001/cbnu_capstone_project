import re
import subprocess
from .robot_actions import DNC, WAV, SKH, MOV, MVA, GRB, REL, TRW, LFT, THR, HRT, HND


CALIBRATION_POSES = [
    {
        "name": "calib_01_center_high",
        "joints": (0.000000, -0.650000, 0.850000, -0.350000, 0.0),
    },
    {
        "name": "calib_02_center_mid",
        "joints": (0.000000, -0.850000, 1.050000, -0.350000, 0.0),
    },
    {
        "name": "calib_03_center_low",
        "joints": (0.000000, -1.050000, 1.250000, -0.450000, 0.0),
    },
    {
        "name": "calib_04_left_front",
        "joints": (-0.497010, 0.863631, -0.346680, -0.475534, 0.0),
    },
    {
        "name": "calib_05_left_mid",
        "joints": (-0.995554, -0.440252, 1.233321, -0.477068, 0.0),
    },
    {
        "name": "calib_06_right_mid",
        "joints": (0.964874, -0.441786, 1.231787, -0.475534, 0.0),
    },
    {
        "name": "calib_07_right_front",
        "joints": (0.607456, 1.084524, -0.688757, -0.475534, 0.0),
    },
    {
        "name": "calib_08_right_low",
        "joints": (0.605922, 0.458660, -0.967942, 0.552233, 0.0),
    },
    {
        "name": "calib_09_left_low",
        "joints": (-0.599786, 0.458660, -0.967942, 0.544563, 0.0),
    },
    {
        "name": "calib_10_far_left",
        "joints": (-1.075321, -0.242369, -0.770058, 0.544563, 0.0),
    },
    {
        "name": "calib_11_far_right",
        "joints": (0.846000, -0.620893, 0.013010, 0.543029, 0.0),
    },
    {
        "name": "calib_12_left_high",
        "joints": (-0.650000, -0.650000, 0.850000, -0.350000, 0.0),
    },
    {
        "name": "calib_13_right_high",
        "joints": (0.650000, -0.650000, 0.850000, -0.350000, 0.0),
    },
    {
        "name": "calib_14_left_center",
        "joints": (-0.550000, -0.850000, 1.050000, -0.350000, 0.0),
    },
    {
        "name": "calib_15_right_center",
        "joints": (0.550000, -0.850000, 1.050000, -0.350000, 0.0),
    },
    {
        "name": "calib_16_left_low_mid",
        "joints": (-0.450000, -1.050000, 1.250000, -0.450000, 0.0),
    },
    {
        "name": "calib_17_right_low_mid",
        "joints": (0.450000, -1.050000, 1.250000, -0.450000, 0.0),
    },
    {
        "name": "calib_18_left_near",
        "joints": (-0.350000, 0.350000, -0.450000, 0.250000, 0.0),
    },
    {
        "name": "calib_19_center_near",
        "joints": (0.000000, 0.350000, -0.450000, 0.250000, 0.0),
    },
    {
        "name": "calib_20_right_near",
        "joints": (0.350000, 0.350000, -0.450000, 0.250000, 0.0),
    },
]

class ROBOT:
    """
    Action set

    DNC : dance
    WAV : wave hand
    SKH : wave hand
    GRB obj : grab object
    REL : release object
    TRW : release object
    MOV obj : move to object
    MVA obj : move above object
    LFT : lift
    THR : throw
    HRT : draw heart
    HND : hand over
    """

    def __init__(self):
        self.base_pose = [0.0, -1.000155, 1.000155, 0.0, 0.0]
        self.current_pose = self.base_pose.copy()
        self.calibration_poses = CALIBRATION_POSES.copy()
        self.gripper_open = 0.0
        self.gripper_closed = 0.015

        self.ros_setup_cmd = (
            "source /opt/ros/jazzy/setup.bash && "
            "source ~/ros2_ws/install/setup.bash"
        )

        self.move_joint_cmd = "ros2 service call /move_joint joint_control/srv/MoveJoint"
        self.get_pose_cmd = "ros2 run joint_control get_pose"

#---------------------------------------------------------------
#        self.weights = self.calibration()
#---------------------------------------------------------------

        self.feedback_max_iter = 30
        self.feedback_sleep = 0.15

    def action(self, action, rgbd_cam=None):
        """
        action 예시:

        {"name": "DNC"}
        {"name": "WAV"}
        {"name": "SKH"}
        {"name": "GRB", "obj": "bottle"}
        {"name": "REL"}
        {"name": "TRW"}
        {"name": "MOV", "obj": "bottle"}
        {"name": "MVA", "obj": "basket"}
        {"name": "LFT"}
        {"name": "THR"}
        {"name": "HRT"}
        {"name": "HND"}

        또는 기존 방식처럼 숫자도 허용:

        0: DNC
        1: WAV
        2: GRB
        3: REL
        4: MOV
        """

        action_name, obj = self._normalize_action(action)

        #print(f"[ROBOT] action: {action_name}, obj: {obj}")

        if action_name == "DNC":
            return DNC(self)

        if action_name == "WAV":
            return WAV(self)

        if action_name == "SKH":
            return SKH(self)

        if action_name == "GRB":
            return GRB(self, obj=obj, rgbd_cam=rgbd_cam)

        if action_name == "REL":
            return REL(self)

        if action_name == "TRW":
            return TRW(self)

        if action_name == "MOV":
            target_obj = self._get_move_target(obj, rgbd_cam)

            if target_obj is None:
                print(f"[ROBOT] MOV target not found: {obj}")
                return "failed"

            return MOV(self, target_obj)

        if action_name == "MVA":
            target_obj = self._get_move_target(obj, rgbd_cam)

            if target_obj is None:
                print(f"[ROBOT] MVA target not found: {obj}")
                return "failed"

            return MVA(self, target_obj)

        if action_name == "LFT":
            return LFT(self)

        if action_name == "THR":
            return THR(self)

        if action_name == "HRT":
            return HRT(self)

        if action_name == "HND":
            return HND(self)

        print(f"[ROBOT] unknown action: {action}")
        return "failed"

    def _normalize_action(self, action):
        if isinstance(action, dict):
            name = str(action.get("name", action.get("action", ""))).strip().upper()
            obj = action.get("obj", action.get("object", None))

            if isinstance(obj, str):
                obj = obj.strip().lower()

            return name, obj

        if isinstance(action, str):
            tokens = action.strip().split()

            if len(tokens) == 0:
                return "UNKNOWN", None

            name = tokens[0].upper()
            obj = " ".join(tokens[1:]).strip().lower() if len(tokens) >= 2 else None

            return name, obj

        if isinstance(action, int):
            table = {
                0: "DNC",
                1: "WAV",
                2: "GRB",
                3: "REL",
                4: "MOV",
            }

            return table.get(action, "UNKNOWN"), None

        return "UNKNOWN", None

    def get_calibration_poses(self):
        return [pose.copy() for pose in self.calibration_poses]

    def move_to_calibration_pose(self, pose, duration=1.5):
        if isinstance(pose, int):
            pose = self.calibration_poses[pose]

        joints = pose.get("joints") if isinstance(pose, dict) else pose

        if joints is None or len(joints) != 5:
            print(f"[ROBOT] invalid calibration pose: {pose}")
            return False

        return self._move_joint(*joints, duration=duration)

    def move_to_base_pose(self, duration=1.5):
        return self._move_joint(*self.base_pose, duration=duration)

    def get_pose(self):
        cmd = f"{self.ros_setup_cmd} && {self.get_pose_cmd}"

        result = subprocess.run(
            cmd,
            shell=True,
            executable="/bin/bash",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            print("[ROBOT] get_pose failed")
            print(result.stderr)
            return self.current_pose.copy()

        pose = self._parse_get_pose_output(result.stdout)

        if pose is None:
            print("[ROBOT] get_pose parse failed")
            print(result.stdout)
            return self.current_pose.copy()

        self.current_pose = pose
        return pose.copy()

    def _get_move_target(self, obj_name, rgbd_cam):
        if rgbd_cam is None:
            print("[ROBOT] target action needs rgbd_cam")
            return None

        try:
            if hasattr(rgbd_cam, "get_latest_camera_data"):
                camera_data = rgbd_cam.get_latest_camera_data()

                if camera_data is None:
                    print("[ROBOT] target camera data is not ready")
                    return None

                yolo_world = camera_data["yolo_world"]
            else:
                _, _, _, yolo_world = rgbd_cam.get_frame()
        except Exception as e:
            print(f"[ROBOT] target camera read failed: {e}")
            return None

        objects = self._as_object_list(yolo_world)

        if obj_name is None:
            if len(objects) == 1:
                return objects[0]

            print("[ROBOT] target action needs target object name")
            return None

        return self._find_object(objects, obj_name)

    def move_to_uvd_offset(
        self,
        obj,
        u_offset=0,
        v_offset=0,
        d_offset=0.0,
        angle_offset=None,
        gripper=None,
        duration=1.0,
    ):
        pose = self._make_offset_pose(
            obj=obj,
            u_offset=u_offset,
            v_offset=v_offset,
            d_offset=d_offset,
            angle_offset=angle_offset,
            gripper=gripper,
        )

        if pose is None:
            print(f"[ROBOT] cannot make offset pose: {obj}")
            return False

        return self._move_joint(*pose, duration=duration)

    def lift_current_pose(self, duration=1.0):
        pose = self.get_pose()
        pose[1] -= 0.18
        pose[2] += 0.18

        return self._move_joint(*pose, duration=duration)

    def _make_offset_pose(
        self,
        obj,
        u_offset=0,
        v_offset=0,
        d_offset=0.0,
        angle_offset=None,
        gripper=None,
    ):
        pose = self._extract_target_pose(obj)

        if pose is None:
            return None

        pose = [float(value) for value in pose[:5]]

        if angle_offset is None:
            angle_offset = self._estimate_angle_offset(
                u_offset=u_offset,
                v_offset=v_offset,
                d_offset=d_offset,
            )

        for idx, offset in enumerate(angle_offset[:4]):
            pose[idx] += float(offset)

        if gripper is not None:
            pose[4] = float(gripper)

        return pose

    def _estimate_angle_offset(self, u_offset=0, v_offset=0, d_offset=0.0):
        horizontal_scale = float(u_offset) / 100.0
        vertical_scale = -float(v_offset) / 45.0
        depth_scale = float(d_offset) / 0.04 if d_offset != 0 else 0.0

        return [
            0.08 * horizontal_scale,
            -0.12 * vertical_scale - 0.05 * depth_scale,
            0.10 * vertical_scale + 0.05 * depth_scale,
            -0.04 * vertical_scale,
        ]

    def _extract_target_pose(self, obj):
        if not isinstance(obj, dict):
            return None

        if "angle" in obj:
            angle = obj["angle"]

            if not isinstance(angle, (list, tuple)) or len(angle) < 5:
                return None

            return list(angle[:5])

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

    def _move_joint(self, j1, j2, j3, j4, gripper=0.0, duration=2.0):
        cmd = (
            f'{self.ros_setup_cmd} && '
            f'{self.move_joint_cmd} '
            f'"{{j1: {j1}, j2: {j2}, j3: {j3}, j4: {j4}, '
            f'gripper: {gripper}, duration: {duration}}}"'
        )

        #print(
        #    f"[ROBOT] move_joint: "
        #    f"{j1:.3f}, {j2:.3f}, {j3:.3f}, {j4:.3f}, "
        #    f"gripper={gripper:.3f}, duration={duration:.2f}"
        #)

        result = subprocess.run(
            cmd,
            shell=True,
            executable="/bin/bash",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            print("[ROBOT] move_joint failed")
            print(result.stderr)
            return False

        self.current_pose = [
            float(j1),
            float(j2),
            float(j3),
            float(j4),
            float(gripper),
        ]

        return True

    def _parse_get_pose_output(self, text):
        values = {}

        for key in ["j1", "j2", "j3", "j4", "gripper"]:
            match = re.search(rf"^{key}:\s*([-+0-9.eE]+)", text, flags=re.MULTILINE)

            if match is None:
                return None

            values[key] = float(match.group(1))

        return [
            values["j1"],
            values["j2"],
            values["j3"],
            values["j4"],
            values["gripper"],
        ]

    def _find_object(self, yolo_world, obj_name):
        """
        yolo_world 예시:

        [
            {"name": "bottle", "u": 320, "v": 240, "d": 0.52},
            {"name": "cup", "u": 100, "v": 200, "d": 0.61},
        ]
        """

        yolo_world = self._as_object_list(yolo_world)

        obj_name = obj_name.lower()

        for item in yolo_world:
            name = str(item.get("name", "")).lower()

            if name == obj_name:
                return item

        return None

    def _as_object_list(self, detections):
        if detections is None:
            return []

        if isinstance(detections, dict):
            return [detections]

        if isinstance(detections, list):
            return detections

        return []

    def _visual_servo_step(self, robot_uvd, obj_uvd):
        """
        매우 단순한 visual servo placeholder.

        현재는 실제 IK/regression 연결 전 구조만 잡아둔 상태입니다.

        나중에 여기서 해야 할 일:

        - robot end-effector uvd
        - object uvd
        - 두 점의 오차 계산
        - 오차 방향에 따라 move_xyz 또는 regression 기반 move_joint 호출
        """

        if robot_uvd is None or obj_uvd is None:
            return "need_feedback"

        ru = robot_uvd.get("u", None)
        rv = robot_uvd.get("v", None)
        rd = robot_uvd.get("d", None)

        ou = obj_uvd.get("u", None)
        ov = obj_uvd.get("v", None)
        od = obj_uvd.get("d", None)

        if None in [ru, rv, rd, ou, ov, od]:
            return "need_feedback"

        du = ou - ru
        dv = ov - rv
        dd = od - rd

        pixel_error = (du ** 2 + dv ** 2) ** 0.5
        depth_error = abs(dd)

        #print(
        #    f"[ROBOT][servo] du={du:.1f}, dv={dv:.1f}, "
        #    f"pixel_error={pixel_error:.1f}, depth_error={depth_error:.3f}"
        #)

        if pixel_error < 25 and depth_error < 0.05:
            return "success"

        return "need_feedback"

    def _open_gripper(self):
        pose = self.get_pose()
        pose[4] = self.gripper_open

        return self._move_joint(*pose, duration=0.8)

    def _close_gripper(self):
        pose = self.get_pose()
        pose[4] = self.gripper_closed

        return self._move_joint(*pose, duration=0.8)

#################################################################################

def main():
    robot = ROBOT()

    robot.action({"name": "DNC"})
    robot.action({"name": "SKH"})
    robot.action({"name": "TRW"})
    
    robot.action({"name": "GRB", "obj": "bottle"})
    # GRB는 rgbd_cam이 필요합니다.
    # robot.action({"name": "GRB", "obj": "bottle"}, rgbd_cam=rgbd_cam)


if __name__ == "__main__":
    main()
