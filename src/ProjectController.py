import threading
import time

from src.CALIBRATION import collect_calibration_samples
from src.ROBOT import RobotActionHandler


class ProjectController:
    """
    Coordinates the project-level control flow.

    This is the central application controller:
    - receives commands from Interface
    - reads the latest RGBD/perception state
    - asks LLMPlanner for an action plan
    - delegates physical execution to RobotActionHandler
    - reports state/results back to Interface
    """

    def __init__(
        self,
        robot,
        llm_planner,
        rgbd_cam,
        interface,
        stop_event=None,
    ):
        self.robot = robot
        self.llm_planner = llm_planner
        self.rgbd_cam = rgbd_cam
        self.interface = interface
        self.stop_event = stop_event or threading.Event()

        self.robot_action_handler = RobotActionHandler(
            robot=self.robot,
            rgbd_cam=self.rgbd_cam,
            interface=self.interface,
        )

        self.thread = None

    def launch(self):
        if self.thread is not None and self.thread.is_alive():
            return

        self.thread = threading.Thread(
            target=self.main_loop,
            daemon=True,
        )
        self.thread.start()

    def join(self, timeout=None):
        if self.thread is not None:
            self.thread.join(timeout=timeout)

    def stop(self):
        self.stop_event.set()

    def main_loop(self):
        while not self.stop_event.is_set():
            user_command = self.interface.get_user_command(timeout=0.1)

            if user_command is None:
                continue

            user_command = str(user_command).strip()

            if user_command == "":
                continue

            if self._is_quit_command(user_command):
                self.stop()
                self.interface.close()
                break

            if self._is_recalibration_command(user_command):
                self._run_recalibration(user_command)
                continue

            self._run_user_command(user_command)

    def _run_user_command(self, user_command):
        camera_data = self.interface.get_latest_camera_data()

        if camera_data is None:
            self.interface.update(
                user_command=user_command,
                print_out="Camera data is not ready.",
                result_text="Camera data is not ready.",
                action_sequence=[],
                action_result="failed",
            )
            return

        yolo_robot = camera_data.get("yolo_robot")
        yolo_world = camera_data.get("yolo_world")
        vlm_summary = camera_data.get("vlm_summary", "")

        action_sequence, print_out = self.llm_planner.inference(
            user_command=user_command,
            vlm_summary=vlm_summary,
            yolo_robot=yolo_robot,
            yolo_world=yolo_world,
        )

        self.interface.update(
            user_command=user_command,
            vlm_summary=vlm_summary,
            print_out=print_out,
            result_text=print_out,
            action_sequence=action_sequence,
            action_result="ready",
        )

        results = self.robot_action_handler.run_sequence(
            action_sequence,
            camera_data={
                "yolo_robot": yolo_robot,
                "yolo_world": yolo_world,
            },
        )
        final_result = self._make_final_result(results)
        self.interface.update(action_result=final_result)

    def _run_recalibration(self, user_command):
        self.interface.update(
            user_command=user_command,
            print_out="Recalibration started.",
            result_text="Recalibration started.",
            action_sequence=[],
            action_result="running",
        )

        previous_yolo_world_enabled = self.rgbd_cam.is_yolo_world_enabled()
        previous_calibration_prediction_enabled = (
            self.rgbd_cam.is_calibration_prediction_enabled()
        )

        try:
            self.rgbd_cam.set_yolo_world_enabled(False)
            self.rgbd_cam.set_calibration_prediction_enabled(False)

            csv_path = collect_calibration_samples(
                robot=self.robot,
                rgbd_cam=self.rgbd_cam,
                cycles=1,
                move_duration=4.0,
                sample_hz=5.0,
                return_home=True,
                capture_callback=self._get_latest_robot_detection,
            )
            self.rgbd_cam.calibration_model = self.rgbd_cam._load_calibration_model()

            result_text = f"Recalibration complete: {csv_path}"
            self.interface.update(
                print_out=result_text,
                result_text=result_text,
                action_result="success",
            )

        except Exception as e:
            result_text = f"Recalibration failed: {e}"
            self.interface.update(
                print_out=result_text,
                result_text=result_text,
                action_result="failed",
            )

        finally:
            self.rgbd_cam.set_calibration_prediction_enabled(
                previous_calibration_prediction_enabled
            )
            self.rgbd_cam.set_yolo_world_enabled(previous_yolo_world_enabled)

    def _get_latest_robot_detection(self, timeout=2.0):
        deadline = time.time() + timeout

        while time.time() < deadline:
            camera_data = self.interface.get_latest_camera_data()

            if camera_data is not None:
                return (
                    camera_data["frame"],
                    camera_data["depth"],
                    camera_data["yolo_robot"],
                )

            time.sleep(0.03)

        raise RuntimeError("camera data is not ready")

    def _make_final_result(self, results):
        if len(results) == 0:
            return "no_action"

        last_result = results[-1]["result"]

        if last_result in ["failed", "unsafe"]:
            return last_result

        return "success"

    def _is_quit_command(self, user_command):
        return user_command.lower() in ["quit", "exit", "q"]

    def _is_recalibration_command(self, user_command):
        return user_command.lower() in [
            "recalibration",
            "recalibrate",
            "recallibration",
        ]
