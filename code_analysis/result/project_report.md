 # 프로젝트 개요
본 프로젝트는 다양한 기계 학습 모델을 사용하여 로봇의 동작을 계획하고, 인터페이스를 통해 실시간으로 카메라 데이터를 분석하는 것을 목적으로 한다. 특히, RGBD(RGB-Depth) 카메라를 사용하여 실시간으로 영상을 분석하고, 이를 기반으로 로봇의 동작을 계획하는 것에 주안점을 두고 있다.

# 전체 폴더 구조
본 프로젝트는 src, trash 그리고 기타 필요한 파일을 담고 있는 기본적인 구조를 가지고 있다. src 디렉토리 내에서는 각 기능별로 하위 디렉토리들을 생성하여 관리한다.

# 주요 파일별 역할
- **code_analysis.py**: 프로젝트의 분석을 담당하는 스크립트이다. AST(Abstract Syntax Tree)를 사용한 소스 코드 분석과, Python 모듈의 import 관계를 분석하여 보고서를 작성한다.
- **main.py**: 프로젝트의 최상위 진입점이다. `src.RobotApp.RobotApp`을 생성하고 실행한다.
- **src/RobotApp.py**: 전체 애플리케이션 런타임을 조립한다. 각 패키지의 `*_main.py`에 정의된 대표 클래스를 생성하고, `ProjectController`에 전달한다.
- **src/ProjectController.py**: 사용자 명령, 카메라 데이터, LLM 계획, 로봇 실행, 캘리브레이션을 연결하는 중앙 orchestration 클래스이다.
- **src/*/*_main.py**: 각 패키지의 RobotApp-facing entry class와 단독 기능 테스트용 `main()`을 함께 둔다.
- **src/INTERFACE/__init__.py**: 기본 `Interface`를 `interface_main.Interface`로 노출한다. PyQt 구현체는 선택적으로 import되며, 현재 기본 실행 형식은 `interface_main.py`를 기준으로 한다.
- **src/**: 주요 기능들을 구현한 Python 모듈이 위치한다. 각 하위 디렉토리는 서로 다른 기능을 담고 있다.
- **trash/**: 테스트, 데이터 수집, TTS(Text to Speech)와 같은 부가적인 기능을 담고 있는 Python 모듈이 위치한다.

# import 관계를 통해 본 모듈 연결
src의 각 하위 디렉토리는 서로 다른 기능을 수행하지만, 최상위 `main.py`는 `src.RobotApp`만 import하여 실행한다. `RobotApp`은 각 패키지의 main 모듈에서 대표 클래스를 import한다. 현재 대표 클래스는 `RGBD_CAM.rgbd_cam_main.RGBD`, `LLM_PLANNER.llm_planner_main.LLMPlanner`, `ROBOT.robot_main.ROBOT`, `INTERFACE.interface_main.Interface`, `CALIBRATION.calibration_main.Calibration`, 그리고 `ProjectController.ProjectController`이다.

이 구조에서 패키지 내부 구현 클래스나 서비스 객체는 각 패키지 main 클래스 뒤에 감춰진다. 따라서 `RobotApp`은 구체 구현 파일보다 패키지 단위 entry class를 조립하는 역할에 집중한다.

# class/function 목록을 통해 본 구현 요소
src 내의 각 파일에는 다양한 class와 function이 정의되어 있다. 현재 구조에서 주요 실행 구성요소는 아래와 같다.
- **RobotApp**: 각 패키지 main class를 생성하고 실행 순서를 관리한다.
- **ProjectController**: `Interface`, `RGBD`, `LLMPlanner`, `ROBOT`, `Calibration`을 받아 전체 작업 흐름을 조율한다.
- **Interface**: `interface_main.py`에 RobotApp-facing 형식을 정의한 클래스이다. `launch`, `run`, `close` 생명주기와 `_send`, `_voice`, `_recalibrate`, `_quit` 계열 버튼 핸들러, 텍스트 표시 갱신 함수, RGBD 표시 갱신 함수를 가진다. `interface_main.py`는 PyQt5를 직접 import하지 않고, `interface_pyqt5.py`의 프로세스 클라이언트에 상태 변경과 RGBD 표시 갱신 요청만 전달한다.
- **InterfacePyQt5Process**: `interface_pyqt5.py`에 정의된 PyQt5 전용 UI 프로세스 클라이언트이다. PyQt5 import와 이벤트 루프는 자식 프로세스 내부에서만 실행되며, main interface와는 queue 메시지로 통신한다.
- **RGBD**: `RGBDService`를 감싼 카메라 패키지 대표 클래스이다. frame, depth, detection 정보를 제공한다.
- **LLMPlanner**: `LLMPlannerService`를 감싼 계획 패키지 대표 클래스이다. 센서 정보와 사용자 명령으로 action sequence를 생성한다.
- **ROBOT**: `RobotService`를 감싼 로봇 패키지 대표 클래스이다. `get_pose`, `move_angle`, action 실행 API를 제공한다.
- **Calibration**: 캘리브레이션 실행 entry class이다. 카메라나 로봇을 직접 소유하지 않고, `ProjectController`가 전달한 robot과 capture callback을 사용한다.

# 전체 실행 흐름 요약
1. `main.py`가 `RobotApp`을 import하여 실행한다.
2. `RobotApp`은 각 패키지 main에서 `RGBD`, `LLMPlanner`, `ROBOT`, `Interface`, `Calibration` 클래스를 생성한다.
3. `RobotApp`은 생성한 객체들을 `ProjectController`에 전달한다.
4. `RobotApp.run()`은 각 객체의 `launch()`를 호출하고, interface 실행 루프를 시작한다.
5. `ProjectController`는 `Interface`에서 사용자 명령을 받고, `RGBD`에서 카메라/센서 정보를 읽는다.
6. `LLMPlanner`는 센서 정보와 사용자 명령을 기반으로 action sequence를 반환한다.
7. `ROBOT`은 `ProjectController`가 전달한 action sequence를 실행한다.
8. 캘리브레이션 명령이 들어오면 `ProjectController`가 `Calibration`을 호출하되, 필요한 robot/capture 정보는 controller를 통해 전달한다.

# 정리 및 개선 가능성
현재 구현된 기능들은 기본적인 동작을 수행하는 데에는 충분하지만, 다양한 개선이 가능할 것으로 보인다.
- **성능 최적화**: 실시간으로 RGBD 영상을 분석하고, 이를 바탕으로 동작 계획을 수립하는 과정에서 더욱 빠르게 처리될 수 있도록 최적화가 필요하다.
- **사용자 인터페이스**: GUI의 사용자 경험을 개선하여, 더욱 직관적이고 사용하기 쉬운 인터페이스를 제공할 수 있다.
- **모델의 성능 개선**: LLM, YoloRobot, YoloWorld 등의 기계 학습 모델의 정확도를 높이고, 런타임을 줄여서 실시간성을 개선해야 한다.
- **에러 처리**: 예기치 못한 상황에 대비하여, 보다 유연한 에러 처리 및 로깅을 도입할 필요가 있다.
- **확장성**: 새로운 기능의 추가나, 다른 유형의 로봇과의 연동을 쉽게 할 수 있는 인터페이스를 개발하여야 한다.

이상으로 본 프로젝트의 개요와 구성을 분석하였다. 기본적인 기능은 작동하나, 더욱 발전된 기능과 성능 향상을 위해서는 지속적인 개발과 연구가 필요할 것이다.

# 변경 기록

## 2026-06-14 Interface 기능 테스트 main 추가
- `src/INTERFACE/interface_main.py`의 `main()`을 1분 동안 자동으로 interface 상태를 갱신하는 기능 테스트 코드로 구성하였다.
- 테스트 중 `_send`, `_voice`, `_recalibrate` 계열 handler를 순차적으로 호출하고, `user_command`, `vlm_summary`, `print_out`, `action_sequence`, `action_result`를 반복 갱신하도록 하였다.
- 테스트용 RGBD 데이터를 생성하는 `_make_test_rgbd_data()`를 추가하여 `frame`, `depth`, `yolo_robot`, `yolo_world` 갱신 흐름을 확인할 수 있게 하였다.
- PyQt5가 설치되지 않은 환경에서도 `interface_main.py` import와 간단한 기능 테스트가 종료되지 않고 남지 않도록 `InterfacePyQt5Process`의 queue 처리와 close 흐름을 보강하였다.

## 2026-06-14 Interface OpenCV 시각화 경로 복구
- `src/INTERFACE/interface_main.py`가 기존 OpenCV 기반 `_visualizer_loop`를 다시 실행하도록 수정하였다.
- `Interface.launch()`에서 OpenCV visualizer process를 시작하고, `_set_rgbd()`와 `update()`가 RGBD packet과 state packet을 visualizer queue로 전달하도록 하였다.
- `python3 src/INTERFACE/interface_main.py`처럼 파일을 직접 실행해도 상대 import 오류가 나지 않도록 import fallback을 추가하였다.
- PyQt5는 계속 `interface_pyqt5.py`의 별도 process client로 분리하고, 기존 OpenCV 시각화는 `interface_main.py`에서 기능 테스트 화면으로 사용할 수 있게 하였다.

## 2026-06-14 Interface PyQt5 검정 UI 복귀
- `src/INTERFACE/interface_main.py`에서 기존 OpenCV 기반 `Interface.py` 및 `_visualizer_loop` 의존을 제거하였다.
- `src/INTERFACE/interface_main.py`는 다시 `InterfacePyQt5Process`만 호출하며, PyQt5 UI 실행은 `src/INTERFACE/interface_pyqt5.py`의 별도 프로세스가 담당하도록 정리하였다.
- `src/INTERFACE/interface_pyqt5.py`에 기존 검정색 UI 스타일시트와 검정색 image panel 스타일을 복구하였다.
- `Interface.py`는 더 이상 `interface_main.py`에서 사용하지 않으며, PyQt5 UI를 기준 interface 표시 방식으로 되돌렸다.

## 2026-06-14 Interface PyQt5 실행 진단 보강
- `src/INTERFACE/interface_pyqt5.py`에서 PyQt5가 설치되지 않은 경우 화면 없이 조용히 넘어가지 않고 설치 안내 메시지를 출력하도록 하였다.
- PyQt5 UI 프로세스가 정상 시작되면 process id를 출력하도록 하여 화면 실행 여부를 확인할 수 있게 하였다.
- Qt platform plugin 경로를 `plugins/platforms`로 지정하도록 보강하여 PyQt5가 설치된 환경에서 platform plugin 로딩 실패 가능성을 줄였다.
- `src/INTERFACE/interface_main.py`의 `show_window` 값이 PyQt5 프로세스 client의 실행 여부에 반영되도록 하였다.

## 2026-06-14 Interface PyQt5 xcb plugin 충돌 수정
- `src/INTERFACE/interface_pyqt5.py`에서 OpenCV(`cv2`) import 이후에도 PyQt5 plugin 경로를 다시 설정하도록 수정하였다.
- OpenCV가 `cv2/qt/plugins` 경로를 Qt plugin search path로 덮어쓰는 경우를 방지하기 위해 `configure_qt_plugin_path()`를 PyQt5, OpenCV, interface utility import 이후 반복 적용하였다.
- `QApplication.setLibraryPaths()`를 사용해 PyQt5 plugin root를 명시적으로 지정하도록 하였다.
- PyQt5 자식 프로세스가 비정상 종료된 경우 `InterfacePyQt5Process.call()`에서 exit code를 한 번 출력하도록 하여 화면이 사라진 원인을 확인할 수 있게 하였다.

## 2026-06-14 ProcessService 위치 이동
- `src/process_service.py`를 제거하고 `src/srv/util/process_service.py`로 이동하였다.
- `src/srv/__init__.py`와 `src/srv/util/__init__.py`를 추가하여 `ProcessService`를 공용 service utility로 import할 수 있게 하였다.
- `RGBDService`, `LLMPlannerService`, `RobotService`의 import 경로를 `from src.srv.util import ProcessService`로 변경하였다.
- 잘못 생성했던 대문자 `src/SRV` 잔여 디렉터리는 제거하고, 요청한 소문자 `src/srv/util` 구조로 정리하였다.

## 2026-06-14 RGBD main 구조 재구성
- `src/RGBD_CAM/rgbd_cam_main.py`를 RGBD 패키지 대표 클래스 중심으로 재작성하였다.
- `RGBD` 클래스에 `launch`, `run`, `close`, `_start_camera_stream`, `_open_camera`, `_close_camera`, `get_rgb`, `get_depth`, `get_rgbd`, `get_frame`, `get_latest_camera_data`, `inference`, `camera_loop`, `_read_camera_once`, `_make_camera_data`, `test`를 구성하였다.
- `YoloRobot`, `YoloWorld`, `VLM` wrapper 클래스를 `rgbd_cam_main.py`에 추가하여 `yolo_robot.inference`, `yolo_world.inference`, `vlm.inference` 형태로 호출할 수 있게 하였다.
- VLM 결과의 `summary`와 `objects`를 camera data의 `vlm_summary`, `vlm_objects`로 포함하고, VLM이 찾은 objects가 있으면 YOLO-World class 설정에 반영하도록 하였다.
- RGBD camera loop가 최신 camera data를 보관하도록 구성하고, `interface_main.py`에서는 camera loop와 `get_frame()` 직접 호출을 제거하여 camera streaming 책임을 RGBD 패키지로 이동하였다.
- `RGBDService`도 새 `rgbd_cam_main.RGBD` 클래스를 사용하도록 변경하여 직접 사용과 service 사용 시 RGBD 구조가 달라지지 않게 하였다.

## 2026-06-14 RGBD 하위 구성요소 위치 분리
- `rgbd_cam_main.py` 안에 임시로 두었던 `YoloRobot`, `YoloWorld`, `VLM` wrapper를 각 구현 위치로 분리하였다.
- `src/RGBD_CAM/YoloRobot.py`에 `YoloRobot` wrapper를 추가하여 기존 `YoloRobotDetector`를 감싸도록 하였다.
- `src/RGBD_CAM/YoloWorld.py`에 `YoloWorld` wrapper를 추가하여 기존 `YoloWorldDetector`를 감싸도록 하였다.
- `src/RGBD_CAM/VLM.py`는 더 이상 trash 경로를 import하지 않고, 기존 `trash/vlm_updator/VLM.py` 구현을 참고한 실제 `VLM` 클래스를 포함하도록 변경하였다.
- `src/RGBD_CAM/rgbd_cam_main.py`는 `YoloRobot`, `YoloWorld`, `VLM`을 각 파일에서 import하여 사용하는 구조로 정리하였다.
- `src/RGBD_CAM/__init__.py`는 새 `rgbd_cam_main.RGBD`, `VLM`, `YoloRobot`, `YoloWorld`를 export하도록 갱신하였다.


## 2026-06-14 Calibration main 구조 구성 및 RGBD 분리
- `src/CALIBRATION/calibration_main.py`에 `Calibration` 대표 클래스를 구성하고 `__init__`, `launch`, `close`, `calibrate`, `run`, `reload`, `uvd2qrst`, `uvd2xyz`, `uvd2qrst_objs`, `test` 메소드를 추가하였다.
- `calibrate()`는 ProjectController가 robot과 capture callback을 전달하는 구조로 두고, 입력이 없을 때는 현재 의도된 재보정 흐름을 pseudocode 데이터로 반환하도록 하였다.
- `uvd2qrst()`는 기존 `CalibrationModel` 예측을 사용하고, `uvd2xyz()`는 camera intrinsics가 준비되기 전에도 테스트 가능한 placeholder 결과를 반환하도록 구성하였다.
- `uvd2qrst_objs()`는 YOLO detected object 목록 또는 단일 dict에 `qrst`, `joint`, `xyz` 필드를 적용해 반환하도록 구성하였다.
- `src/RGBD_CAM/rgbd_cam_main.py`에서 직접 들고 있던 `_calibration()` 로직을 제거하고, RGBD는 `Calibration.uvd2qrst_objs()`를 호출하는 형태로 변경하였다.
- `src/ProjectController.py`는 재보정 시 `Calibration.calibrate()`를 호출하고, 완료 후 RGBD에 최신 Calibration 객체를 주입하도록 변경하였다.
- `src/RGBD_CAM/RGBDService.py`에 `reload_calibration()` 호환 메소드를 추가하여 기존 `_load_calibration_model()` 호출 경로가 새 구조로 이어지도록 하였다.


## 2026-06-14 CalibrationModel 명명 정리 및 RGBDService legacy 이동
- `src/CALIBRATION/calibration_main.py`의 대표 클래스를 `Calibration`에서 `CalibrationModel`로 변경하고, 기존 UVD-to-joint KNN 모델은 내부 alias인 `UVDCalibrationModel`로 구분하였다.
- `RobotApp`, `ProjectController`, `RGBD`에서 calibration 객체 변수명을 `calibration_model` 중심으로 정리하였다.
- `CALIBRATION.__init__`에서 sample collector를 lazy import하도록 변경하여 `calibration_main.py` 단독 실행 시 발생하던 circular import 가능성을 제거하였다.
- `src/RGBD_CAM/RGBDService.py`는 `trash/RGBD_CAM/RGBDService.py`로 이동하고, `src/RGBD_CAM/__init__.py` export에서 제거하였다.
- RGBD main은 기존 service wrapper가 제공하던 주요 호출 표면인 `get_frame`, `get_latest_camera_data`, enable toggle, `reload_calibration`을 직접 제공하는 구조로 유지하였다.


## 2026-06-14 RobotActions 클래스 구성
- `/home/thor/Projects/CAPSTONE/framework.py`와 기존 `robot_actions.py` 함수형 action set을 참고하여 `src/ROBOT/robot_actions.py`에 `RobotActions` 클래스를 추가하였다.
- `RobotActions`는 `DNC`, `WAV`, `SKH`, `MOV`, `MVA`, `GRB`, `REL`, `TRW`, `LFT`, `THR`, `HRT`, `HND` action registry를 가진다.
- 각 action은 `run(action_name, obj=None, rgbd_cam=None)`으로 호출할 수 있게 구성하고, 설명 조회용 `get_available_actions()`와 개별 action 조회용 `get_action()`을 추가하였다.
- 기존 `DNC()`, `WAV()`, `GRB()` 등 함수형 wrapper는 호환을 위해 유지하되 내부에서 `RobotActions` 메소드를 호출하도록 변경하였다.
- `src/ROBOT/RobotManager.py`는 직접 action 함수를 import하지 않고 `RobotActions(self)`를 소유하도록 변경하였다.


## 2026-06-14 ROBOT main 통합 및 calibration pose 이동
- `RobotManager.py`에 있던 `CALIBRATION_POSES`를 `src/CALIBRATION/calibration_main.py`의 `DEFAULT_CALIBRATION_POSES`로 이동하였다.
- `src/ROBOT/robot_main.py`를 실제 ROBOT 대표 클래스로 재구성하여 `RobotService` proxy 없이 lifecycle, pose, action, sequence, primitive control 메소드를 직접 제공하도록 하였다.
- 기존 `RobotActionHandler.run_sequence()` 역할은 `ROBOT.run_sequence()`로 통합하고, `ProjectController`가 `self.robot.run_sequence(...)`를 직접 호출하도록 변경하였다.
- `src/ROBOT/__init__.py`는 `ROBOT`과 `RobotActions`만 export하도록 정리하였다.
- legacy `RobotManager.py`, `RobotService.py`, `RobotActionHandler.py`는 `trash/ROBOT/`로 이동하였다.


## 2026-06-14 calibration_model 파일명 정리 및 calibration pose 분리
- `src/CALIBRATION/Calibration.py`를 `src/CALIBRATION/calibration_model.py`로 변경하여 대문자 `Calibration` 파일명을 제거하였다.
- `src/CALIBRATION/calibration_main.py`는 내부 예측 모델을 `calibration_model.py`에서 `UVDCalibrationModel` alias로 import하도록 변경하였다.
- `DEFAULT_CALIBRATION_POSES`를 `calibration_main.py`에서 제거하고 `src/CALIBRATION/calibration_poses.py`에 별도 저장하였다.
- `src/ROBOT/robot_main.py`는 calibration pose를 `calibration_poses.py`에서만 import하도록 변경하였다.
- legacy `src/RGBD_CAM/RGBD.py`가 package-level `CalibrationModel`을 잘못 가져가지 않도록 `UVDCalibrationModel` import로 수정하였다.


## 2026-06-14 RegressionModel 명명 정리
- `src/CALIBRATION/calibration_model.py` 내부 클래스를 `CalibrationModel`에서 `RegressionModel`로 변경하였다.
- `src/CALIBRATION/calibration_main.py`의 대표 클래스 `CalibrationModel`은 유지하고, 내부 회귀 모델은 `UVDRegressionModel` alias로 import하도록 정리하였다.
- `src/CALIBRATION/__init__.py`는 `UVDRegressionModel`을 export하도록 변경하였다.
- legacy `src/RGBD_CAM/RGBD.py`도 `UVDRegressionModel` import를 사용하도록 수정하였다.


## 2026-06-14 regression_model 파일명 변경
- `src/CALIBRATION/calibration_model.py` 파일명을 `src/CALIBRATION/regression_model.py`로 변경하였다.
- `src/CALIBRATION/calibration_main.py`와 `src/CALIBRATION/__init__.py`의 import 경로를 `regression_model.RegressionModel`로 수정하였다.
- 활성 `src` 코드에서 `calibration_model.py` import 문자열이 남지 않도록 확인하였다.


## 2026-06-14 LLM_PLANNER main 통합
- `src/LLM_PLANNER/llm_planner_main.py`에 Ollama client 역할의 `LLM` 클래스와 planner 역할의 `LLMPlanner` 클래스를 통합하였다.
- 기존 service proxy 구조를 제거하고, `LLMPlanner`가 `launch`, `run`, `close`, `inference`를 직접 제공하도록 변경하였다.
- `src/LLM_PLANNER/__init__.py`는 `llm_planner_main`의 `LLM`, `LLMPlanner`만 export하도록 정리하였다.
- legacy `LLMService.py`, `LLM_planner.py`, `LLM.py`는 `trash/LLM_PLANNER/`로 이동하였다.
- Ollama import는 inference 호출 시점으로 늦춰, Ollama 패키지가 없는 환경에서도 package import와 fallback 테스트가 가능하도록 하였다.


## 2026-06-14 LLM 클래스 분리
- `src/LLM_PLANNER/llm_planner_main.py`에서 `LLM` 클래스를 제거하고, 대표 클래스 `LLMPlanner`만 남겼다.
- Ollama client 역할의 `LLM` 클래스는 `src/LLM_PLANNER/llm.py`로 분리하였다.
- `src/LLM_PLANNER/__init__.py`는 `llm.py`의 `LLM`과 `llm_planner_main.py`의 `LLMPlanner`를 export하도록 변경하였다.


## 2026-06-14 ProcessService srv 위치 정리
- `src/srv/util/process_service.py`를 `src/srv/process_service.py`로 이동하였다.
- `src/srv/__init__.py`가 `ProcessService`를 직접 export하도록 변경하였다.
- 불필요해진 `src/srv/util/` 디렉터리를 제거하였다.


## 2026-06-14 recalibration 로직 CALIBRATION 이동
- `src/CALIBRATION/calibration_main.py`에 `CalibrationModel.run_recalibration()`을 추가하였다.
- RGBD의 YOLO-World enable 상태와 calibration prediction enable 상태를 저장, 비활성화, 복구하는 절차를 CALIBRATION 패키지로 이동하였다.
- 재보정 완료 후 RGBD에 최신 calibration model을 주입하는 로직도 CALIBRATION 패키지로 이동하였다.
- `src/ProjectController.py`의 `_run_recalibration()`은 UI 상태 업데이트와 `calibration_model.run_recalibration(...)` 호출만 담당하도록 축소하였다.


## 2026-06-14 ProjectController orchestrator 구조 재정리
- `src/ProjectController.py`를 Interface, RGBD, LLM_PLANNER, ROBOT, CALIBRATION 사이의 message router 역할이 드러나도록 재구성하였다.
- command 처리 흐름을 `_receive_interface_command`, `_route_interface_command`, `_handle_user_task_command`, `_handle_recalibration_command`로 분리하였다.
- RGBD 요청은 `_request_rgbd_snapshot`, LLM 요청은 `_request_llm_plan`, ROBOT 명령은 `_command_robot`, Interface 반영은 `_publish_rgbd_snapshot`, `_publish_interface_state`로 분리하였다.
- 사용자 task 처리 흐름은 RGBD snapshot publish → LLM plan publish → ROBOT sequence 실행 → final result publish 순서로 명확히 하였다.
- recalibration은 CALIBRATION 패키지의 `run_recalibration()`에 위임하고 Controller는 UI 상태 전파만 담당하도록 유지하였다.


## 2026-06-14 ProjectController RGBD-Interface 기능 테스트 추가
- `src/ProjectController.py`에 `test_rgbd_interface(duration, hz)`를 추가하여 RGBD camera data를 ProjectController를 통해 Interface/PyQt로 지속 publish하는 테스트 루프를 만들었다.
- 테스트 흐름은 RGBD 최신 snapshot 요청, 필요 시 RGBD blocking frame 요청, Interface `rgbd_data` publish, 테스트 상태 text publish 순서로 구성하였다.
- `python3 src/ProjectController.py rgbd_interface --duration 60 --hz 10` 형식의 직접 실행 CLI를 추가하였다.
- 실제 Robot/LLM이 필요 없는 테스트를 위해 `_NoopRobot`, `_NoopLLMPlanner`를 ProjectController 테스트용으로 추가하였다.


## 2026-06-14 ProjectController test() wrapper 추가
- `src/ProjectController.py`에 `test(duration=60.0, hz=10.0, close_on_finish=True)`를 추가하였다.
- `test()`는 RGBD, LLMPlanner, ROBOT, CalibrationModel, Interface를 launch한 뒤 `test_rgbd_interface()`를 실행하고, 종료 시 close까지 수행한다.
- `RobotApp.__init__`에서 필요할 때 `self.project_controller.test()`를 호출할 수 있도록 주석 예시를 추가하였다.
- fake module 기반으로 launch, RGBD publish, close 순서가 동작하는지 검증하였다.


## 2026-06-14 main.py RGBD-Interface test 실행 연결
- `src/RobotApp.py`에 `test(duration=60.0, hz=10.0)` wrapper를 추가하여 `ProjectController.test()`를 호출할 수 있게 하였다.
- `main.py`가 `RobotApp()` 생성 후 바로 종료하지 않고 `app.test()`를 호출하도록 수정하였다.
- 이제 `python3 main.py`는 RGBD -> ProjectController -> Interface/PyQt 송출 기능 테스트를 실행한다.


## 2026-06-14 RGBD-Interface 테스트에서 VLM/추론 제거
- `src/RGBD_CAM/rgbd_cam_main.py`의 `camera_loop()`가 `inference()`를 호출하지 않고 RGB/depth camera data만 갱신하도록 변경하였다.
- `RGBD.get_camera_data()`를 추가하여 frame/depth만 포함한 camera data를 생성하고 최신 상태로 저장하도록 하였다.
- `RGBD.run()`은 테스트 송출 목적에 맞게 `get_camera_data()`를 반환하도록 변경하였다.
- VLM은 기본 비활성화 및 lazy initialization 구조로 바꾸어 명시적 `inference()` 호출 없이는 실행되지 않도록 하였다.
- `src/ProjectController.py`의 RGBD-Interface 테스트 경로가 `get_camera_data()`를 우선 호출하도록 변경하였다.
- ProjectController 기능 테스트는 RGBD와 Interface만 launch/close하여 LLM, ROBOT, CALIBRATION 실행이 섞이지 않도록 축소하였다.
- fake RGBD/Interface 테스트로 `get_camera_data()` 호출 및 `inference()` 미호출을 확인하였다.


## 2026-06-14 RGBD YOLO lazy initialization 적용
- `src/RGBD_CAM/rgbd_cam_main.py`에서 YOLO-World와 YOLO-Robot 객체 생성을 `RGBD.__init__()` 시점이 아니라 명시적 `inference()` 호출 시점으로 늦췄다.
- `set_yolo_world_enabled`, `set_yolo_robot_enabled`, `set_yolo_world_classes`는 detector가 아직 생성되지 않은 경우 설정값만 저장하도록 변경하였다.
- `_get_yolo_world()`, `_get_yolo_robot()` helper를 추가하여 추론이 실제로 필요할 때 detector를 생성하고 저장된 설정을 적용하도록 하였다.
- `RGBD()` 생성 시 `yolo_world`, `yolo_robot`, `vlm`이 모두 로드되지 않음을 확인하였다.
- ProjectController RGBD-Interface 테스트에서 `get_camera_data()`만 호출되고 `inference()`는 호출되지 않음을 재검증하였다.


## 2026-06-14 RGBD 메소드 이름 역할 기준 정리
- PyQT 송출용 원본 RGB/depth 데이터는 `rgbd_frame`으로 부르도록 정리하였다.
- YOLO/VLM/보정 결과가 포함될 수 있는 데이터는 `perception_data`로 부르도록 ProjectController 흐름을 수정하였다.
- `src/RGBD_CAM/rgbd_cam_main.py`에 `capture_rgbd_frame()`, `get_latest_rgbd_frame()`, `get_latest_perception_data()`, `get_perception_frame()`을 추가하였다.
- `RGBD.run()`과 `RGBD.camera_loop()`는 `capture_rgbd_frame()`을 사용하도록 변경하여 이름과 기능을 맞췄다.
- `src/ProjectController.py`의 PyQT 송출 테스트 경로는 `_request_latest_rgbd_frame()`, `_capture_rgbd_frame()`, `_publish_rgbd_frame()` 이름을 사용하도록 변경하였다.
- 일반 사용자 명령 처리 경로는 `_request_perception_data()`를 통해 추론 데이터가 필요하다는 점이 드러나도록 수정하였다.
- `src/INTERFACE/interface_main.py`는 RGBD에서 `get_latest_rgbd_frame()`을 우선 호출하도록 변경하였다.
- fake RGBD 테스트로 RGBD-Interface 테스트 경로에서 `capture_rgbd_frame()`만 호출되고 `inference()`는 호출되지 않음을 확인하였다.


## 2026-06-14 RGBD-Interface 테스트 무제한 실행 변경
- `src/ProjectController.py`의 `test()`와 `test_rgbd_interface()` 기본 `duration`을 `None`으로 변경하였다.
- `duration=None`이면 시간 제한 없이 `stop_event`가 설정될 때까지 RGBD frame을 Interface/PyQt로 계속 송출하도록 변경하였다.
- `duration` 값이 명시된 경우에만 지정 초 이후 테스트 완료 상태를 publish하도록 변경하였다.
- `KeyboardInterrupt` 발생 시 `stop_event`를 설정하고 close 절차로 진입하도록 처리하였다.
- `src/RobotApp.py`의 `RobotApp.test()` 기본값도 `duration=None`으로 변경하여 `python3 main.py`가 60초 후 자동 종료되지 않도록 하였다.
- `src/ProjectController.py rgbd_interface` CLI의 `--duration` 기본값도 `None`으로 변경하였다.
- fake RGBD/Interface 테스트로 `duration=None`에서 stop 이벤트 전까지 반복 송출되고, stop 이벤트 후 정상 종료되는 것을 확인하였다.


## 2026-06-14 Interface 버튼 기능 연결
- `src/INTERFACE/interface_pyqt5.py`에서 Send, Voice, Recalibration, Inference, Quit 버튼이 구조화된 command dictionary를 부모 프로세스로 보내도록 변경하였다.
- PyQT command row에 `Inference` 버튼을 추가하였다.
- `src/INTERFACE/interface_main.py`에서 Send 버튼 command를 `_send_handler()`로 처리하여 UserCommand를 정규화하고 Interface state에 반영하도록 연결하였다.
- Voice 버튼은 `VoiceManager`를 lazy import한 뒤 `listen()` 결과를 UserCommand로 변환하도록 연결하였다.
- Recalibration 버튼은 실제 calibration 실행 대신 pseudocode 상태 메시지를 publish하는 command로 연결하였다.
- Quit 버튼은 Interface close 및 ProjectController stop 흐름으로 연결하였다.
- `src/ProjectController.py`에 `perception_inference` command 처리 경로를 추가하여 Inference 버튼을 누른 경우에만 RGBD `inference(use_vlm=True)`를 호출하도록 하였다.
- `src/RGBD_CAM/rgbd_cam_main.py`의 `inference(use_vlm=True)`에서 VLM을 먼저 실행해 YOLO-World class를 갱신한 뒤 YOLO 추론을 수행하도록 순서를 정리하였다.
- RGBD-Interface 테스트 루프 안에서도 버튼 command를 읽어 Quit, Recalibration, Inference를 처리하도록 연결하였다.
- compileall 및 fake Interface/ProjectController 테스트로 Send 정규화, Inference 버튼의 `use_vlm=True` 호출, Quit stop 처리를 확인하였다.


## 2026-06-14 RGBD 역할 축소 및 Inference 버튼 버그 수정
- `src/INTERFACE/interface_main.py`에서 Inference 버튼 처리 시 UserCommand를 `perception_inference`로 덮어쓰던 동작을 제거하였다.
- Interface에 `get_current_user_command()`를 추가하여 ProjectController가 현재 UserCommand를 조회할 수 있도록 하였다.
- `src/ProjectController.py`의 Inference 처리에서 현재 UserCommand를 VLM에 전달하도록 수정하였다.
- RGBD-Interface 테스트 루프가 매 프레임 `print_out`에 streaming tick/elapsed를 쓰지 않도록 변경하여 Inference 결과가 Print Out에 남도록 하였다.
- `src/RGBD_CAM/rgbd_cam_main.py`를 카메라 전용 클래스로 재작성하여 VLM, YOLO, CalibrationModel import와 inference 책임을 제거하였다.
- VLM, YOLO-Robot, YOLO-World, calibration 적용 흐름은 ProjectController에서 RGBD frame을 받아 수행하도록 이동하였다.
- `src/RGBD_CAM/VLM.py`는 `inference(frame, user_command=...)`를 지원하도록 수정하여 UserCommand 기준으로 관련 객체를 우선 추출하게 하였다.
- `src/RGBD_CAM/RGB.py`와 기존 legacy `src/RGBD_CAM/RGBD.py`를 `trash/RGBD_CAM/`로 이동하여 active RGBD 구현을 `rgbd_cam_main.RGBD`로 통합하였다.
- `src/RGBD_CAM/__init__.py`에서 `RGB` export를 제거하였다.
- fake Interface/ProjectController 테스트로 Inference 후 UserCommand 유지, VLM에 UserCommand 전달, YOLO-World class 설정, Print Out 결과 표시를 확인하였다.
- `python3 -m compileall src main.py`로 전체 컴파일을 확인하였다.


## 2026-06-14 Send 기반 perception 및 Action Sequence 생성 연결
- `src/ProjectController.py`의 일반 Send command 처리 경로가 UserCommand를 기준으로 VLM, YOLO-Robot, YOLO-World를 실행하도록 연결하였다.
- VLM 결과의 object list를 YOLO-World class로 설정한 뒤 YOLO-World 추론을 수행하도록 유지하였다.
- Send 처리 결과를 `Print Out`에 `Perception result`와 `Planner result` 형식으로 출력하도록 구성하였다.
- VLM summary, VLM objects, YOLO robot 결과, YOLO world 결과, planner response, Action Sequence가 Print Out에 함께 표시되도록 하였다.
- LLMPlanner가 생성한 action sequence를 Interface의 `action_sequence` 상태에 반영하고 `action_result`는 `ready`로 표시하도록 하였다.
- 현재 단계에서는 Send 처리 후 ROBOT 실행까지 가지 않고 Action Sequence 생성까지만 수행하도록 제한하였다.
- `ProjectController.test()`의 RGBD-Interface 루프에서도 일반 Send command를 `_handle_user_task_command()`로 전달하도록 수정하였다.
- fake VLM/YOLO/LLMPlanner 테스트로 Send command `pick cup`이 VLM에 전달되고, YOLO-World class가 `cup`으로 설정되며, Action Sequence `[{'name': 'GRB', 'obj': 'cup'}]`가 Interface에 반영되는 것을 확인하였다.


## 2026-06-15 Interface Inference Canvas 표시 변경
- `src/INTERFACE/interface_utils.py`에 `Canvas` 클래스를 추가하여 RGB view, inference view, placeholder view 생성을 담당하도록 하였다.
- YOLO detection drawing에서 `bbox`가 존재하면 중심점 대신 bounding box를 그리도록 개선하였다.
- `src/INTERFACE/interface_main.py`의 `rgbd_state`에 inference snapshot 전용 필드(`inference_frame`, `inference_yolo_robot`, `inference_yolo_world`, `inference_vlm_summary`)를 추가하였다.
- raw RGBD streaming frame이 들어올 때는 inference snapshot을 지우지 않고, VLM/YOLO 결과가 포함된 perception data가 들어올 때만 inference snapshot을 갱신하도록 변경하였다.
- `src/INTERFACE/interface_pyqt5.py`에서 기존 Depth 패널을 Inference 패널로 교체하였다.
- Inference 패널은 VLM이 추론한 frame 위에 YOLO-World/Robot 결과를 box/marker로 표시하고 VLM summary를 상단 caption으로 보여준다.
- 아직 inference 결과가 없는 경우 Inference 패널에는 placeholder를 표시하도록 하였다.
- compileall, Canvas image rendering 테스트, raw streaming 이후 inference snapshot 유지 테스트를 수행하였다.


## 2026-06-15 Inference 화면 YOLO-world box 표시 강화
- `src/INTERFACE/interface_utils.py`에 `draw_yolo_world_boxes()`를 추가하여 오른쪽 Inference 화면에서 YOLO-world 결과를 명시적으로 bounding box로 그리도록 변경하였다.
- `Canvas.inference()`가 `draw_robot_markers()`와 `draw_yolo_world_boxes()`를 분리 호출하도록 수정하였다.
- YOLO-world 결과에 `bbox`가 없을 경우 `u`, `v` 중심점 주변에 fallback box를 만들어 표시하도록 `_make_bbox()`를 추가하였다.
- YOLO-world box는 두꺼운 노란색 계열 선으로 표시되도록 설정하였다.
- compileall, bbox pixel 검사, fallback box drawing 검사를 수행하였다.


## 2026-06-15 Send 기반 LLMPlanner action_sequence 적용
- `/home/thor/Projects/CAPSTONE/src/LLM_planner.py`의 로직을 기준으로 현재 `src/LLM_PLANNER/llm_planner_main.py` 동작을 정렬하였다.
- `LLMPlanner.inference()`는 UserCommand, VLM summary, YOLO robot, YOLO world를 입력으로 받아 `_make_plan()`에서 action_sequence를 생성하고 `_make_print_out()`에서 LLM 기반 print_out을 생성하도록 유지하였다.
- `src/ProjectController.py`에서 Send 처리 후 ProjectController가 print_out을 임의로 재작성하던 동작을 제거하였다.
- Interface의 Print Out에는 LLMPlanner가 반환한 print_out만 반영되도록 수정하였다.
- LLMPlanner action validation은 참고 파일처럼 가능한 action name만 검증하고, object가 yolo_world에 없다는 이유로 action_sequence를 제거하지 않도록 수정하였다.
- fake LLM 테스트로 `pick cup` 입력 시 action_sequence `[{'name': 'GRB', 'obj': 'cup'}]`와 print_out `I will grab the cup.`이 생성되는 것을 확인하였다.
- fake ProjectController 테스트로 Send 처리 결과가 Interface의 UserCommand, Action Sequence, Print Out, Action Result에 반영되는 것을 확인하였다.


## 2026-06-15 VLM object 기반 YOLO-world class queue 적용
- `src/ProjectController.py`에 `yolo_world_class_queue = deque(maxlen=15)`를 추가하였다.
- inference 시 VLM이 반환한 `objects`를 정리한 뒤 YOLO-world class queue에 누적하도록 구현하였다.
- human 계열 class(`person`, `people`, `human`, `man`, `woman`, `face`, `body`, `arm`, `leg` 등)는 YOLO-world class queue에 추가하지 않도록 필터링하였다.
- 중복 class는 queue에서 기존 항목을 제거한 뒤 최신 항목으로 다시 append하도록 하였다.
- YOLO-world 추론은 VLM objects 원본이 아니라 queue에 누적된 최대 15개 class 전체를 사용하도록 변경하였다.
- perception data에 `yolo_world_classes`를 포함하여 실제 YOLO-world에 사용된 class 목록을 확인할 수 있게 하였다.
- `src/RGBD_CAM/VLM.py`의 prompt와 parser limit을 최대 15개 object로 수정하였다.
- `src/RGBD_CAM/YoloWorld.py` 내부 class cleaning limit도 최대 15개로 수정하였다.
- fake 테스트로 human 제외, 최대 15개 유지, 최신 class queue 기반 YOLO-world 추론을 확인하였다.


## 2026-06-15 YOLO-world class queue 책임 위치 수정
- YOLO-world class queue와 human filtering 책임을 `src/ProjectController.py`에서 제거하였다.
- `src/RGBD_CAM/YoloWorld.py`의 `YoloWorld` wrapper가 `deque(maxlen=15)` class queue를 직접 소유하도록 이동하였다.
- `YoloWorld.add_classes_from_vlm(objects)`를 추가하여 VLM object 정리, human class 제외, 중복 제거, 최신 class queue 유지, detector class 설정을 한 메소드에서 처리하도록 하였다.
- `ProjectController`는 VLM objects를 `self.yolo_world.add_classes_from_vlm(...)`에 전달하고 `self.yolo_world.get_classes()`로 사용 class를 조회하는 역할만 하도록 축소하였다.
- fake 테스트로 RGBD 패키지 내부의 YoloWorld queue가 human 제외, 최대 15개 유지, detector class 반영을 수행함을 확인하였다.
- `python3 -m compileall src main.py`로 전체 컴파일을 확인하였다.


## 2026-06-15 Send/Inference Print Out TTS 연결
- `src/INTERFACE/interface_main.py`에 TTS queue와 background thread를 추가하였다.
- Interface launch 시 TTS thread를 시작하고 close 시 안전하게 종료하도록 구성하였다.
- `VoiceManager.speak()`를 사용하여 Interface의 최종 result text를 시스템 기본 오디오 출력으로 재생하도록 연결하였다.
- Send 최종 결과(`action_result="ready"`)와 Inference 최종 결과(`action_result="success"`)만 TTS로 출력하도록 제한하였다.
- `action_result="running"` 중간 메시지는 TTS로 출력하지 않도록 하였다.
- 같은 텍스트가 반복 출력될 경우 중복 재생하지 않도록 `last_spoken_text`를 추가하였다.
- fake VoiceManager 테스트로 running 메시지는 말하지 않고 ready/success 결과만 speak 호출되는 것을 확인하였다.


## 2026-06-15 VoiceManager STT 입력 장치 진단 및 선택 추가
- `src/INTERFACE/VoiceManager.py`에서 STT 입력 장치 목록과 기본 input device를 최초 listen 시 출력하도록 추가하였다.
- `ROBOT_STT_DEVICE` 환경변수로 STT 입력 장치를 index 또는 이름 일부로 지정할 수 있도록 구현하였다.
- `ROBOT_STT_MODEL`, `ROBOT_STT_SAMPLE_RATE`, `ROBOT_STT_RECORD_SECONDS`, `ROBOT_STT_LANGUAGE`, `ROBOT_STT_GAIN` 환경변수를 지원하도록 추가하였다.
- 녹음 후 RMS/peak audio level을 출력하여 마이크 입력이 실제로 들어오는지 확인할 수 있게 하였다.
- peak가 너무 낮으면 Whisper 호출 전에 빈 문자열을 반환하고 마이크 입력 장치 확인 메시지를 출력하도록 하였다.
- `src/INTERFACE/interface_main.py`에서 음성 인식 결과가 빈 문자열이면 Interface Print Out에 마이크 입력 장치 확인 메시지를 표시하도록 수정하였다.
- 현재 장치 조회 결과 기본 input은 `40 default`, USB 마이크 후보는 `0 CM-102MUSB microphone`으로 확인하였다.


## 2026-06-15 VoiceManager STT 자동 입력 장치 선택
- `src/INTERFACE/VoiceManager.py`의 기본 STT device 설정을 `auto`로 변경하였다.
- `python3 main.py`만 실행해도 입력 장치 목록에서 `usb`, `microphone`, `mic` 키워드가 있는 실제 입력 장치를 우선 선택하도록 구현하였다.
- 적합한 실제 입력 장치가 없을 때만 시스템 default input device를 사용하도록 fallback을 두었다.
- fake sounddevice 테스트로 default가 `40 default`여도 `0 CM-102MUSB microphone`이 자동 선택되는 것을 확인하였다.


## 2026-06-15 VoiceManager STT sample rate 자동화
- `src/INTERFACE/VoiceManager.py`에서 STT 녹음 시 고정 16000Hz 대신 선택된 input device의 `default_samplerate`를 사용하도록 변경하였다.
- USB 마이크가 48000Hz 장치인 경우 `device=0 sample_rate=48000`으로 녹음하도록 수정하여 ALSA `paInvalidSampleRate` 오류를 방지하였다.
- fake sounddevice 테스트로 자동 선택된 device 0의 sample rate가 48000으로 적용되는 것을 확인하였다.


## 2026-06-15 Voice/Enter UserCommand 로딩 전용 변경
- `src/INTERFACE/interface_pyqt5.py`에서 Enter 입력과 Send 버튼을 분리하였다.
- Enter 입력은 `load_command` 이벤트를 보내 UserCommand에 텍스트를 로딩만 하도록 변경하였다.
- Send 버튼은 `send` 이벤트를 보내 실제 추론/계획 실행을 요청하도록 유지하였다.
- Send 버튼을 누를 때 입력칸이 비어 있으면 현재 로딩된 UserCommand를 실행하도록 하였다.
- `src/INTERFACE/interface_main.py`에 `_load_command_handler()`를 추가하였다.
- Voice 버튼은 음성 인식 결과를 UserCommand에 로딩만 하고 ProjectController에는 command를 반환하지 않도록 수정하였다.
- Inference 버튼은 기존처럼 현재 UserCommand를 기준으로 추론만 수행하고 UserCommand를 변경하지 않도록 유지하였다.
- fake Interface 테스트로 Voice와 load_command는 반환값이 `None`이고, Send/Inference만 실행 command를 반환하는 것을 확인하였다.
