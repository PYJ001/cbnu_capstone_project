#!/usr/bin/python3

import argparse
import sys

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool


DEFAULT_TORQUE_SERVICE = 'dynamixel_hardware_interface/set_dxl_torque'


class MotorFreeClient(Node):
    def __init__(self, service_name=DEFAULT_TORQUE_SERVICE):
        super().__init__('motor_free_client')
        self.service_name = service_name
        self.client = self.create_client(SetBool, service_name)

    def send_request(self, torque_enabled, timeout_sec=5.0):
        if not self.client.wait_for_service(timeout_sec=float(timeout_sec)):
            self.get_logger().error(
                f'torque service is not available: {self.service_name}'
            )
            return False

        request = SetBool.Request()
        request.data = bool(torque_enabled)

        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is None:
            self.get_logger().error('torque service call failed')
            return False

        response = future.result()

        if response.success:
            state = 'locked' if torque_enabled else 'free'
            self.get_logger().info(f'motor state: {state}. {response.message}')
        else:
            self.get_logger().error(f'torque service rejected request: {response.message}')

        return bool(response.success)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            'Disable Dynamixel torque so joints can be moved by hand while '
            '/joint_states and joint_control get_pose remain available.'
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--free',
        action='store_true',
        help='Disable torque. This is the default.',
    )
    group.add_argument(
        '--lock',
        action='store_true',
        help='Enable torque again.',
    )
    parser.add_argument(
        '--service',
        default=DEFAULT_TORQUE_SERVICE,
        help='SetBool torque service name.',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=5.0,
        help='Seconds to wait for the torque service.',
    )
    return parser.parse_args(argv)


def main(args=None):
    parsed = parse_args(sys.argv[1:])
    torque_enabled = bool(parsed.lock)

    rclpy.init(args=args)
    node = MotorFreeClient(service_name=parsed.service)

    try:
        success = node.send_request(
            torque_enabled=torque_enabled,
            timeout_sec=parsed.timeout,
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()

    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()
