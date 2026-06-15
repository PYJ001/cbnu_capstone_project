import subprocess
from pathlib import Path
import ast
import requests

ROOT = Path(".")
MODEL = "deepseek-coder-v2:16b"

IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".vscode",
    "build",
    "install",
    "log",
    "runs",
    "recordings",
    "recordings_new_auto_labeled",
}

def should_skip(path):
    return any(part in IGNORE_DIRS for part in path.parts)

def get_tree():
    cmd = [
        "tree",
        "-L",
        "3",
        "-I",
        "__pycache__|*.pt|*.jpg|*.png|*.mp4|runs|recordings|build|install|log"
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    return result.stdout

def analyze_python_file(path):
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except Exception as e:
        return f"## {path}\n분석 실패: {e}\n"

    imports = []
    classes = []
    functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}")

        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)

            classes.append((node.name, methods))

        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)

    lines = []
    lines.append(f"## {path}")

    lines.append("### imports")
    if imports:
        for item in sorted(set(imports)):
            lines.append(f"- {item}")
    else:
        lines.append("- 없음")

    lines.append("### classes")
    if classes:
        for class_name, methods in classes:
            lines.append(f"- {class_name}")
            for method in methods:
                lines.append(f"  - {method}()")
    else:
        lines.append("- 없음")

    lines.append("### functions")
    if functions:
        for fn in sorted(set(functions)):
            lines.append(f"- {fn}()")
    else:
        lines.append("- 없음")

    lines.append("")
    return "\n".join(lines)

def analyze_project():
    py_files = [
        path for path in ROOT.rglob("*.py")
        if not should_skip(path)
    ]

    result = []
    for path in py_files:
        result.append(analyze_python_file(path))

    return "\n".join(result)

def ask_ollama(prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()
    return response.json()["response"]

def main():
    project_tree = get_tree()
    project_analysis = analyze_project()

    Path("project_tree.txt").write_text(project_tree, encoding="utf-8")
    Path("project_analysis.md").write_text(project_analysis, encoding="utf-8")

    prompt = f"""
너는 Python 프로젝트 구조를 분석해서 보고서를 작성하는 도우미다.

아래에는 프로젝트의 tree 구조와 각 Python 파일의 import, class, function 목록이 있다.

주의사항:
- 함수 내부 기능을 과하게 추측하지 마라.
- 코드에 없는 내용을 지어내지 마라.
- 파일명, import 관계, class 이름, function 이름을 근거로 설명하라.
- A4 2장 정도 분량의 한국어 보고서로 작성하라.
- 문체는 대학 과제 보고서처럼 자연스럽게 작성하라.
- 너무 세부적인 코드 설명보다는 파일 간 관계와 전체 구조를 중심으로 설명하라.

보고서 구성:
1. 프로젝트 개요
2. 전체 폴더 구조
3. 주요 파일별 역할
4. import 관계를 통해 본 모듈 연결
5. class/function 목록을 통해 본 구현 요소
6. 전체 실행 흐름 요약
7. 정리 및 개선 가능성

[프로젝트 tree]
{project_tree}

[파일별 분석 결과]
{project_analysis}
"""

    report = ask_ollama(prompt)

    Path("project_report.md").write_text(report, encoding="utf-8")

    print("생성 완료:")
    print("- project_tree.txt")
    print("- project_analysis.md")
    print("- project_report.md")

if __name__ == "__main__":
    main()