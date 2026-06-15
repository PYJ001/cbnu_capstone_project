#!/usr/bin/python3

import os
import sys

import rclpy
from rclpy.node import Node

from joint_control.srv import GetPose, MoveJoint


class MoveJointClient(Node):
    def __init__(self):
        super().__init__('move_joint_client')
        self.client = self.create_client(MoveJoint, 'move_joint')

    def send_request(self, j1, j2, j3, j4, gripper, duration):
        if not self.client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error('move_joint service is not available')
            return False

        request = MoveJoint.Request()
        request.j1 = float(j1)
        request.j2 = float(j2)
        request.j3 = float(j3)
        request.j4 = float(j4)
        request.gripper = float(gripper)
        request.duration = float(duration)

        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is None:
            self.get_logger().error('service call failed')
            return False

        return future.result().success


class GetPoseClient(Node):
    def __init__(self):
        super().__init__('get_pose_client')
        self.client = self.create_client(GetPose, 'get_pose')

    def send_request(self):
        if not self.client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error('get_pose service is not available')
            return None

        request = GetPose.Request()
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is None:
            self.get_logger().error('service call failed')
            return None

        return future.result()


def print_move_usage():
    print('Usage:')
    print('  ros2 run joint_control move_joint <j1> <j2> <j3> <j4> <gripper> <duration>')
    print()
    print('Note: values are actual joint positions, not percentages.')
    print('  j1/j2/j3/j4 in radians, gripper in meters')
    print('  j1 range: -3.14..3.14')
    print('  j2/j3/j4 range: -1.5..1.5')
    print('  gripper range: -0.01..0.019')
    print('Example:')
    print('  ros2 run joint_control move_joint 0.5 -0.3 1.0 -1.0 0.01 2.0')


def print_get_pose_usage():
    print('Usage:')
    print('  ros2 run joint_control get_pose')


def main(args=None):
    program_name = os.path.basename(sys.argv[0])
    if program_name == 'get_pose':
        if len(sys.argv) != 1:
            print_get_pose_usage()
            return

        rclpy.init(args=args)
        node = GetPoseClient()

        try:
            response = node.send_request()
            if response is not None:
                print(f'j1: {response.j1}')
                print(f'j2: {response.j2}')
                print(f'j3: {response.j3}')
                print(f'j4: {response.j4}')
                print(f'gripper: {response.gripper}')
        finally:
            node.destroy_node()
            rclpy.shutdown()

    else:
        if len(sys.argv) != 7:
            print_move_usage()
            return

        rclpy.init(args=args)
        node = MoveJointClient()

        try:
            success = node.send_request(
                sys.argv[1],
                sys.argv[2],
                sys.argv[3],
                sys.argv[4],
                sys.argv[5],
                sys.argv[6],
            )

            if success:
                node.get_logger().info('move_joint succeeded')
            else:
                node.get_logger().error('move_joint failed')

        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    main()
