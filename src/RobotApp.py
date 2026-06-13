import threading

from src.RGBD_CAM    import RGBDService
from src.LLM_PLANNER import LLMPlannerService
from src.ROBOT       import RobotService

from src.ProjectController import ProjectController
from src.INTERFACE   import Interface

class RobotApp:
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

    def __init__(self):
#        camera_backend     = "realsense"
#        rgb_camera_index   = "/dev/video6"
#        depth_camera_index = 0

        ##################################################################
        # robot       : Controller for robot. includes and handler.
        # llm_planner : Orchestrates the input from the interface and RGBD
        #               camera and generates the command for the robot. 
        # rgbd_cam    : Camera module. It uses YOLO and VLM model.  
        #               returns the data for the llm_planner.
        # interface   : Interface. uses mike, speaker, pyQt5, keyboard and mouse
        ##################################################################



        # Core services. These are created once and owned by RobotApp.
        self.rgbd_cam           = RGBDService()
        self.llm_planner        = LLMPlannerService()
        self.robot              = RobotService()

        # interface
        self.interface          = Interface()
        #project_controller
        self.shutdown_event = threading.Event()
        self.project_controller = ProjectController(
            robot       = self.robot,
            llm_planner = self.llm_planner,
            rgbd_cam    = self.rgbd_cam,
            interface   = self.interface,
            stop_event  = self.shutdown_event,
        )

    ######################################################################
    # Intended data flow
    ######################################################################
    #
    # 1. Interface receives a text/voice/shortcut command.
    #    - PyQt callback puts it into interface.command_queue.
    #
    # 2. ProjectController wakes up.
    #    - command = interface.get_user_command(timeout=...)
    #    - camera_data = interface.get_latest_camera_data()
    #      or rgbd_cam.get_frame() if a fresh blocking snapshot is required.
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
    # 4. RobotActionHandler executes actions serially.
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

            self.interface.start_camera_stream(self.rgbd_cam)
            self.project_controller.launch()
            return self.interface.run()


        finally:
            self.close()

    def close(self):
        """
        Stop every service owned by RobotApp.
        """
        self.shutdown_event.set()

        self.project_controller.join(timeout=1.0)
        self.interface.close()

        self.robot.close()
        self.llm_planner.close()
        self.rgbd_cam.close()
