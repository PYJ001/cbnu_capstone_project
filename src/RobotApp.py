import threading

from src.interface_pyqt5        import Interface
from src.LLM_planner            import LLMPlanner
from src.RGBD                   import RGBD
from src.RobotCommandController import RobotCommandController
from src.RobotManager           import ROBOT
from src.VLMWorldClassUpdater   import VLMWorldClassLoop, VLMWorldClassUpdater


class RobotApp:
    def __init__(self):
        self.robot       = ROBOT()
        self.llm_planner = LLMPlanner()
        self.rgbd_cam    = RGBD()
        self.interface   = Interface()
        self.vlm_updater = VLMWorldClassUpdater(interval=3.0)

        self.latest_vlm = {
            "summary": "",
            "objects": [],
        }
        self.latest_vlm_lock = threading.Lock()
        self.stop_event      = threading.Event()

        self.vlm_loop = VLMWorldClassLoop(
            interface       = self.interface,
            rgbd_cam        = self.rgbd_cam,
            vlm_updater     = self.vlm_updater,
            latest_vlm      = self.latest_vlm,
            latest_vlm_lock = self.latest_vlm_lock,
            stop_event      = self.stop_event,
        )
        self.command_controller = RobotCommandController(
            robot           = self.robot,
            llm_planner     = self.llm_planner,
            rgbd_cam        = self.rgbd_cam,
            interface       = self.interface,
            vlm_updater     = self.vlm_updater,
            latest_vlm      = self.latest_vlm,
            latest_vlm_lock = self.latest_vlm_lock,
            stop_event      = self.stop_event,
        )

        self.vlm_worker     = None
        self.command_worker = None

    def run(self):
        self.interface.start_camera_stream(self.rgbd_cam)
        self.vlm_updater.start()

        self.vlm_worker = threading.Thread(
            target = self.vlm_loop.run,
            daemon = True,
        )
        self.command_worker = threading.Thread(
            target = self.command_controller.run,
            daemon = True,
        )

        self.vlm_worker.start()
        self.command_worker.start()

        try:
            self.interface.run()
        finally:
            self.close()

    def close(self):
        self.stop_event.set()
        self.interface.close()
        self.vlm_updater.close()
        self.rgbd_cam.close()

        if self.vlm_worker is not None:
            self.vlm_worker.join(timeout=1.0)

        if self.command_worker is not None:
            self.command_worker.join(timeout=1.0)
