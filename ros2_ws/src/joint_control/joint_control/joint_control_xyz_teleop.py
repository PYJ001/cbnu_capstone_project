#!/usr/bin/python3

import math
import select
import sys
import termios
import threading
import time
import tty

import numpy as np

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from control_msgs.action import GripperCommand
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint


# ============================================================
# OpenMANIPULATOR-X local IK keyboard controller
#
# 외부 IK 서비스 사용 안 함.
# MoveIt 사용 안 함.
# /compute_ik 사용 안 함.
# robot_description 사용 안 함.
#
# 이 파일 안의 OpenManipulatorXKinematics.solve_ik()가 IK 구현입니다.
# ============================================================


# ============================================================
# ROS 설정
# ============================================================

ARM_TOPIC = "/arm_controller/joint_trajectory"
JOINT_STATES_TOPIC = "/joint_states"
GRIPPER_ACTION = "/gripper_controller/gripper_cmd"

ARM_JOINT_NAMES = ["joint1", "joint2", "joint3", "joint4"]


# ============================================================
# OpenMANIPULATOR-X 기구학 파라미터
# 단위: meter, radian
#
# chain:
# world/base
#   -> joint1
#   -> joint2
#   -> joint3
#   -> joint4
#   -> tool/end-effector
#
# joint1 axis: z
# joint2~4 axis: y
# ============================================================

JOINT_ORIGINS = [
    np.array([0.012, 0.000, 0.017], dtype=float),   # joint1 origin
    np.array([0.000, 0.000, 0.0595], dtype=float),  # joint2 origin
    np.array([0.024, 0.000, 0.128], dtype=float),   # joint3 origin
    np.array([0.124, 0.000, 0.000], dtype=float),   # joint4 origin
]

TOOL_OFFSET = np.array([0.126, 0.000, 0.000], dtype=float)

JOINT_AXES = [
    np.array([0.0, 0.0, 1.0], dtype=float),  # joint1
    np.array([0.0, 1.0, 0.0], dtype=float),  # joint2
    np.array([0.0, 1.0, 0.0], dtype=float),  # joint3
    np.array([0.0, 1.0, 0.0], dtype=float),  # joint4
]

JOINT_LIMITS = [
    (-math.pi, math.pi),   # joint1
    (-2.050, 1.571),       # joint2
    (-1.571, 1.530),       # joint3
    (-1.800, 2.000),       # joint4
]


# ============================================================
# 안전 작업공간
# 처음에는 보수적으로 잡았습니다.
# 바닥 긁힘 방지를 위해 z 최소값을 높게 둡니다.
# ============================================================

X_MIN = 0.09
X_MAX = 0.36

Y_MIN = -0.30
Y_MAX = 0.30

Z_MIN = 0.04
Z_MAX = 0.32

PITCH_MIN = math.radians(-80.0)
PITCH_MAX = math.radians(80.0)


# ============================================================
# 조작 속도
# ============================================================

XYZ_DELTA = 0.004
PITCH_DELTA = math.radians(2.0)

TRAJECTORY_DURATION = 0.6
COMMAND_INTERVAL = 0.08

GRIPPER_MIN = -0.01
GRIPPER_MAX = 0.019
GRIPPER_DELTA = 0.002


# ============================================================
# IK 튜닝
# ============================================================

IK_MAX_ITER = 120
IK_DAMPING = 0.04

IK_POS_TOL = 0.006
IK_PITCH_TOL = math.radians(5.0)

IK_MAX_STEP = 0.06

# pitch보다 xyz 위치를 더 중요하게 둡니다.
IK_POSITION_WEIGHT = 1.0
IK_PITCH_WEIGHT = 0.25


# ============================================================
# 수학 유틸
# ============================================================

def clamp(value, low, high):
    return max(low, min(high, value))


def clamp_joint_vector(q):
    q = np.array(q, dtype=float)

    for i, (low, high) in enumerate(JOINT_LIMITS):
        q[i] = clamp(q[i], low, high)

    return q


def wrap_angle(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi

    while angle < -math.pi:
        angle += 2.0 * math.pi

    return angle


def rotation_about_axis(axis, angle):
    axis = np.array(axis, dtype=float)
    norm = np.linalg.norm(axis)

    if norm < 1e-9:
        return np.eye(3)

    axis = axis / norm
    x, y, z = axis

    c = math.cos(angle)
    s = math.sin(angle)
    v = 1.0 - c

    return np.array([
        [x * x * v + c,     x * y * v - z * s, x * z * v + y * s],
        [y * x * v + z * s, y * y * v + c,     y * z * v - x * s],
        [z * x * v - y * s, z * y * v + x * s, z * z * v + c],
    ], dtype=float)


def make_transform(rotation=None, translation=None):
    transform = np.eye(4)

    if rotation is not None:
        transform[:3, :3] = rotation

    if translation is not None:
        transform[:3, 3] = translation

    return transform


def transform_from_origin_and_joint(origin, axis, q):
    t_origin = make_transform(translation=origin)
    r_joint = make_transform(rotation=rotation_about_axis(axis, q))

    return t_origin @ r_joint


def extract_pitch_from_rotation(rotation):
    """
    end-effector x축 방향이 수평면보다 얼마나 위/아래를 보는지 계산합니다.

    + pitch: tool x축이 위쪽
    - pitch: tool x축이 아래쪽
    """

    x_axis = rotation[:3, 0]
    horizontal = math.sqrt(x_axis[0] ** 2 + x_axis[1] ** 2)

    return math.atan2(x_axis[2], horizontal)


# ============================================================
# OpenMANIPULATOR-X FK / IK
# ============================================================

class OpenManipulatorXKinematics:

    def __init__(self):
        pass

    def forward_kinematics(self, q):
        """
        입력:
            q = [joint1, joint2, joint3, joint4]

        출력:
            position: [x, y, z]
            pitch: tool x축 기준 pitch
            transform: 4x4 homogeneous transform
        """

        q = np.array(q, dtype=float)

        transform = np.eye(4)

        for i in range(4):
            transform = transform @ transform_from_origin_and_joint(
                JOINT_ORIGINS[i],
                JOINT_AXES[i],
                q[i],
            )

        transform = transform @ make_transform(translation=TOOL_OFFSET)

        position = transform[:3, 3].copy()
        pitch = extract_pitch_from_rotation(transform[:3, :3])

        return position, pitch, transform

    def task_vector(self, q):
        position, pitch, _ = self.forward_kinematics(q)

        return np.array([
            position[0],
            position[1],
            position[2],
            pitch,
        ], dtype=float)

    def error_vector(self, target, current):
        error = target - current
        error[3] = wrap_angle(error[3])
        return error

    def numerical_jacobian(self, q):
        jacobian = np.zeros((4, 4), dtype=float)
        eps = 1e-4

        for j in range(4):
            q_plus = q.copy()
            q_minus = q.copy()

            q_plus[j] += eps
            q_minus[j] -= eps

            f_plus = self.task_vector(q_plus)
            f_minus = self.task_vector(q_minus)

            diff = (f_plus - f_minus) / (2.0 * eps)
            diff[3] = wrap_angle(diff[3])

            jacobian[:, j] = diff

        return jacobian

    def one_ik_attempt(self, target, seed_q):
        q = clamp_joint_vector(seed_q)

        best_q = q.copy()
        best_error_score = float("inf")
        best_pos_error = float("inf")
        best_pitch_error = float("inf")

        weight = np.diag([
            IK_POSITION_WEIGHT,
            IK_POSITION_WEIGHT,
            IK_POSITION_WEIGHT,
            IK_PITCH_WEIGHT,
        ])

        for _ in range(IK_MAX_ITER):
            current = self.task_vector(q)
            error = self.error_vector(target, current)

            pos_error = np.linalg.norm(error[:3])
            pitch_error = abs(error[3])

            error_score = pos_error + 0.03 * pitch_error

            if error_score < best_error_score:
                best_error_score = error_score
                best_pos_error = pos_error
                best_pitch_error = pitch_error
                best_q = q.copy()

            if pos_error <= IK_POS_TOL and pitch_error <= IK_PITCH_TOL:
                return q.tolist(), True, pos_error, pitch_error

            jacobian = self.numerical_jacobian(q)

            weighted_jacobian = weight @ jacobian
            weighted_error = weight @ error

            jt = weighted_jacobian.T

            # Damped Least Squares:
            # dq = J^T (J J^T + lambda^2 I)^-1 e
            lhs = weighted_jacobian @ jt + (IK_DAMPING ** 2) * np.eye(4)
            rhs = weighted_error

            try:
                dq = jt @ np.linalg.solve(lhs, rhs)
            except np.linalg.LinAlgError:
                dq = jt @ np.linalg.pinv(lhs) @ rhs

            dq = np.clip(dq, -IK_MAX_STEP, IK_MAX_STEP)

            # 너무 작은 업데이트면 더 진행해도 의미가 적음
            if np.linalg.norm(dq) < 1e-6:
                break

            q = q + dq
            q = clamp_joint_vector(q)

        return best_q.tolist(), False, best_pos_error, best_pitch_error

    def make_seed_list(self, current_q, target_x, target_y):
        """
        IK가 local minimum에 빠질 수 있어서 seed를 여러 개 시도합니다.
        첫 번째 seed는 현재 관절값입니다.
        """

        yaw = math.atan2(target_y, target_x)

        seeds = []

        current_q = clamp_joint_vector(current_q)
        seeds.append(current_q)

        # 유저님이 이전에 기준으로 삼았던 안전 자세 계열
        seeds.append(np.array([yaw, -1.000155, 1.000155, 0.0], dtype=float))

        # 일반적인 elbow 후보
        seeds.append(np.array([yaw, -0.7, 0.9, 0.0], dtype=float))
        seeds.append(np.array([yaw, -0.9, 1.2, 0.2], dtype=float))
        seeds.append(np.array([yaw, -0.5, 0.8, -0.3], dtype=float))
        seeds.append(np.array([yaw, -1.2, 1.4, 0.3], dtype=float))

        # 반대 elbow 후보
        seeds.append(np.array([yaw, 0.3, -0.8, 0.4], dtype=float))
        seeds.append(np.array([yaw, 0.5, -1.0, 0.6], dtype=float))

        return [clamp_joint_vector(seed) for seed in seeds]

    def solve_ik(self, target_x, target_y, target_z, target_pitch, current_q):
        """
        실제 IK 함수입니다.

        입력:
            target_x, target_y, target_z, target_pitch
            current_q = 현재 joint1~4

        출력:
            joints, success, info
        """

        target = np.array([
            target_x,
            target_y,
            target_z,
            target_pitch,
        ], dtype=float)

        seeds = self.make_seed_list(current_q, target_x, target_y)

        best_joints = None
        best_success = False
        best_pos_error = float("inf")
        best_pitch_error = float("inf")
        best_score = float("inf")

        for seed in seeds:
            joints, success, pos_error, pitch_error = self.one_ik_attempt(
                target=target,
                seed_q=seed,
            )

            score = pos_error + 0.03 * pitch_error

            if score < best_score:
                best_score = score
                best_joints = joints
                best_success = success
                best_pos_error = pos_error
                best_pitch_error = pitch_error

            if success:
                break

        info = {
            "pos_error": best_pos_error,
            "pitch_error": best_pitch_error,
            "score": best_score,
        }

        return best_joints, best_success, info


# ============================================================
# Keyboard Controller
# ============================================================

class KeyboardXYZPitchLocalIK(Node):

    def __init__(self):
        super().__init__("keyboard_xyz_pitch_local_ik")

        self.arm_joint_names = ARM_JOINT_NAMES
        self.arm_joint_positions = [0.0, 0.0, 0.0, 0.0]

        self.gripper_position = 0.0

        self.joint_received = False
        self.running = True

        self.kinematics = OpenManipulatorXKinematics()

        self.arm_publisher = self.create_publisher(
            JointTrajectory,
            ARM_TOPIC,
            10,
        )

        self.joint_sub = self.create_subscription(
            JointState,
            JOINT_STATES_TOPIC,
            self.joint_state_callback,
            10,
        )

        self.gripper_client = ActionClient(
            self,
            GripperCommand,
            GRIPPER_ACTION,
        )

        self.target_x = 0.20
        self.target_y = 0.00
        self.target_z = 0.18
        self.target_pitch = 0.0

        self.target_initialized_from_current_pose = False

        self.last_command_time = time.time()

        self.get_logger().info("Node created.")
        self.get_logger().info("Local IK is implemented inside this file.")
        self.get_logger().info("No external IK service is used.")

    def joint_state_callback(self, msg):
        if set(self.arm_joint_names).issubset(set(msg.name)):
            for i, joint_name in enumerate(self.arm_joint_names):
                idx = msg.name.index(joint_name)
                self.arm_joint_positions[i] = msg.position[idx]

            if not self.joint_received:
                self.joint_received = True
                self.get_logger().info(
                    "Initial joint states: "
                    f"{[round(v, 4) for v in self.arm_joint_positions]}"
                )

        if "rh_r1_joint" in msg.name:
            idx = msg.name.index("rh_r1_joint")
            self.gripper_position = msg.position[idx]

    def get_key(self, timeout=0.01):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)

            if rlist:
                return sys.stdin.read(1)

            return None

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def wait_for_joint_states(self):
        wait_count = 0

        while rclpy.ok() and self.running and not self.joint_received:
            rclpy.spin_once(self, timeout_sec=0.2)
            wait_count += 1

            if wait_count % 10 == 0:
                self.get_logger().warn("Waiting for /joint_states...")

            if wait_count >= 50:
                self.get_logger().error("/joint_states가 들어오지 않습니다.")
                return False

        return True

    def initialize_target_from_current_pose(self):
        """
        시작할 때 로봇을 갑자기 움직이지 않게,
        현재 joint state의 FK 결과를 target xyz/pitch로 사용합니다.
        """

        position, pitch, _ = self.kinematics.forward_kinematics(
            self.arm_joint_positions
        )

        self.target_x = clamp(float(position[0]), X_MIN, X_MAX)
        self.target_y = clamp(float(position[1]), Y_MIN, Y_MAX)
        self.target_z = clamp(float(position[2]), Z_MIN, Z_MAX)
        self.target_pitch = clamp(float(pitch), PITCH_MIN, PITCH_MAX)

        self.target_initialized_from_current_pose = True

        self.get_logger().info(
            "Initial target is set from current FK: "
            f"x={self.target_x:.3f}, "
            f"y={self.target_y:.3f}, "
            f"z={self.target_z:.3f}, "
            f"pitch={math.degrees(self.target_pitch):.1f} deg"
        )

    def update_target_by_key(self, key):
        if key == "1":
            self.target_x += XYZ_DELTA
        elif key == "q":
            self.target_x -= XYZ_DELTA

        elif key == "2":
            self.target_y += XYZ_DELTA
        elif key == "w":
            self.target_y -= XYZ_DELTA

        elif key == "3":
            self.target_z += XYZ_DELTA
        elif key == "e":
            self.target_z -= XYZ_DELTA

        elif key == "4":
            self.target_pitch += PITCH_DELTA
        elif key == "r":
            self.target_pitch -= PITCH_DELTA

        self.target_x = clamp(self.target_x, X_MIN, X_MAX)
        self.target_y = clamp(self.target_y, Y_MIN, Y_MAX)
        self.target_z = clamp(self.target_z, Z_MIN, Z_MAX)
        self.target_pitch = clamp(self.target_pitch, PITCH_MIN, PITCH_MAX)

    def send_arm_command(self, joint_positions):
        msg = JointTrajectory()
        msg.joint_names = self.arm_joint_names

        point = JointTrajectoryPoint()
        point.positions = [float(v) for v in joint_positions]

        point.time_from_start.sec = int(TRAJECTORY_DURATION)
        point.time_from_start.nanosec = int(
            (TRAJECTORY_DURATION - int(TRAJECTORY_DURATION)) * 1e9
        )

        msg.points.append(point)
        self.arm_publisher.publish(msg)

        self.get_logger().info(
            "Arm command sent: "
            f"j1={joint_positions[0]:.3f}, "
            f"j2={joint_positions[1]:.3f}, "
            f"j3={joint_positions[2]:.3f}, "
            f"j4={joint_positions[3]:.3f}"
        )

    def send_gripper_command(self):
        goal_msg = GripperCommand.Goal()
        goal_msg.command.position = float(self.gripper_position)
        goal_msg.command.max_effort = 10.0

        if not self.gripper_client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warn("Gripper action server is not available.")
            return

        future = self.gripper_client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, future, timeout_sec=1.0)

        self.get_logger().info(
            f"Gripper command sent: {self.gripper_position:.4f}"
        )

    def command_current_target(self):
        joints, success, info = self.kinematics.solve_ik(
            target_x=self.target_x,
            target_y=self.target_y,
            target_z=self.target_z,
            target_pitch=self.target_pitch,
            current_q=self.arm_joint_positions,
        )

        if joints is None:
            self.get_logger().warn("IK returned no joint solution.")
            return

        if not success:
            self.get_logger().warn(
                "IK did not converge enough. Command skipped. "
                f"pos_error={info['pos_error']:.4f} m, "
                f"pitch_error={math.degrees(info['pitch_error']):.2f} deg, "
                f"target x={self.target_x:.3f}, "
                f"y={self.target_y:.3f}, "
                f"z={self.target_z:.3f}, "
                f"pitch={math.degrees(self.target_pitch):.1f} deg"
            )
            return

        self.send_arm_command(joints)

        fk_position, fk_pitch, _ = self.kinematics.forward_kinematics(joints)

        self.get_logger().info(
            "Target TCP: "
            f"x={self.target_x:.3f}, "
            f"y={self.target_y:.3f}, "
            f"z={self.target_z:.3f}, "
            f"pitch={math.degrees(self.target_pitch):.1f} deg | "
            "FK check: "
            f"x={fk_position[0]:.3f}, "
            f"y={fk_position[1]:.3f}, "
            f"z={fk_position[2]:.3f}, "
            f"pitch={math.degrees(fk_pitch):.1f} deg | "
            f"error={info['pos_error']:.4f} m"
        )

    def print_help(self):
        self.get_logger().info("")
        self.get_logger().info("========================================")
        self.get_logger().info("Keyboard XYZ/Pitch Local IK")
        self.get_logger().info("========================================")
        self.get_logger().info("1 / q : x + / x -")
        self.get_logger().info("2 / w : y + / y -")
        self.get_logger().info("3 / e : z + / z -")
        self.get_logger().info("4 / r : pitch + / pitch -")
        self.get_logger().info("o / p : gripper open / close")
        self.get_logger().info("ESC   : exit")
        self.get_logger().info("========================================")
        self.get_logger().info("")

    def run(self):
        if not self.wait_for_joint_states():
            self.running = False
            return

        self.initialize_target_from_current_pose()
        self.print_help()

        try:
            while rclpy.ok() and self.running:
                rclpy.spin_once(self, timeout_sec=0.0)

                key = self.get_key()
                now = time.time()

                if key is None:
                    continue

                if key == "\x1b":
                    self.running = False
                    break

                if now - self.last_command_time < COMMAND_INTERVAL:
                    continue

                if key in ["1", "q", "2", "w", "3", "e", "4", "r"]:
                    self.update_target_by_key(key)
                    self.command_current_target()

                elif key == "o":
                    self.gripper_position = min(
                        self.gripper_position + GRIPPER_DELTA,
                        GRIPPER_MAX,
                    )
                    self.send_gripper_command()

                elif key == "p":
                    self.gripper_position = max(
                        self.gripper_position - GRIPPER_DELTA,
                        GRIPPER_MIN,
                    )
                    self.send_gripper_command()

                self.last_command_time = now

        except Exception as e:
            self.get_logger().error(f"Exception in run loop: {e}")


def main(args=None):
    rclpy.init(args=args)

    node = KeyboardXYZPitchLocalIK()

    thread = threading.Thread(target=node.run)
    thread.start()

    try:
        while thread.is_alive():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down...")
        node.running = False
        thread.join()

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
