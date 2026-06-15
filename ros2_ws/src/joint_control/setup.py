from setuptools import setup

package_name = 'joint_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    install_requires=['setuptools'],
    entry_points={
        'console_scripts': [
            'joint_control_service = joint_control.joint_control_service:main',
            'move_joint = joint_control.joint_control_client:main',
            'motor_free = joint_control.motor_free:main',
            'open_manipulator_x_teleop_xyz = joint_control.joint_control_xyz_teleop:main',
        ],
    },
)
