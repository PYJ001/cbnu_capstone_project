import json
from collections import defaultdict


PACKAGE_ROLES = {
    "ROOT": "프로젝트 실행 진입점과 분석 보조 스크립트",
    "CALIBRATION": "RGBD 카메라 좌표와 로봇 관절/작업 좌표를 연결하는 보정 모듈",
    "INTERFACE": "사용자 입력, 상태 표시, RGBD 화면 표시를 담당하는 UI 모듈",
    "LLM_PLANNER": "사용자 명령과 인식 결과를 로봇 action sequence로 변환하는 계획 모듈",
    "RGBD_CAM": "RGBD 카메라, VLM, YOLO 기반 객체/로봇 인식을 담당하는 perception 모듈",
    "ROBOT": "로봇 primitive 동작과 action sequence 실행을 담당하는 제어 모듈",
    "srv": "공용 service/process utility 모듈",
}


def group_by_package(file_infos):
    groups = defaultdict(list)
    for info in file_infos:
        parts = info.path.parts
        if len(parts) >= 3 and parts[0] == "src":
            groups[parts[1]].append(info)
        elif len(parts) >= 2 and parts[0] == "src":
            groups["ROOT"].append(info)
        elif len(parts) == 1:
            groups["ROOT"].append(info)
        else:
            groups[parts[0]].append(info)
    return dict(sorted(groups.items()))


def summarize_role(package_name):
    return PACKAGE_ROLES.get(package_name, "보조 모듈")


def make_markdown_analysis(file_infos):
    lines = ["# 프로젝트 코드 분석", ""]
    lines.append("## 패키지 요약")

    for package_name, infos in group_by_package(file_infos).items():
        total_lines = sum(info.line_count for info in infos)
        class_count = sum(len(info.classes) for info in infos)
        fn_count = sum(len(info.functions) for info in infos)
        lines.append(
            f"- **{package_name}**: {summarize_role(package_name)} "
            f"({len(infos)} files, {total_lines} lines, {class_count} classes, {fn_count} functions)"
        )

    lines.extend(["", "## 파일별 상세"])
    for info in file_infos:
        lines.append(f"### {info.path}")
        if info.error:
            lines.append(f"- 분석 실패: {info.error}")
            lines.append("")
            continue

        lines.append(f"- 라인 수: {info.line_count}")
        if info.docstring:
            lines.append(f"- 설명: {info.docstring}")

        lines.append("- imports:")
        if info.imports:
            for item in sorted(set(info.imports)):
                lines.append(f"  - {item}")
        else:
            lines.append("  - 없음")

        lines.append("- classes:")
        if info.classes:
            for class_info in info.classes:
                method_text = ", ".join(f"{method}()" for method in class_info.methods)
                lines.append(f"  - {class_info.name}: {method_text or 'method 없음'}")
        else:
            lines.append("  - 없음")

        lines.append("- functions:")
        if info.functions:
            for fn in info.functions:
                lines.append(f"  - {fn}()")
        else:
            lines.append("  - 없음")
        lines.append("")

    return "\n".join(lines)


def make_architecture_summary(file_infos):
    package_groups = group_by_package(file_infos)
    lines = ["# 발표용 아키텍처 요약", ""]
    lines.append("## 한 문장 소개")
    lines.append(
        "이 프로젝트는 RGBD 카메라 인식, LLM 기반 작업 계획, 로봇 action 실행, 사용자 인터페이스, "
        "카메라-로봇 캘리브레이션을 하나의 제어 흐름으로 연결하는 지능형 로봇 제어 시스템이다."
    )
    lines.append("")

    lines.append("## 핵심 실행 흐름")
    flow = [
        "사용자가 Interface에 자연어 명령을 입력한다.",
        "ProjectController가 최신 RGBD frame과 perception 결과를 요청한다.",
        "RGBD_CAM이 VLM, YOLO-World, YOLO-Robot 결과를 구성한다.",
        "CALIBRATION이 camera 좌표를 로봇이 사용할 수 있는 좌표 정보로 변환한다.",
        "LLM_PLANNER가 사용자 명령과 인식 정보를 action sequence로 변환한다.",
        "ROBOT이 action sequence를 primitive 동작으로 실행한다.",
        "Interface가 인식 결과, 계획, 실행 결과를 화면에 갱신한다.",
    ]
    for index, item in enumerate(flow, start=1):
        lines.append(f"{index}. {item}")
    lines.append("")

    lines.append("## 모듈별 발표 포인트")
    for package_name, infos in package_groups.items():
        if package_name == "ROOT":
            continue
        representative_classes = [
            class_info.name
            for info in infos
            for class_info in info.classes
            if not class_info.name.startswith("_")
        ][:5]
        class_text = ", ".join(representative_classes) if representative_classes else "대표 class 없음"
        lines.append(f"- **{package_name}**: {summarize_role(package_name)}")
        lines.append(f"  - 대표 클래스: {class_text}")
    lines.append("")

    lines.append("## Mermaid 구조도")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    lines.append("    User[User] --> Interface[INTERFACE]")
    lines.append("    Interface --> Controller[ProjectController]")
    lines.append("    Controller --> RGBD[RGBD_CAM]")
    lines.append("    RGBD --> Calibration[CALIBRATION]")
    lines.append("    Controller --> Planner[LLM_PLANNER]")
    lines.append("    Planner --> Controller")
    lines.append("    Controller --> Robot[ROBOT]")
    lines.append("    Robot --> Controller")
    lines.append("    Controller --> Interface")
    lines.append("```")
    return "\n".join(lines)


def make_presentation_material(file_infos):
    package_groups = group_by_package(file_infos)
    module_count = len([name for name in package_groups if name != "ROOT"])
    class_count = sum(len(info.classes) for info in file_infos)
    line_count = sum(info.line_count for info in file_infos)

    slides = [
        {
            "title": "프로젝트 소개",
            "bullets": [
                "RGBD 카메라와 로봇 제어를 결합한 지능형 로봇 시스템",
                "자연어 명령을 인식, 계획, 실행 흐름으로 연결",
                "카메라-로봇 좌표 보정을 통해 실제 동작까지 확장",
            ],
            "script": "첫 슬라이드에서는 프로젝트를 한 문장으로 소개합니다. 핵심은 사용자의 명령이 카메라 인식과 LLM 계획을 거쳐 로봇 동작으로 이어진다는 점입니다.",
        },
        {
            "title": "개발 목표",
            "bullets": [
                "사용자 명령을 로봇 action sequence로 변환",
                "RGBD/VLM/YOLO 기반으로 주변 상황과 객체를 인식",
                "UI에서 명령, 인식 결과, 실행 결과를 확인",
            ],
            "script": "개발 목표는 단순한 로봇 동작 실행이 아니라, 사용자가 이해하기 쉬운 인터페이스와 인식 결과를 함께 제공하는 통합 시스템을 만드는 것입니다.",
        },
        {
            "title": "전체 구조",
            "bullets": [
                f"분석 대상: {module_count}개 주요 패키지, {class_count}개 클래스, 약 {line_count}라인",
                "RobotApp이 주요 모듈을 생성하고 ProjectController가 흐름을 조율",
                "각 기능은 INTERFACE, RGBD_CAM, LLM_PLANNER, ROBOT, CALIBRATION으로 분리",
            ],
            "script": "여기서는 구조를 강조합니다. RobotApp은 조립 역할이고, 실제 흐름 제어는 ProjectController가 담당한다는 점을 말하면 좋습니다.",
        },
        {
            "title": "ProjectController의 역할",
            "bullets": [
                "사용자 명령을 받아 작업/재보정/인식 명령으로 분기",
                "RGBD snapshot, LLM plan, robot execution을 순서대로 연결",
                "Interface에 중간 상태와 최종 결과를 지속적으로 publish",
            ],
            "script": "ProjectController는 발표에서 가장 중요한 중심 모듈입니다. 여러 기능을 직접 구현하기보다 각 모듈을 연결하는 orchestrator라는 점을 강조합니다.",
        },
        {
            "title": "Perception: RGBD_CAM",
            "bullets": [
                "RGB frame과 depth 정보를 최신 camera data로 유지",
                "YoloRobot, YoloWorld, VLM을 통해 로봇/객체/장면 정보를 추출",
                "인식 결과를 LLM 계획과 UI 표시에서 재사용",
            ],
            "script": "RGBD_CAM은 로봇이 환경을 이해하기 위한 눈 역할입니다. RGB, depth, 객체 인식 결과가 다음 단계의 입력이 됩니다.",
        },
        {
            "title": "Planning: LLM_PLANNER",
            "bullets": [
                "사용자 명령과 perception summary를 입력으로 사용",
                "로봇이 수행할 action sequence를 생성",
                "Ollama 기반 LLM 호출 구조로 로컬 실행 가능",
            ],
            "script": "이 슬라이드에서는 자연어가 어떻게 로봇 명령 형태로 바뀌는지 설명합니다. LLM은 고수준 명령을 action sequence로 변환하는 계획자입니다.",
        },
        {
            "title": "Control: ROBOT",
            "bullets": [
                "RobotActions가 DNC, WAV, MOV, GRB 같은 primitive action을 관리",
                "ROBOT 대표 클래스가 action sequence 실행과 primitive 제어 API를 제공",
                "ProjectController는 robot.run_sequence 형태로 실행을 위임",
            ],
            "script": "ROBOT 모듈은 계획 결과를 실제 동작으로 바꾸는 부분입니다. action registry 구조 덕분에 새 동작을 추가하기 쉽다는 점을 말할 수 있습니다.",
        },
        {
            "title": "Calibration",
            "bullets": [
                "카메라의 u, v, depth 정보를 로봇 좌표/관절 정보로 변환",
                "RegressionModel을 사용해 보정 모델을 구성",
                "재보정 흐름을 CALIBRATION 패키지로 분리해 유지보수성 개선",
            ],
            "script": "캘리브레이션은 인식과 제어를 연결하는 다리입니다. 카메라에서 보이는 위치가 로봇이 움직일 수 있는 좌표로 바뀌어야 실제 조작이 가능합니다.",
        },
        {
            "title": "Interface",
            "bullets": [
                "사용자 명령 입력과 상태 표시를 담당",
                "PyQt5 프로세스로 UI를 분리해 메인 로직과 화면 갱신을 분리",
                "RGBD frame, 인식 결과, action 결과를 한 화면에 표시",
            ],
            "script": "Interface는 사용자가 시스템 상태를 확인하는 창입니다. UI 프로세스를 분리해 로봇/카메라 루프와 화면 이벤트 루프가 서로 방해하지 않게 구성했습니다.",
        },
        {
            "title": "시연 및 향후 개선",
            "bullets": [
                "시연: main.py 실행 후 RGBD 화면, 명령 입력, action 결과 확인",
                "개선: 예외 처리, 로그 체계, action 확장, 모델 정확도 개선",
                "확장: 다른 로봇이나 다른 perception 모델로 교체 가능한 구조",
            ],
            "script": "마지막에는 현재 구현된 시연 흐름과 앞으로의 개선점을 정리합니다. 특히 모듈 분리 덕분에 확장 가능하다는 결론으로 마무리하면 자연스럽습니다.",
        },
    ]

    lines = ["# 발표자료 초안", ""]
    for index, slide in enumerate(slides, start=1):
        lines.append(f"## Slide {index}. {slide['title']}")
        lines.append("### 화면에 넣을 내용")
        for bullet in slide["bullets"]:
            lines.append(f"- {bullet}")
        lines.append("### 발표 대본")
        lines.append(slide["script"])
        lines.append("")

    lines.append("## 발표 순서 추천")
    lines.append("1. 문제 정의와 목표를 먼저 설명한다.")
    lines.append("2. 전체 아키텍처를 보여준 뒤 ProjectController 중심 흐름을 설명한다.")
    lines.append("3. RGBD_CAM, LLM_PLANNER, ROBOT, CALIBRATION, INTERFACE를 기능 단위로 설명한다.")
    lines.append("4. 실제 시연 장면과 개선 가능성으로 마무리한다.")
    return "\n".join(lines)


def make_json_summary(file_infos):
    data = []
    for info in file_infos:
        data.append(
            {
                "path": str(info.path),
                "line_count": info.line_count,
                "imports": sorted(set(info.imports)),
                "classes": [
                    {
                        "name": class_info.name,
                        "methods": class_info.methods,
                        "docstring": class_info.docstring,
                    }
                    for class_info in info.classes
                ],
                "functions": info.functions,
                "docstring": info.docstring,
                "error": info.error,
            }
        )
    return json.dumps(data, ensure_ascii=False, indent=2)


def make_report_prompt(project_tree, project_analysis, architecture_summary):
    return f"""
너는 캡스톤 디자인 발표자료 작성을 돕는 조교다.

아래 프로젝트 구조와 코드 분석 결과를 바탕으로 한국어 발표용 보고서를 작성하라.

작성 조건:
- 코드에 없는 내용을 지어내지 마라.
- 발표자료 제작에 바로 활용할 수 있게 작성하라.
- 기능 설명보다 "왜 이런 모듈 구조가 필요한지"와 "실행 흐름"을 강조하라.
- 분량은 A4 2장 정도로 작성하라.
- 마지막에 7분 발표용 흐름을 bullet로 정리하라.

[프로젝트 tree]
{project_tree}

[파일별 분석 결과]
{project_analysis}

[아키텍처 요약]
{architecture_summary}
"""
