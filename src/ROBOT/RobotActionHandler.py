class RobotActionHandler:
    """
    Executes robot action sequences serially.

    ProjectController decides what should happen.
    RobotActionHandler only performs robot-side actions and reports results.
    """

    def __init__(self, robot, rgbd_cam=None, interface=None):
        self.robot = robot
        self.rgbd_cam = rgbd_cam
        self.interface = interface

    def run_sequence(self, action_sequence):
        results = []

        for action in action_sequence or []:
            result = self.robot.action(action, self.rgbd_cam)
            results.append(
                {
                    "action": action,
                    "result": result,
                }
            )

            if self.interface is not None:
                self.interface.update(action_result=result)

            if result in ["failed", "unsafe"]:
                break

        return results


__all__ = ["RobotActionHandler"]
