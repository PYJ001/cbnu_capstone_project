import copy
import importlib.util
import sys
from pathlib import Path

try:
    from .regression_model import RegressionModel as UVDRegressionModel
except ImportError:
    calibration_path = Path(__file__).resolve().with_name("regression_model.py")
    spec = importlib.util.spec_from_file_location(
        "_calibration_uvd_model",
        calibration_path,
    )
    calibration_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calibration_module)
    UVDRegressionModel = calibration_module.RegressionModel


class CalibrationModel:
    """
    RobotApp-facing calibration package entry point.

    CalibrationModel does not own camera or robot objects. ProjectController passes
    robot/camera callbacks when recalibration needs physical movement.
    """

    def __init__(
        self,
        csv_path=None,
        search_dir="src/CALIBRATION/robot_camera_calibration_samples",
        k=1,
        camera_intrinsics=None,
        auto_load=True,
    ):
        self.csv_path = csv_path
        self.search_dir = search_dir
        self.k = k
        self.camera_intrinsics = camera_intrinsics or {}
        self.model = None
        self.last_calibration_data = None

        if auto_load:
            self.reload()

    def launch(self):
        return True

    def close(self):
        return True

    def run(self, *args, **kwargs):
        return self.calibrate(*args, **kwargs)

    def record_teleoperation_poses(self, robot, **kwargs):
        try:
            from .teleoperation_recorder import record_teleoperation_poses
        except ImportError:
            project_root = Path(__file__).resolve().parents[2]

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from src.CALIBRATION.teleoperation_recorder import (
                record_teleoperation_poses,
            )

        return record_teleoperation_poses(robot=robot, **kwargs)

    def load_teleoperation_poses(self, path):
        try:
            from .teleoperation_recorder import load_teleoperation_poses
        except ImportError:
            project_root = Path(__file__).resolve().parents[2]

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from src.CALIBRATION.teleoperation_recorder import (
                load_teleoperation_poses,
            )

        return load_teleoperation_poses(path)

    def run_recalibration(
        self,
        robot,
        rgbd_cam,
        capture_callback,
        **kwargs,
    ):
        previous_yolo_world_enabled = self._safe_call(
            rgbd_cam,
            "is_yolo_world_enabled",
            default=None,
        )
        previous_calibration_prediction_enabled = self._safe_call(
            rgbd_cam,
            "is_calibration_prediction_enabled",
            default=None,
        )

        try:
            self._safe_call(rgbd_cam, "set_yolo_world_enabled", False)
            self._safe_call(rgbd_cam, "set_calibration_prediction_enabled", False)

            calibration_data = self.calibrate(
                robot=robot,
                capture_callback=capture_callback,
                **kwargs,
            )

            if hasattr(rgbd_cam, "set_calibration_model"):
                rgbd_cam.set_calibration_model(self)

            return calibration_data

        finally:
            if previous_calibration_prediction_enabled is not None:
                self._safe_call(
                    rgbd_cam,
                    "set_calibration_prediction_enabled",
                    previous_calibration_prediction_enabled,
                )

            if previous_yolo_world_enabled is not None:
                self._safe_call(
                    rgbd_cam,
                    "set_yolo_world_enabled",
                    previous_yolo_world_enabled,
                )

    def calibrate(self, robot=None, capture_callback=None, **kwargs):
        """
        Recalibration entry point.

        Current intended flow:
        1. ProjectController disables world inference/calibration prediction.
        2. ProjectController passes robot and RGBD capture callback here.
        3. collect_calibration_samples moves robot through calibration poses.
        4. A fresh CalibrationModel is loaded from the returned csv.
        """
        if robot is None or capture_callback is None:
            self.last_calibration_data = {
                "status": "skipped",
                "csv_path": None,
                "message": (
                    "robot and capture_callback are required for physical "
                    "recalibration"
                ),
                "pseudocode": [
                    "robot.move_angle(test_angle)",
                    "frame, depth, yolo_robot = capture_callback()",
                    "save robot joint pose with detected robot u/v/d",
                    "reload calibration model from saved csv",
                ],
            }
            return self.last_calibration_data

        csv_path = self._collect_calibration_samples(
            robot=robot,
            rgbd_cam=None,
            capture_callback=capture_callback,
            **kwargs,
        )

        self.reload(csv_path=csv_path)
        self.last_calibration_data = {
            "status": "success",
            "csv_path": str(csv_path),
            "model_loaded": self.model is not None,
        }
        return self.last_calibration_data

    def reload(self, csv_path=None, search_dir=None, k=None):
        if csv_path is not None:
            self.csv_path = csv_path

        if search_dir is not None:
            self.search_dir = search_dir

        if k is not None:
            self.k = k

        try:
            self.model = UVDRegressionModel.from_latest_or_path(
                csv_path=self.csv_path,
                search_dir=self.search_dir,
                k=self.k,
            )
            self.csv_path = Path(self.model.csv_path)
            print(f"[CalibrationModel] model loaded: {self.csv_path}")
        except Exception as exc:
            self.model = None
            print(f"[CalibrationModel] model disabled: {exc}")

        return self.model

    def uvd2qrst(self, u=None, v=None, d=None, obj=None):
        if obj is not None:
            u = obj.get("u", u)
            v = obj.get("v", v)
            d = obj.get("d", d)

        if u is None or v is None:
            return None

        if self.model is None:
            return None

        try:
            prediction = self.model.predict(u, v, d)
        except Exception as exc:
            print(f"[CalibrationModel] uvd2qrst failed: {exc}")
            return None

        return self._format_qrst(prediction)

    def uvd2xyz(self, u=None, v=None, d=None, obj=None):
        if obj is not None:
            u = obj.get("u", u)
            v = obj.get("v", v)
            d = obj.get("d", d)

        if u is None or v is None or d is None:
            return None

        fx = self.camera_intrinsics.get("fx")
        fy = self.camera_intrinsics.get("fy")
        cx = self.camera_intrinsics.get("cx")
        cy = self.camera_intrinsics.get("cy")

        if None in [fx, fy, cx, cy]:
            return {
                "x": None,
                "y": None,
                "z": float(d),
                "u": float(u),
                "v": float(v),
                "pseudocode": "set camera intrinsics to compute metric xyz",
            }

        z = float(d)
        x = (float(u) - float(cx)) * z / float(fx)
        y = (float(v) - float(cy)) * z / float(fy)
        return {"x": x, "y": y, "z": z}

    def uvd2qrst_objs(self, yolo_detected_objects):
        if yolo_detected_objects is None:
            return []

        if isinstance(yolo_detected_objects, dict):
            objects = [yolo_detected_objects]
        else:
            objects = list(yolo_detected_objects)

        calibrated_objects = []

        for obj in objects:
            if not isinstance(obj, dict):
                calibrated_objects.append(obj)
                continue

            item = copy.deepcopy(obj)
            qrst = self.uvd2qrst(obj=item)
            xyz = self.uvd2xyz(obj=item)

            item["qrst"] = qrst
            item["joint"] = self._qrst_to_joint_tuple(qrst)
            item["xyz"] = xyz
            calibrated_objects.append(item)

        return calibrated_objects

    def test(self, robot=None, test_angle=None, target_uvd=None):
        """
        Pseudocode test hook until ROBOT main is finalized.
        """
        if test_angle is None:
            test_angle = [0.0, -0.5, 0.8, -0.3, 0.0]

        result = {
            "status": "pseudocode",
            "steps": [
                f"move robot to angle: {test_angle}",
                "capture robot marker/object with RGBD",
                "run uvd2qrst on measured u/v/d",
                "compare predicted q/r/s/t with robot.get_pose()",
            ],
            "target_uvd": target_uvd,
        }

        if robot is not None and hasattr(robot, "move_angle"):
            result["robot_call"] = "robot.move_angle(test_angle)"

        if target_uvd is not None:
            result["predicted_qrst"] = self.uvd2qrst(
                target_uvd.get("u"),
                target_uvd.get("v"),
                target_uvd.get("d"),
            )

        print(f"[CalibrationModel TEST] {result}")
        return result

    def _format_qrst(self, prediction):
        values = list(prediction)
        names = ["q", "r", "s", "t", "gripper"]
        return {
            name: float(values[index])
            for index, name in enumerate(names)
            if index < len(values)
        }

    def _qrst_to_joint_tuple(self, qrst):
        if qrst is None:
            return None

        return tuple(
            qrst.get(name)
            for name in ["q", "r", "s", "t", "gripper"]
            if name in qrst
        )

    def _collect_calibration_samples(self, *args, **kwargs):
        try:
            from .collect_calibration_samples import collect_calibration_samples
        except ImportError:
            project_root = Path(__file__).resolve().parents[2]

            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from src.CALIBRATION.collect_calibration_samples import (
                collect_calibration_samples,
            )

        return collect_calibration_samples(*args, **kwargs)

    def _safe_call(self, obj, method_name, *args, default=None, **kwargs):
        if obj is None or not hasattr(obj, method_name):
            return default

        try:
            return getattr(obj, method_name)(*args, **kwargs)
        except Exception:
            return default


CalibrationModelService = CalibrationModel


def create_calibration_model():
    return CalibrationModel()


def main():
    calibration_model = CalibrationModel()
    print("[CalibrationModel TEST] launch:", calibration_model.launch())
    print(
        "[CalibrationModel TEST] uvd2xyz:",
        calibration_model.uvd2xyz(u=320, v=240, d=0.5),
    )
    print(
        "[CalibrationModel TEST] uvd2qrst:",
        calibration_model.uvd2qrst(u=320, v=240, d=0.5),
    )
    print(
        "[CalibrationModel TEST] uvd2qrst_objs:",
        calibration_model.uvd2qrst_objs([
            {"name": "sample", "u": 320, "v": 240, "d": 0.5}
        ]),
    )
    calibration_model.test(target_uvd={"u": 320, "v": 240, "d": 0.5})
    calibration_model.close()


if __name__ == "__main__":
    main()
