"""
Project-level orchestrator.

ProjectController is the message router between packages:
- receives user commands from Interface
- requests perception snapshots from RGBD
- asks LLMPlanner for action sequences
- sends action sequences to ROBOT
- delegates recalibration flow to CALIBRATION
- publishes state/results back to Interface
"""

import threading
import time
import sys
from pathlib import Path

try:
    from src.CALIBRATION import CalibrationModelService
    from src.RGBD_CAM.VLM import VLM
    from src.RGBD_CAM.YoloRobot import YoloRobot
    from src.RGBD_CAM.YoloWorld import YoloWorld
except ImportError:
    project_root = Path(__file__).resolve().parents[1]

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.CALIBRATION import CalibrationModelService
    from src.RGBD_CAM.VLM import VLM
    from src.RGBD_CAM.YoloRobot import YoloRobot
    from src.RGBD_CAM.YoloWorld import YoloWorld


class ProjectController:
    def __init__(
        self,
        robot,
        llm_planner,
        rgbd_cam,
        interface,
        calibration_model = None,
        stop_event        = None,
    ):
        self.robot             = robot
        self.llm_planner       = llm_planner
        self.rgbd_cam          = rgbd_cam
        self.interface         = interface
        self.calibration_model = calibration_model or CalibrationModelService()
        self.stop_event        = stop_event or threading.Event()

        self.vlm        = None
        self.yolo_robot = None
        self.yolo_world = None
        self.thread = None

    # lifecycle
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

    # orchestration loop
    def main_loop(self):
        while not self.stop_event.is_set():
            user_command = self._receive_interface_command(timeout=0.1)

            if user_command is None:
                continue

            self._route_interface_command(user_command)

    def _receive_interface_command(self, timeout=0.1):
        user_command = self.interface.get_user_command(timeout=timeout)

        if user_command is None:
            return None

        user_command = str(user_command).strip()

        if user_command == "":
            return None

        return user_command

    def _route_interface_command(self, user_command):
        if self._is_quit_command(user_command):
            self._handle_quit_command()
            return

        if self._is_perception_command(user_command):
            self._handle_perception_command(user_command)
            return

        if self._is_recalibration_command(user_command):
            self._handle_recalibration_command(user_command)
            return

        self._handle_user_task_command(user_command)

    # command handlers
    def _handle_quit_command(self):
        self.stop()
        self.interface.close()

    def _handle_user_task_command(self, user_command):
        self._publish_interface_state(
            user_command=user_command,
            print_out="Perception and planning started.",
            result_text="Perception and planning started.",
            action_result="running",
        )

        perception_data = self._request_fresh_perception_data(
            user_command=user_command,
        )

        if perception_data is None:
            self._publish_interface_state(
                user_command=user_command,
                print_out="Perception data is not ready.",
                result_text="Perception data is not ready.",
                action_sequence=[],
                action_result="failed",
            )
            return

        self._publish_rgbd_frame(perception_data)

        action_sequence, print_out = self._request_llm_plan(
            user_command=user_command,
            perception_data=perception_data,
        )

        self._publish_interface_state(
            user_command=user_command,
            vlm_summary=perception_data.get("vlm_summary", ""),
            print_out=print_out,
            result_text=print_out,
            action_sequence=action_sequence,
            action_result="ready",
        )

        robot_results = self._command_robot(
            action_sequence,
            perception_data=perception_data,
        )
        final_result = self._make_final_result(robot_results)
        action_result = self._format_robot_execution_result(
            robot_results=robot_results,
            final_result=final_result,
        )
        self._publish_interface_state(
            action_result=action_result,
        )
        return action_sequence

    def _handle_recalibration_command(self, user_command):
        current_user_command = self._get_current_user_command()
        self._publish_interface_state(
            user_command    = current_user_command or user_command,
            print_out       = "Recalibration started.",
            result_text     = "Recalibration started.",
            action_sequence = [],
            action_result   = "running",
        )

        if self.calibration_model is None:
            result_text = "Recalibration failed: calibration model is not available."
            self._publish_interface_state(
                print_out=result_text,
                result_text=result_text,
                action_result="failed",
            )
            return False

        try:
            calibration_data = self.calibration_model.run_recalibration(
                robot=self.robot,
                rgbd_cam=self.rgbd_cam,
                capture_callback=self._capture_calibration_robot_detection,
                cycles=1,
                move_duration=8.0,
                settle_time=1.0,
                sample_hz=5.0,
                max_samples_per_pose=None,
                max_attempts_per_pose=None,
                min_uv_distance=0.0,
                sample_while_moving=True,
                min_robot_conf=0.45,
                return_home=True,
            )
        except Exception as exc:
            result_text = f"Recalibration failed: {exc}"
            print(f"[ProjectController] {result_text}")
            self._publish_interface_state(
                print_out=result_text,
                result_text=result_text,
                action_result="failed",
            )
            return False

        if not isinstance(calibration_data, dict):
            result_text = f"Recalibration failed: invalid result {calibration_data}"
            self._publish_interface_state(
                print_out=result_text,
                result_text=result_text,
                action_result="failed",
            )
            return False

        status = calibration_data.get("status", "unknown")
        csv_path = calibration_data.get("csv_path")
        model_loaded = calibration_data.get("model_loaded")

        if status != "success" or not model_loaded:
            result_text = (
                "Recalibration failed: "
                f"status={status}, model_loaded={model_loaded}, csv={csv_path}"
            )
            self._publish_interface_state(
                print_out=result_text,
                result_text=result_text,
                action_result="failed",
            )
            return False

        result_text = (
            "Recalibration complete.\n"
            f"- CSV: {csv_path}\n"
            f"- Model loaded: {model_loaded}"
        )
        self._publish_interface_state(
            print_out=result_text,
            result_text=result_text,
            action_sequence=[],
            action_result="success",
        )
        return True

    def _handle_perception_command(self, user_command):
        current_user_command = self._get_current_user_command()
        self._publish_interface_state(
            print_out="Perception inference started.",
            result_text="Perception inference started.",
            action_result="running",
        )

        perception_data = self._request_fresh_perception_data(
            user_command=current_user_command,
        )

        if perception_data is None:
            self._publish_interface_state(
                print_out="Perception inference failed.",
                result_text="Perception inference failed.",
                action_result="failed",
            )
            return

        self._publish_rgbd_frame(perception_data)
        self._publish_interface_state(
            vlm_summary=perception_data.get("vlm_summary", ""),
            print_out=self._format_perception_result(perception_data),
            result_text=self._format_perception_result(perception_data),
            action_result="success",
        )

    # package requests
    def _request_latest_rgbd_frame(self):
        try:
            if hasattr(self.rgbd_cam, "get_latest_rgbd_frame"):
                return self.rgbd_cam.get_latest_rgbd_frame()

            return self.rgbd_cam.get_latest_camera_data()
        except Exception as exc:
            print(f"[ProjectController] latest RGBD frame request failed: {exc}")
            return None

    def _request_perception_data(self):
        return self._request_fresh_perception_data(
            user_command=self._get_current_user_command(),
        )

    def _request_fresh_perception_data(self, user_command=""):
        rgbd_frame = self._request_latest_rgbd_frame()

        if rgbd_frame is None:
            rgbd_frame = self._capture_rgbd_frame()

        if rgbd_frame is None:
            return None

        frame = rgbd_frame.get("frame")
        depth = rgbd_frame.get("depth")

        try:
            vlm_result = self._run_vlm(frame, user_command=user_command)
            yolo_robot = self._run_yolo_robot(frame, depth)
            yolo_world = self._run_yolo_world(
                frame=frame,
                depth=depth,
                vlm_objects=vlm_result.get("objects", []),
            )
            yolo_robot, yolo_world = self._apply_calibration(
                yolo_robot=yolo_robot,
                yolo_world=yolo_world,
            )

            return {
                "frame": frame,
                "depth": depth,
                "yolo_robot": yolo_robot,
                "yolo_world": yolo_world,
                "vlm_summary": vlm_result.get("summary", ""),
                "vlm_objects": vlm_result.get("objects", []),
                "yolo_world_classes": self.yolo_world.get_classes(),
            }

        except Exception as exc:
            print(f"[ProjectController] fresh perception request failed: {exc}")
            return None

    def _run_vlm(self, frame, user_command=""):
        if self.vlm is None:
            self.vlm = VLM()

        return self.vlm.inference(
            frame=frame,
            user_command=user_command,
        )

    def _run_yolo_robot(self, frame, depth):
        if self.yolo_robot is None:
            self.yolo_robot = YoloRobot()

        return self.yolo_robot.inference(frame, depth)

    def _run_yolo_world(self, frame, depth, vlm_objects):
        if self.yolo_world is None:
            self.yolo_world = YoloWorld()

        self.yolo_world.add_classes_from_vlm(vlm_objects)
        return self.yolo_world.inference(frame, depth)

    def _apply_calibration(self, yolo_robot, yolo_world):
        if self.calibration_model is None:
            return yolo_robot, yolo_world

        if yolo_robot is not None:
            calibrated_robot = self.calibration_model.uvd2qrst_objs(yolo_robot)
            yolo_robot = calibrated_robot[0] if calibrated_robot else yolo_robot

        yolo_world = self.calibration_model.uvd2qrst_objs(yolo_world)
        return yolo_robot, yolo_world

    def _capture_calibration_robot_detection(self):
        rgbd_frame = self._request_latest_rgbd_frame()

        if rgbd_frame is None:
            rgbd_frame = self._capture_rgbd_frame()

        if rgbd_frame is None:
            raise RuntimeError("camera data is not ready")

        frame = rgbd_frame.get("frame")
        depth = rgbd_frame.get("depth")
        yolo_robot = self._run_yolo_robot(frame, depth)

        self._publish_rgbd_frame(
            {
                "frame": frame,
                "depth": depth,
                "yolo_robot": yolo_robot,
                "yolo_world": [],
                "vlm_summary": "",
                "vlm_objects": [],
            }
        )

        return frame, depth, yolo_robot

    def _request_llm_plan(self, user_command, perception_data):
        return self.llm_planner.inference(
            user_command=user_command,
            vlm_summary=perception_data.get("vlm_summary", ""),
            yolo_robot=perception_data.get("yolo_robot"),
            yolo_world=perception_data.get("yolo_world"),
        )

    def _select_calibration_target(self, perception_data):
        yolo_world = perception_data.get("yolo_world") or []

        if isinstance(yolo_world, dict):
            yolo_world = [yolo_world]

        for obj in yolo_world:
            if not isinstance(obj, dict):
                continue

            joint = obj.get("joint")

            if self._is_valid_joint(joint):
                return obj

        return None

    def _is_valid_joint(self, joint):
        if not isinstance(joint, (list, tuple)):
            return False

        if len(joint) < 5:
            return False

        try:
            [float(value) for value in joint[:5]]
            return True
        except Exception:
            return False

    def _command_robot(self, action_sequence, perception_data=None):
        return self.robot.run_sequence(
            action_sequence,
            camera_data=perception_data,
            interface=self.interface,
        )

    def _request_latest_robot_detection(self, timeout=2.0):
        deadline = time.time() + timeout

        while time.time() < deadline:
            perception_data = self._request_perception_data()

            if perception_data is not None:
                self._publish_rgbd_frame(perception_data)
                return (
                    perception_data["frame"],
                    perception_data["depth"],
                    perception_data["yolo_robot"],
                )

            time.sleep(0.03)

        raise RuntimeError("camera data is not ready")

    # Interface publishing
    def _publish_rgbd_frame(self, rgbd_frame):
        self.interface.update(rgbd_data=rgbd_frame)

    def _publish_interface_state(self, **kwargs):
        return self.interface.update(**kwargs)

    # functional tests
    def test(self, duration=None, hz=10.0, close_on_finish=True):
        """
        ProjectController integration test.

        This method is intentionally callable from RobotApp.__init__:
            self.project_controller.test()

        It launches RGBD and Interface, then streams RGBD camera data to PyQt
        through ProjectController until the user quits. If duration is given,
        the test stops after that many seconds.
        """
        try:
            self._launch_test_modules()
            return self.test_rgbd_interface(duration=duration, hz=hz)
        except KeyboardInterrupt:
            self.stop()
            return False
        finally:
            if close_on_finish:
                self._close_test_modules()

    def test_rgbd_interface(self, duration=None, hz=10.0):
        """
        Stream RGBD camera data into Interface/PyQt through ProjectController.

        Checklist target:
        RGBD -> ProjectController -> Interface -> PyQt5 display
        """
        started_at = time.time()
        tick = 0
        interval = 1.0 / max(float(hz), 1.0)

        self._publish_interface_state(
            print_out="RGBD to Interface test started.",
            action_result="running",
        )

        while not self.stop_event.is_set():
            elapsed = time.time() - started_at

            if duration is not None and elapsed >= float(duration):
                break

            self._handle_test_interface_command()

            if self.stop_event.is_set():
                break

            tick += 1
            rgbd_frame = self._request_latest_rgbd_frame()

            if rgbd_frame is None:
                rgbd_frame = self._capture_rgbd_frame()

            if rgbd_frame is None:
                self._publish_interface_state(
                    print_out=(
                        "RGBD to Interface test waiting for camera data "
                        f"tick={tick}"
                    ),
                    action_result="waiting",
                )
                time.sleep(interval)
                continue

            self._publish_rgbd_frame(rgbd_frame)
            time.sleep(interval)

        if duration is not None:
            self._publish_interface_state(
                print_out="RGBD to Interface test complete.",
                action_result="success",
            )

        return True

    def _handle_test_interface_command(self):
        user_command = self._receive_interface_command(timeout=0)

        if user_command is None:
            return None

        if self._is_quit_command(user_command):
            self._handle_quit_command()
            return user_command

        if self._is_recalibration_command(user_command):
            self._handle_recalibration_command(user_command)
            return user_command

        if self._is_perception_command(user_command):
            self._handle_perception_command(user_command)
            return user_command

        self._handle_user_task_command(user_command)
        return user_command

    def _capture_rgbd_frame(self):
        try:
            if hasattr(self.rgbd_cam, "capture_rgbd_frame"):
                result = self.rgbd_cam.capture_rgbd_frame()
            elif hasattr(self.rgbd_cam, "get_camera_data"):
                result = self.rgbd_cam.get_camera_data()
            else:
                result = self.rgbd_cam.run()

            if isinstance(result, dict):
                return result

            if isinstance(result, tuple) and len(result) >= 4:
                return {
                    "frame": result[0],
                    "depth": result[1],
                    "yolo_robot": result[2],
                    "yolo_world": result[3],
                    "vlm_summary": "",
                    "vlm_objects": [],
                }

            return self._request_latest_rgbd_frame()
        except Exception as exc:
            print(f"[ProjectController] RGBD frame capture failed: {exc}")
            return None

    def _launch_test_modules(self):
        if hasattr(self.rgbd_cam, "launch"):
            self.rgbd_cam.launch()

        if hasattr(self.interface, "launch"):
            self.interface.launch(self.rgbd_cam)

    def _close_test_modules(self):
        for module in [
            self.interface,
            self.rgbd_cam,
        ]:
            if hasattr(module, "close"):
                module.close()

    # result helpers
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

    def _is_perception_command(self, user_command):
        return user_command.lower() in [
            "perception_inference",
            "inference",
            "detect",
        ]

    def _format_perception_result(self, perception_data):
        yolo_robot = perception_data.get("yolo_robot")
        yolo_world = perception_data.get("yolo_world") or []
        vlm_summary = perception_data.get("vlm_summary", "")

        return (
            "Perception inference complete. "
            f"robot={yolo_robot is not None}, "
            f"world_count={len(yolo_world)}, "
            f"vlm={vlm_summary[:120]}"
        )

    def _format_task_result(
        self,
        perception_data,
        planner_print_out,
        action_sequence,
    ):
        yolo_robot = perception_data.get("yolo_robot")
        yolo_world = perception_data.get("yolo_world") or []
        vlm_summary = perception_data.get("vlm_summary", "")
        vlm_objects = perception_data.get("vlm_objects", [])

        yolo_world_names = [
            str(item.get("name", ""))
            for item in yolo_world
            if isinstance(item, dict) and str(item.get("name", "")) != ""
        ]

        return (
            "Perception result\n"
            f"- VLM summary: {vlm_summary}\n"
            f"- VLM objects: {vlm_objects}\n"
            f"- YOLO robot: {yolo_robot}\n"
            f"- YOLO world: {yolo_world_names}\n"
            "\n"
            "Planner result\n"
            f"- Response: {planner_print_out}\n"
            f"- Action Sequence: {action_sequence}"
        )

    def _format_calibration_move_result(self, target_obj, qrst, joint, status):
        name = target_obj.get("name", "object")
        u = target_obj.get("u")
        v = target_obj.get("v")
        d = target_obj.get("d")

        return (
            "Calibration move "
            f"{status}\n"
            f"- Target: {name}\n"
            f"- UVD: u={u}, v={v}, d={d}\n"
            f"- QRST: {qrst}\n"
            f"- Joint: {joint}"
        )

    def _format_robot_execution_result(
        self,
        robot_results,
        final_result,
    ):
        return (
            f"- Result: {final_result}\n"
            f"- Steps: {robot_results}"
        )

    def _get_current_user_command(self):
        if hasattr(self.interface, "get_current_user_command"):
            return self.interface.get_current_user_command()

        state = getattr(self.interface, "state", {})
        return state.get("user_command", "")


class _NoopRobot:
    def run_sequence(self, action_sequence, rgbd_cam=None, interface=None):
        return []


class _NoopLLMPlanner:
    def inference(self, **kwargs):
        return [], "LLM planner is not used in this test."


def main():
    import argparse

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    rgbd_parser = subparsers.add_parser("rgbd_interface")
    rgbd_parser.add_argument("--duration", type=float, default=None)
    rgbd_parser.add_argument("--hz", type=float, default=10.0)
    rgbd_parser.add_argument("--camera-backend", default="realsense")
    rgbd_parser.add_argument("--hide-window", action="store_true")

    args = parser.parse_args()

    if args.command == "rgbd_interface":
        from src.INTERFACE.interface_main import Interface
        from src.RGBD_CAM.rgbd_cam_main import RGBD

        rgbd_cam = RGBD(camera_backend=args.camera_backend)
        interface = Interface(show_window=not args.hide_window)
        controller = ProjectController(
            robot=_NoopRobot(),
            llm_planner=_NoopLLMPlanner(),
            rgbd_cam=rgbd_cam,
            interface=interface,
        )

        controller.test(
            duration=args.duration,
            hz=args.hz,
        )


if __name__ == "__main__":
    main()
