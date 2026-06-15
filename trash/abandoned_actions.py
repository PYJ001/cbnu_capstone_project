"""
Actions intentionally removed from the active RobotActions registry.

These are kept only as references for future restoration or rewriting.
"""


def wave_hand_action(robot):
    result = robot.actions._run_recorded_motion("wave_hand", speed=2.0)

    if result is not None:
        return result

    poses = [
        [0.0, -0.85, 1.05, -0.25, 0.0],
        [0.0, -0.75, 1.00, -0.35, 0.0],
        [0.0, -0.85, 1.05, -0.25, 0.0],
        [0.0, -0.75, 1.00, -0.35, 0.0],
        robot.base_pose,
    ]

    return robot.actions._run_pose_sequence(poses, duration=0.8, sleep=0.15)


def shake_hand_action(robot):
    return wave_hand_action(robot)


def WAV(robot):
    return wave_hand_action(robot)


def SKH(robot):
    return shake_hand_action(robot)
