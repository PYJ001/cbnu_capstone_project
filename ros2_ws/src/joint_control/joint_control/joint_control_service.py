#!/usr/bin/python3

from control_msgs.action import GripperCommand
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint

from joint_control.srv import GetPose, MoveJoint


class JointControlService(Node):
    def __init__(self):
        super().__init__('joint_control_service')

        self.arm_joint_names = ['joint1', 'joint2', 'joint3', 'joint4']
        self.gripper_joint_names = [
            'rh_r1_joint',
            'gripper_left_joint',
            'gripper_joint_1',
        ]

        self.limits = {
            'j1': (-3.14, 3.14),
            'j2': (-3.14, 3.14),
            'j3': (-3.14, 3.14),
            'j4': (-3.14, 3.14),
            'gripper': (-0.05, 0.05),
        }

        self.current_pose = {
            'j1': 0.0,
            'j2': 0.0,
            'j3': 0.0,
            'j4': 0.0,
            'gripper': 0.0,
        }
        self.received_joint_state = False

        self.arm_publisher = self.create_publisher(
            JointTrajectory,
            '/arm_controller/joint_trajectory',
            10,
        )

        self.gripper_client = ActionClient(
            self,
            GripperCommand,
            '/gripper_controller/gripper_cmd',
        )

        self.create_subscription(
            JointState,
            '/joint_states',
            self.joint_state_callback,
            10,
        )

        self.get_pose_service = self.create_service(
            GetPose, 'get_pose', self.get_pose_callback)

        self.move_joint_service = self.create_service(
            MoveJoint, 'move_joint', self.move_joint_callback)

        self.get_logger().info('Joint Control Service started')
        self.get_logger().info('arm command topic: /arm_controller/joint_trajectory')
        self.get_logger().info('gripper action: /gripper_controller/gripper_cmd')

    def joint_state_callback(self, msg):
        for pose_name, joint_name in zip(
            ['j1', 'j2', 'j3', 'j4'],
            self.arm_joint_names,
        ):
            if joint_name in msg.name:
                self.current_pose[pose_name] = msg.position[msg.name.index(joint_name)]

        for joint_name in self.gripper_joint_names:
            if joint_name in msg.name:
                self.current_pose['gripper'] = msg.position[msg.name.index(joint_name)]
                break

        self.received_joint_state = True

    def get_pose_callback(self, request, response):
        if not self.received_joint_state:
            self.get_logger().warn(
                'No /joint_states received yet; returning last known default pose.'
            )

        response.j1 = float(self.current_pose['j1'])
        response.j2 = float(self.current_pose['j2'])
        response.j3 = float(self.current_pose['j3'])
        response.j4 = float(self.current_pose['j4'])
        response.gripper = float(self.current_pose['gripper'])

        return response

    def move_joint_callback(self, request, response):
        target_positions = [
            float(request.j1),
            float(request.j2),
            float(request.j3),
            float(request.j4),
        ]

        gripper_position = float(request.gripper)
        duration = float(request.duration)

        if duration <= 0.0:
            duration = 1.0

        if not self.gripper_client.wait_for_server(timeout_sec=0.1):
            self.get_logger().error(
                'Gripper action server is not available: '
                '/gripper_controller/gripper_cmd'
            )
            response.success = False
            return response

        self.publish_arm_command(target_positions, duration)
        self.send_gripper_command(gripper_position)

        self.get_logger().info(
            f'Move command sent: j1={target_positions[0]:.6f}, '
            f'j2={target_positions[1]:.6f}, '
            f'j3={target_positions[2]:.6f}, '
            f'j4={target_positions[3]:.6f}, '
            f'gripper={gripper_position:.6f}, duration={duration:.3f}s'
        )

        response.success = True
        return response

    def publish_arm_command(self, positions, duration):
        msg = JointTrajectory()
        msg.joint_names = self.arm_joint_names

        point = JointTrajectoryPoint()
        point.positions = positions

        sec = int(duration)
        point.time_from_start.sec = sec
        point.time_from_start.nanosec = int((duration - sec) * 1_000_000_000)

        msg.points.append(point)
        self.arm_publisher.publish(msg)

    def send_gripper_command(self, position):
        goal_msg = GripperCommand.Goal()
        goal_msg.command.position = position
        goal_msg.command.max_effort = 10.0

        future = self.gripper_client.send_goal_async(goal_msg)
        future.add_done_callback(self.gripper_goal_response_callback)

    def gripper_goal_response_callback(self, future):
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f'Failed to send gripper command: {exc}')
            return

        if not goal_handle.accepted:
            self.get_logger().error('Gripper command was rejected.')
            return

        self.get_logger().info('Gripper command was accepted.')

    def is_safe_range(self, values):
        return all(
            self.limits[name][0] <= value <= self.limits[name][1]
            for name, value in values.items()
        )


def main(args=None):
    rclpy.init(args=args)
    service = JointControlService()

    try:
        rclpy.spin(service)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        service.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
