_RobotApp_description = """
    RobotApp is the process/service manager for the whole robot system.

    Treat this class like a small ROS-style runtime:

    - Owns long-lived modules:
      robot, llm_planner, rgbd_cam, interface.
    - Starts/stops service loops:
      interface GUI loop, camera stream loop, LLM planning loop,
      and robot command execution loop.
    - Controls data flow between modules:
      interface input -> perception snapshot -> LLM plan -> robot action
      -> interface feedback.
    - Keeps slow/blocking work away from the PyQt UI thread.

    The modules should not directly drive each other in random places.
    RobotApp should be the single place where queues, threads, shutdown,
    and cross-module ownership are coordinated.
    """


    ######################################################################
    # Intended data flow
    ######################################################################
    #
    # 1. Interface receives a text/voice/shortcut command.
    #    - PyQt callback puts it into interface.command_queue.
    #
    # 2. ProjectController wakes up.
    #    - command = interface.get_user_command(timeout=...)
    #    - rgbd_frame = rgbd_cam.get_latest_rgbd_frame()
    #      or rgbd_cam.capture_rgbd_frame() for a fresh blocking UI frame.
    #    - perception_data = project_controller requests VLM/YOLO when needed.
    #    - Extract:
    #        vlm_summary
    #        yolo_robot
    #        yolo_world
    #
    # 3. LLMPlanner runs like a service.
    #    - action_sequence, print_out = llm_planner.inference(...)
    #    - Interface is updated with user command, detections, plan,
    #      and natural language response.
    #
    # 4. robot_main.ROBOT executes actions serially.
    #    - Robot movement must be one-at-a-time.
    #    - For each action in action_sequence:
    #        robot.action(action, rgbd_cam=rgbd_cam)
    #    - Feedback-based actions such as GRB can keep using rgbd_cam.
    #
    # 5. Interface receives final result.
    #    - action_result/result_text is pushed to interface.update().
    #
    # Shutdown order should be:
    #   set shutdown_event
    #   stop accepting UI/camera work
    #   join planner/robot threads
    #   close RGBD camera
    #   close Interface/TTS/Qt
    ######################################################################


import threading

from src.CALIBRATION.calibration_main import CalibrationModel
from src.INTERFACE.interface_main      import Interface
from src.LLM_PLANNER.llm_planner_main  import LLMPlanner
from src.ProjectController             import ProjectController
from src.RGBD_CAM.rgbd_cam_main        import RGBD
from src.ROBOT.robot_main              import ROBOT

class RobotApp:

    def __init__(self):
#        camera_backend     = "realsense"
#        rgb_camera_index   = "/dev/video6"
#        depth_camera_index = 0

        self.rgbd_cam           = RGBD()
        self.llm_planner        = LLMPlanner()
        self.robot              = ROBOT()
        self.calibration_model  = CalibrationModel()
        
        self.interface          = Interface()
        self.shutdown_event     = threading.Event()
        self.project_controller = ProjectController(
            robot             = self.robot,
            llm_planner       = self.llm_planner,
            rgbd_cam          = self.rgbd_cam,
            interface         = self.interface,
            calibration_model = self.calibration_model,
            stop_event        = self.shutdown_event,
        )
        # RGBD -> ProjectController -> Interface/PyQt functional test.
        # self.project_controller.test()

    def test(self, duration=None, hz=10.0):
        return self.project_controller.test(duration=duration, hz=hz)

    def run(self):
        """
        Start the application runtime.
        PyQt must stay on the main thread. ProjectController runs in a
        background thread and consumes Interface commands.
        """
        try:
            self.rgbd_cam.launch()
            self.llm_planner.launch()
            self.robot.launch()
            self.calibration_model.launch()

            self.interface.launch(self.rgbd_cam)
            self.project_controller.launch()
            self.interface.run()

        except KeyboardInterrupt:
            print("[RobotApp] interrupted. Shutting down.")

        finally:
            self.close()

    def close(self):
        self.shutdown_event.set()

        self.project_controller.join(timeout=1.0)
        self.interface.close()

        self.robot.close()
        self.llm_planner.close()
        self.calibration_model.close()
        self.rgbd_cam.close()
