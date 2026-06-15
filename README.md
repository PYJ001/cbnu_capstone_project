# CAPSTONE Robot Interface

OpenManipulatorX robot arm project with RGB-D perception, YOLO end-effector detection, YOLO-World object detection, VLM-guided class updates, LLM action planning, PyQt5 UI, TTS, calibration collection, and recorded motion replay.

## Main Entry

```bash
python3 main.py
```

`main.py` only starts `RobotApp`. Most logic lives inside `src/`.

## Code Analysis Package

The `code_analysis` package generates presentation-ready project summaries.

Run without installation:

```bash
python3 -m code_analysis
```

Generated files are written to `code_analysis_output/` by default:

```text
architecture_summary.md
presentation_material.md
project_analysis.md
project_analysis.json
project_report.md
project_tree.txt
```

Optional Ollama report generation:

```bash
python3 -m code_analysis --ollama
```

Editable install for CLI usage:

```bash
pip install -e .
code-analysis --root . --output-dir code_analysis_output
```

## Required Project Tree

```text
capstone_project/
├── main.py
├── collect_calibration_samples.py
├── test_record_motion.py
├── requirements.txt
├── README.md
│
├── yolov8s-worldv2.pt
│
├── runs/
│   └── end_effector_yolo12n_416_safe/
│       └── weights/
│           ├── best.pt
│           └── last.pt
│
├── src/
│   ├── __init__.py
│   ├── RobotApp.py
│   ├── RobotCommandController.py
│   ├── RobotManager.py
│   ├── robot_actions.py
│   ├── RGBD.py
│   ├── Calibration.py
│   ├── LLM.py
│   ├── LLM_planner.py
│   ├── VLM.py
│   ├── VLMWorldClassUpdater.py
│   ├── interface_pyqt5.py
│   ├── Interface.py
│   ├── TTS.py
│   ├── WhisperSTT.py
│   ├── MotionTrajectory.py
│   └── utils.py
│
├── robot_camera_calibration_samples/
│   └── <timestamp>/
│       ├── robot_camera_calibration_samples.csv
│       ├── calibration_report.json
│       ├── calibration_report.txt
│       └── uv_coverage.png
│
└── robot_motion_records/
    ├── heart/<timestamp>/motion.csv
    ├── dance/<timestamp>/motion.csv
    └── wave_hand/<timestamp>/motion.csv
```

## Important Files

```text
main.py
└── src/RobotApp.py
    ├── src/interface_pyqt5.py
    │   ├── src/Interface.py
    │   ├── src/TTS.py
    │   └── src/WhisperSTT.py
    ├── src/RGBD.py
    │   └── src/Calibration.py
    ├── src/RobotCommandController.py
    │   ├── collect_calibration_samples.py
    │   ├── src/LLM_planner.py
    │   │   ├── src/LLM.py
    │   │   └── src/robot_actions.py
    │   │       └── src/MotionTrajectory.py
    │   └── src/RobotManager.py
    └── src/VLMWorldClassUpdater.py
        └── src/VLM.py
```

## Model Weights

This project currently uses:

```text
yolov8s-worldv2.pt
runs/end_effector_yolo12n_416_safe/weights/best.pt
runs/end_effector_yolo12n_416_safe/weights/last.pt
```

Current weight sizes are below GitHub's 100 MB per-file limit, so they can be committed normally. If weights grow later, use Git LFS:

```bash
git lfs install
git lfs track "*.pt"
git add .gitattributes
```

## Python Environment

Recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

This project also requires:

```text
ROS 2 Jazzy
OpenManipulatorX control package providing:
  /move_joint service
  ros2 run joint_control get_pose
Ollama running locally
Ollama models:
  qwen2.5:7b-instruct
  qwen2.5vl:3b
RealSense SDK / pyrealsense2 for RGB-D camera
```

## Runtime Notes

The robot command layer expects:

```text
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
```

These are configured inside `src/RobotManager.py`.

## Calibration

From the PyQt interface, use the `Recalibration` button or command.

During calibration:

```text
VLM updater is paused
YOLO-World is disabled
Calibration prediction is disabled
Only RGB-D frame reading and end-effector YOLO run
```

Manual calibration script:

```bash
python3 collect_calibration_samples.py --move-duration 4.0 --sample-hz 5 --return-home
```

Calibration output includes:

```text
robot_camera_calibration_samples.csv
calibration_report.json
calibration_report.txt
uv_coverage.png
```

## Recorded Motions

Record teleoperated motion:

```bash
python3 test_record_motion.py --name heart --hz 5
python3 test_record_motion.py --name dance --hz 5
python3 test_record_motion.py --name wave_hand --hz 5
```

Replay:

```bash
python3 test_record_motion.py --replay robot_motion_records/heart/<timestamp>/motion.csv
```

`src/robot_actions.py` automatically uses the latest recorded trajectory if available. If no recording exists, it falls back to hard-coded poses.

## Suggested Copy Command

From the current project directory:

```bash
mkdir -p /home/thor/Projects/capstone_project
rsync -av \
  main.py collect_calibration_samples.py test_record_motion.py README.md requirements.txt \
  yolov8s-worldv2.pt \
  src \
  /home/thor/Projects/capstone_project/

mkdir -p /home/thor/Projects/capstone_project/runs/end_effector_yolo12n_416_safe/weights
rsync -av \
  runs/end_effector_yolo12n_416_safe/weights/*.pt \
  /home/thor/Projects/capstone_project/runs/end_effector_yolo12n_416_safe/weights/
```

Then copy the latest calibration and motion records if you want to version them:

```bash
rsync -av robot_camera_calibration_samples /home/thor/Projects/capstone_project/
rsync -av robot_motion_records /home/thor/Projects/capstone_project/
```
# cbnu_capstone_project
# cbnu_capstone_project
# cbnu_capstone_project
# cbnu_capstone_project
