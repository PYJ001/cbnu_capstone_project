import argparse
from pathlib import Path

from .analyzer import DEFAULT_IGNORE_DIRS, analyze_project, get_tree
from .ollama import ask_ollama
from .renderers import (
    make_architecture_summary,
    make_json_summary,
    make_markdown_analysis,
    make_presentation_material,
    make_report_prompt,
)

DEFAULT_MODEL = "deepseek-coder-v2:16b"
DEFAULT_OUTPUT_DIR = "code_analysis_output"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="code-analysis",
        description="Analyze a Python project and generate presentation-ready materials.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root to analyze. Default: current directory.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for generated files. Default: {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--tree-depth",
        type=int,
        default=4,
        help="Maximum directory depth for project_tree.txt.",
    )
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Generate project_report.md with Ollama. Disabled by default for fast local runs.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model name. Default: {DEFAULT_MODEL}.",
    )
    return parser.parse_args(argv)


def write_outputs(root, output_dir, tree_depth=4, use_ollama=False, model=DEFAULT_MODEL):
    root = Path(root).resolve()
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    try:
        ignore_dirs.add(output_dir.relative_to(root).parts[0])
    except ValueError:
        pass

    project_tree = get_tree(root, depth=tree_depth, ignore_dirs=ignore_dirs)
    file_infos = analyze_project(root, ignore_dirs=ignore_dirs)
    project_analysis = make_markdown_analysis(file_infos)
    architecture_summary = make_architecture_summary(file_infos)
    presentation_material = make_presentation_material(file_infos)

    outputs = {
        "project_tree.txt": project_tree,
        "project_analysis.md": project_analysis,
        "project_analysis.json": make_json_summary(file_infos),
        "architecture_summary.md": architecture_summary,
        "presentation_material.md": presentation_material,
    }

    if use_ollama:
        report_prompt = make_report_prompt(
            project_tree=project_tree,
            project_analysis=project_analysis,
            architecture_summary=architecture_summary,
        )
        report = ask_ollama(report_prompt, model=model)
        if report is None:
            report = (
                "# 프로젝트 발표 보고서\n\n"
                "Ollama 또는 requests 패키지를 사용할 수 없어 LLM 보고서 생성을 건너뛰었습니다.\n"
                "`architecture_summary.md`와 `presentation_material.md`를 발표자료 초안으로 사용하세요.\n"
            )
    else:
        report = (
            "# 프로젝트 발표 보고서\n\n"
            "기본 실행에서는 빠른 발표자료 생성을 위해 Ollama 보고서 생성을 건너뜁니다.\n\n"
            "발표자료 제작에는 아래 파일을 우선 사용하세요.\n"
            "- `architecture_summary.md`: 전체 구조와 실행 흐름 요약\n"
            "- `presentation_material.md`: 슬라이드별 화면 내용과 발표 대본\n"
            "- `project_analysis.md`: 파일별 import/class/function 상세 분석\n\n"
            "`--ollama`를 붙이면 LLM 기반 장문 보고서를 생성합니다.\n"
        )
    outputs["project_report.md"] = report

    written = []
    for filename, content in outputs.items():
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def main(argv=None):
    args = parse_args(argv)
    written = write_outputs(
        root=args.root,
        output_dir=args.output_dir,
        tree_depth=args.tree_depth,
        use_ollama=args.ollama,
        model=args.model,
    )

    print("생성 완료:")
    for path in written:
        print(f"- {path}")
