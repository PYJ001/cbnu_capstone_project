# 발표자료 초안

## Slide 1. 프로젝트 소개
### 화면에 넣을 내용
- RGBD 카메라와 로봇 제어를 결합한 지능형 로봇 시스템
- 자연어 명령을 인식, 계획, 실행 흐름으로 연결
- 카메라-로봇 좌표 보정을 통해 실제 동작까지 확장
### 발표 대본
첫 슬라이드에서는 프로젝트를 한 문장으로 소개합니다. 핵심은 사용자의 명령이 카메라 인식과 LLM 계획을 거쳐 로봇 동작으로 이어진다는 점입니다.

## Slide 2. 개발 목표
### 화면에 넣을 내용
- 사용자 명령을 로봇 action sequence로 변환
- RGBD/VLM/YOLO 기반으로 주변 상황과 객체를 인식
- UI에서 명령, 인식 결과, 실행 결과를 확인
### 발표 대본
개발 목표는 단순한 로봇 동작 실행이 아니라, 사용자가 이해하기 쉬운 인터페이스와 인식 결과를 함께 제공하는 통합 시스템을 만드는 것입니다.

## Slide 3. 전체 구조
### 화면에 넣을 내용
- 분석 대상: 7개 주요 패키지, 26개 클래스, 약 7885라인
- RobotApp이 주요 모듈을 생성하고 ProjectController가 흐름을 조율
- 각 기능은 INTERFACE, RGBD_CAM, LLM_PLANNER, ROBOT, CALIBRATION으로 분리
### 발표 대본
여기서는 구조를 강조합니다. RobotApp은 조립 역할이고, 실제 흐름 제어는 ProjectController가 담당한다는 점을 말하면 좋습니다.

## Slide 4. ProjectController의 역할
### 화면에 넣을 내용
- 사용자 명령을 받아 작업/재보정/인식 명령으로 분기
- RGBD snapshot, LLM plan, robot execution을 순서대로 연결
- Interface에 중간 상태와 최종 결과를 지속적으로 publish
### 발표 대본
ProjectController는 발표에서 가장 중요한 중심 모듈입니다. 여러 기능을 직접 구현하기보다 각 모듈을 연결하는 orchestrator라는 점을 강조합니다.

## Slide 5. Perception: RGBD_CAM
### 화면에 넣을 내용
- RGB frame과 depth 정보를 최신 camera data로 유지
- YoloRobot, YoloWorld, VLM을 통해 로봇/객체/장면 정보를 추출
- 인식 결과를 LLM 계획과 UI 표시에서 재사용
### 발표 대본
RGBD_CAM은 로봇이 환경을 이해하기 위한 눈 역할입니다. RGB, depth, 객체 인식 결과가 다음 단계의 입력이 됩니다.

## Slide 6. Planning: LLM_PLANNER
### 화면에 넣을 내용
- 사용자 명령과 perception summary를 입력으로 사용
- 로봇이 수행할 action sequence를 생성
- Ollama 기반 LLM 호출 구조로 로컬 실행 가능
### 발표 대본
이 슬라이드에서는 자연어가 어떻게 로봇 명령 형태로 바뀌는지 설명합니다. LLM은 고수준 명령을 action sequence로 변환하는 계획자입니다.

## Slide 7. Control: ROBOT
### 화면에 넣을 내용
- RobotActions가 DNC, WAV, MOV, GRB 같은 primitive action을 관리
- ROBOT 대표 클래스가 action sequence 실행과 primitive 제어 API를 제공
- ProjectController는 robot.run_sequence 형태로 실행을 위임
### 발표 대본
ROBOT 모듈은 계획 결과를 실제 동작으로 바꾸는 부분입니다. action registry 구조 덕분에 새 동작을 추가하기 쉽다는 점을 말할 수 있습니다.

## Slide 8. Calibration
### 화면에 넣을 내용
- 카메라의 u, v, depth 정보를 로봇 좌표/관절 정보로 변환
- RegressionModel을 사용해 보정 모델을 구성
- 재보정 흐름을 CALIBRATION 패키지로 분리해 유지보수성 개선
### 발표 대본
캘리브레이션은 인식과 제어를 연결하는 다리입니다. 카메라에서 보이는 위치가 로봇이 움직일 수 있는 좌표로 바뀌어야 실제 조작이 가능합니다.

## Slide 9. Interface
### 화면에 넣을 내용
- 사용자 명령 입력과 상태 표시를 담당
- PyQt5 프로세스로 UI를 분리해 메인 로직과 화면 갱신을 분리
- RGBD frame, 인식 결과, action 결과를 한 화면에 표시
### 발표 대본
Interface는 사용자가 시스템 상태를 확인하는 창입니다. UI 프로세스를 분리해 로봇/카메라 루프와 화면 이벤트 루프가 서로 방해하지 않게 구성했습니다.

## Slide 10. 시연 및 향후 개선
### 화면에 넣을 내용
- 시연: main.py 실행 후 RGBD 화면, 명령 입력, action 결과 확인
- 개선: 예외 처리, 로그 체계, action 확장, 모델 정확도 개선
- 확장: 다른 로봇이나 다른 perception 모델로 교체 가능한 구조
### 발표 대본
마지막에는 현재 구현된 시연 흐름과 앞으로의 개선점을 정리합니다. 특히 모듈 분리 덕분에 확장 가능하다는 결론으로 마무리하면 자연스럽습니다.

## 발표 순서 추천
1. 문제 정의와 목표를 먼저 설명한다.
2. 전체 아키텍처를 보여준 뒤 ProjectController 중심 흐름을 설명한다.
3. RGBD_CAM, LLM_PLANNER, ROBOT, CALIBRATION, INTERFACE를 기능 단위로 설명한다.
4. 실제 시연 장면과 개선 가능성으로 마무리한다.