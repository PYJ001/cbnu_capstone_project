import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from src.CALIBRATION.calibration_poses import DEFAULT_CALIBRATION_POSES
    from src.ROBOT.robot_actions import RobotActions
except ImportError:
    project_root = Path(__file__).resolve().parents[2]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.CALIBRATION.calibration_poses import DEFAULT_CALIBRATION_POSES
    from src.ROBOT.robot_actions import RobotActions


class ROBOT:
    """
    RobotApp-facing robot package entry point.

    robot_main owns the runtime robot object now. Legacy RobotManager,
    RobotService, and RobotActionHandler are no longer part of the active path.
    """

    def __init__(
        self,
        dry_run=False,
        command_timeout=None,
        validate_limits=False,
    ):
        self.base_pose = [0.0, -1.000155, 1.000155, 0.0, 0.0]
        self.current_pose = self.base_pose.copy()
        self.calibration_poses = [pose.copy() for pose in DEFAULT_CALIBRATION_POSES]
        self.gripper_open = 0.0
        self.gripper_closed = 0.015
        self.dry_run = bool(dry_run)
        self.command_timeout = command_timeout
        self.validate_limits = bool(validate_limits)
        self.move_history = []
        self.joint_limits = {
            "j1": (-3.14, 3.14),
            "j2": (-3.14, 3.14),
            "j3": (-3.14, 3.14),
            "j4": (-3.14, 3.14),
            "gripper": (-0.05, 0.05),
        }

        self.ros_setup_cmd = (
            "source /opt/ros/jazzy/setup.bash && "
            "source ~/ros2_ws/install/setup.bash"
        )
        self.move_joint_cmd = "ros2 service call /move_joint joint_control/srv/MoveJoint"
        self.get_pose_cmd = "ros2 run joint_control get_pose"

        self.feedback_max_iter = 30
        self.feedback_sleep = 0.15
        self.actions = RobotActions(self)
        self.running = False

    # lifecycle
    def launch(self):
        self.running = True
        return True

    def run(self, action_sequence=None, rgbd_cam=None, camera_data=None, interface=None):
        return self.run_sequence(
            action_sequence or [],
            rgbd_cam=rgbd_cam,
            camera_data=camera_data,
            interface=interface,
        )

    def close(self):
        self.running = False
        return True

    # pose/state
    def get_pose(self):
        if self.dry_run:
            return self.current_pose.copy()

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

    def get_current_pose(self):
        return self.current_pose.copy()

    def set_current_pose(self, pose):
        if pose is None or len(pose) != 5:
            return False

        self.current_pose = [float(value) for value in pose]
        return True

    def move_angle(self, j1, j2, j3, j4, gripper=0.0, duration=2.0):
        return self._move_joint(
            j1=j1,
            j2=j2,
            j3=j3,
            j4=j4,
            gripper=gripper,
            duration=duration,
        )

    def move_to_base_pose(self, duration=1.5):
        return self._move_joint(*self.base_pose, duration=duration)

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

    # action orchestration
    def action(self, action, rgbd_cam=None, camera_data=None):
        action_name, obj = self._normalize_action(action)
        target_source = rgbd_cam if rgbd_cam is not None else camera_data

        if action_name in ["MOV", "MVA"]:
            target_obj = self._get_move_target(obj, target_source)

            if target_obj is None:
                print(f"[ROBOT] {action_name} target not found: {obj}")
                return "failed"

            return self.actions.run(action_name, obj=target_obj, rgbd_cam=target_source)

        if action_name in self.actions.registry:
            return self.actions.run(action_name, obj=obj, rgbd_cam=target_source)

        print(f"[ROBOT] unknown action: {action}")
        return "failed"

    def run_sequence(
        self,
        action_sequence,
        rgbd_cam=None,
        camera_data=None,
        interface=None,
    ):
        results = []
        target_source = rgbd_cam if rgbd_cam is not None else camera_data

        for action in action_sequence or []:
            result = self.action(action, rgbd_cam=target_source)
            results.append({"action": action, "result": result})

            if interface is not None:
                interface.update(action_result=result)

            if result in ["failed", "unsafe"]:
                break

        return results

    def get_available_actions(self):
        return self.actions.get_available_actions()

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
                1: "GRB",
                2: "REL",
                3: "MOV",
                4: "MVA",
                5: "PRN",
                6: "STD",
                7: "GRT",
                8: "BAS",
                9: "CLS",
            }
            return table.get(action, "UNKNOWN"), None

        return "UNKNOWN", None

    def _get_move_target(self, obj_name, rgbd_cam=None):
        if isinstance(obj_name, dict):
            return obj_name

        objects = self._get_world_objects(rgbd_cam)

        if obj_name is None:
            if len(objects) == 1:
                return objects[0]

            print("[ROBOT] target action needs target object name")
            return None

        return self._find_object(objects, obj_name)

    def _get_world_objects(self, rgbd_cam=None):
        if rgbd_cam is None:
            print("[ROBOT] target action needs rgbd_cam or camera_data")
            return []

        if isinstance(rgbd_cam, dict):
            return self._as_object_list(rgbd_cam.get("yolo_world"))

        try:
            if hasattr(rgbd_cam, "get_latest_camera_data"):
                camera_data = rgbd_cam.get_latest_camera_data()

                if camera_data is None:
                    print("[ROBOT] target camera data is not ready")
                    return []

                return self._as_object_list(camera_data.get("yolo_world"))

            _, _, _, yolo_world = rgbd_cam.get_frame()
            return self._as_object_list(yolo_world)
        except Exception as exc:
            print(f"[ROBOT] target camera read failed: {exc}")
            return []

    # primitive control
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

    def _open_gripper(self):
        pose = self.get_pose()
        pose[4] = self.gripper_open
        return self._move_joint(*pose, duration=0.8)

    def _close_gripper(self):
        pose = self.get_pose()
        pose[4] = self.gripper_closed
        return self._move_joint(*pose, duration=0.8)

    def _move_joint(self, j1, j2, j3, j4, gripper=0.0, duration=2.0):
        pose = [
            float(j1),
            float(j2),
            float(j3),
            float(j4),
            float(gripper),
        ]
        duration = float(duration)

        if self.dry_run:
            self.current_pose = pose.copy()
            self._record_move(pose, duration, dry_run=True)
            return True

        cmd = (
            f"{self.ros_setup_cmd} && "
            f"{self.move_joint_cmd} "
            f'"{{j1: {pose[0]}, j2: {pose[1]}, j3: {pose[2]}, j4: {pose[3]}, '
            f'gripper: {pose[4]}, duration: {duration}}}"'
        )

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                executable="/bin/bash",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.command_timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"[ROBOT] move_joint timeout after {self.command_timeout}s")
            return False

        if result.returncode != 0:
            print("[ROBOT] move_joint failed")
            print(result.stderr)
            return False

        self.current_pose = pose.copy()
        self._record_move(pose, duration, dry_run=False)
        return True

    # helpers
    def _record_move(self, pose, duration, dry_run):
        self.move_history.append(
            {
                "j1": pose[0],
                "j2": pose[1],
                "j3": pose[2],
                "j4": pose[3],
                "gripper": pose[4],
                "duration": duration,
                "dry_run": dry_run,
            }
        )

    def _validate_pose(self, pose):
        if not self.validate_limits:
            return True

        names = ["j1", "j2", "j3", "j4", "gripper"]

        for name, value in zip(names, pose):
            low, high = self.joint_limits[name]

            if not low <= value <= high:
                print(
                    f"[ROBOT] {name} out of range: "
                    f"{value} not in [{low}, {high}]"
                )
                return False

        return True

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

        if "joint" in obj and obj["joint"] is not None:
            joint = obj["joint"]

            if isinstance(joint, (list, tuple)) and len(joint) >= 5:
                return list(joint[:5])

        if "qrst" in obj and obj["qrst"] is not None:
            qrst = obj["qrst"]

            if isinstance(qrst, dict):
                names = ["q", "r", "s", "t", "gripper"]

                if all(name in qrst for name in names):
                    return [qrst[name] for name in names]

        if "angle" in obj:
            angle = obj["angle"]

            if isinstance(angle, (list, tuple)) and len(angle) >= 5:
                return list(angle[:5])

        required_keys = ["j1", "j2", "j3", "j4", "gripper"]

        if all(key in obj for key in required_keys):
            return [
                obj["j1"],
                obj["j2"],
                obj["j3"],
                obj["j4"],
                obj["gripper"],
            ]

        return None

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
        yolo_world = self._as_object_list(yolo_world)
        obj_name = self._canonical_object_name(obj_name)

        for item in yolo_world:
            name = self._canonical_object_name(item.get("name", ""))

            if name == obj_name:
                return item

        return None

    def _canonical_object_name(self, name):
        name = str(name).strip().lower()
        name = name.replace("'s", "")
        name = " ".join(name.split())

        if "hand" in name:
            return "hand"

        if "bottle" in name:
            return "bottle"

        if "cup" in name or "mug" in name:
            return "cup"

        if "box" in name:
            return "box"

        if "basket" in name or "container" in name or name == "bin":
            return "basket"

        return name

    def _as_object_list(self, detections):
        if detections is None:
            return []

        if isinstance(detections, dict):
            return [detections]

        if isinstance(detections, list):
            return detections

        return []

    def _visual_servo_step(self, robot_uvd, obj_uvd):
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

        if pixel_error < 25 and depth_error < 0.05:
            return "success"

        return "need_feedback"

    # test
    def test(self):
        return {
            "running": self.running,
            "current_pose": self.current_pose.copy(),
            "calibration_pose_count": len(self.calibration_poses),
            "actions": sorted(self.get_available_actions().keys()),
        }


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("test")
    subparsers.add_parser("get_pose")

    move_parser = subparsers.add_parser("move_angle")
    move_parser.add_argument("j1", type=float)
    move_parser.add_argument("j2", type=float)
    move_parser.add_argument("j3", type=float)
    move_parser.add_argument("j4", type=float)
    move_parser.add_argument("--gripper", type=float, default=0.0)
    move_parser.add_argument("--duration", type=float, default=2.0)

    action_parser = subparsers.add_parser("action")
    action_parser.add_argument("action")
    action_parser.add_argument("--obj", default=None)

    args = parser.parse_args()
    robot = ROBOT()
    robot.launch()

    try:
        if args.command == "test":
            result = robot.test()
        elif args.command == "get_pose":
            result = robot.get_pose()
        elif args.command == "move_angle":
            result = robot.move_angle(
                args.j1,
                args.j2,
                args.j3,
                args.j4,
                gripper=args.gripper,
                duration=args.duration,
            )
        else:
            result = robot.action({"name": args.action, "obj": args.obj})

        print(json.dumps(result, ensure_ascii=False))
    finally:
        robot.close()


if __name__ == "__main__":
    main()
