from .regression_model import RegressionModel as UVDRegressionModel
from .calibration_poses import DEFAULT_CALIBRATION_POSES
from .calibration_main import (
    CalibrationModel,
    CalibrationModelService,
    create_calibration_model,
)

def collect_calibration_samples(*args, **kwargs):
    from .collect_calibration_samples import collect_calibration_samples as collect

    return collect(*args, **kwargs)


__all__ = [
    "CalibrationModel",
    "CalibrationModelService",
    "DEFAULT_CALIBRATION_POSES",
    "UVDRegressionModel",
    "collect_calibration_samples",
    "create_calibration_model",
]
