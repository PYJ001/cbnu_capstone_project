import time

from collect_calibration_samples import collect_calibration_samples


class RobotCommandController:
    def __init__(
        self,
        robot,
        llm_planner,
        rgbd_cam,
        interface,
        vlm_updater,
        latest_vlm,
        latest_vlm_lock,
        stop_event,
    ):
        self.robot = robot
        self.llm_planner = llm_planner
        self.rgbd_cam = rgbd_cam
        self.interface = interface
        self.vlm_updater = vlm_updater
        self.latest_vlm = latest_vlm
        self.latest_vlm_lock = latest_vlm_lock
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            user_command = self.interface.get_user_command()

            if user_command.lower() in ["quit", "exit", "q"]:
                print("[RobotCommandController] quit")
                break

            if self._is_recalibration_command(user_command):
                self._run_recalibration(user_command)
                continue

            self._run_user_command(user_command)

        self.stop_event.set()
        self.interface.close()

    def _run_user_command(self, user_command):
        camera_data = self.interface.get_latest_camera_data()

        if camera_data is None:
            print("[RobotCommandController] camera data is not ready")
            return

        yolo_robot = camera_data["yolo_robot"]
        yolo_world = camera_data["yolo_world"]

        with self.latest_vlm_lock:
            vlm_summary = self.latest_vlm["summary"]

        print(f"[RobotCommandController] yolo_world : {yolo_world}")

        action_sequence, result_text = self.llm_planner.inference(
            user_command=user_command,
            vlm_summary=vlm_summary,
            yolo_robot=yolo_robot,
            yolo_world=yolo_world,
        )

        self.interface.update(
            user_command=user_command,
            vlm_summary=vlm_summary,
            print_out=result_text,
            result_text=result_text,
            action_sequence=action_sequence,
            action_result="ready",
        )

        for action in action_sequence:
            result = self.robot.action(action, self.interface)

            self.interface.update(action_result=result)

            if result in ["failed", "unsafe"]:
                print(f"[RobotCommandController] action result: {result}")
                print("[RobotCommandController] stop remaining actions")
                break

    def _run_recalibration(self, user_command):
        self.interface.update(
            user_command=user_command,
            print_out="Recalibration started.",
            action_sequence=[],
            action_result="running",
        )

        previous_yolo_world_enabled = self.rgbd_cam.is_yolo_world_enabled()
        previous_calibration_prediction_enabled = (
            self.rgbd_cam.is_calibration_prediction_enabled()
        )

        self.vlm_updater.pause()
        self.rgbd_cam.set_yolo_world_enabled(False)
        self.rgbd_cam.set_calibration_prediction_enabled(False)

        try:
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
            print(f"[RobotCommandController] {result_text}")
            self.interface.update(
                print_out=result_text,
                action_result="success",
            )
        except Exception as e:
            result_text = f"Recalibration failed: {e}"
            print(f"[RobotCommandController] {result_text}")
            self.interface.update(
                print_out=result_text,
                action_result="failed",
            )
        finally:
            self.rgbd_cam.set_calibration_prediction_enabled(
                previous_calibration_prediction_enabled
            )
            self.rgbd_cam.set_yolo_world_enabled(previous_yolo_world_enabled)
            self.vlm_updater.resume()

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

    def _is_recalibration_command(self, user_command):
        return user_command.lower() in [
            "recalibration",
            "recalibrate",
            "recallibration",
        ]
