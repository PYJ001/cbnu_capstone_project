import ast
import subprocess
from pathlib import Path

from .models import ClassInfo, FileInfo


DEFAULT_IGNORE_DIRS = {
    "__pycache__",
    ".git",
    ".vscode",
    ".idea",
    ".pytest_cache",
    "build",
    "dist",
    "install",
    "log",
    "logs",
    "runs",
    "trash",
    "trash0604",
    "trash0608",
    "recordings",
    "recordings_new_auto_labeled",
    "robot_camera_calibration_samples",
    "code_analysis_output",
}

DEFAULT_IGNORE_FILE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".mp4",
    ".webm",
    ".pt",
    ".pyc",
}


def should_skip(path, ignore_dirs=None, ignore_suffixes=None):
    ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
    ignore_suffixes = ignore_suffixes or DEFAULT_IGNORE_FILE_SUFFIXES
    if any(part in ignore_dirs for part in path.parts):
        return True
    return path.suffix.lower() in ignore_suffixes


def get_tree(root, depth=4, ignore_dirs=None):
    root = Path(root)
    ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
    ignored = "|".join(
        sorted(
            {
                "__pycache__",
                "*.pt",
                "*.jpg",
                "*.jpeg",
                "*.png",
                "*.mp4",
                "*.webm",
                *ignore_dirs,
            }
        )
    )
    cmd = ["tree", "-L", str(depth), "-I", ignored]

    try:
        result = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return make_fallback_tree(root, depth=depth, ignore_dirs=ignore_dirs)

    return result.stdout if result.stdout.strip() else make_fallback_tree(root, depth=depth, ignore_dirs=ignore_dirs)


def make_fallback_tree(root, depth=4, ignore_dirs=None):
    root = Path(root)
    lines = ["."]
    paths = sorted(path for path in root.rglob("*") if not should_skip(path.relative_to(root), ignore_dirs))
    for path in paths:
        relative = path.relative_to(root)
        item_depth = len(relative.parts) - 1
        if item_depth > depth:
            continue
        indent = "    " * item_depth
        marker = "/" if path.is_dir() else ""
        lines.append(f"{indent}{relative.name}{marker}")
    return "\n".join(lines)


def normalize_docstring(text):
    if not text:
        return ""
    return " ".join(text.strip().split())


def analyze_python_file(path, display_path=None):
    path = Path(path)
    info = FileInfo(path=Path(display_path) if display_path else path)

    try:
        text = path.read_text(encoding="utf-8")
        info.line_count = len(text.splitlines())
        tree = ast.parse(text)
    except Exception as e:
        info.error = str(e)
        return info

    info.docstring = normalize_docstring(ast.get_docstring(tree))

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                info.imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imported = f"{module}.{alias.name}" if module else alias.name
                info.imports.append(imported)

        elif isinstance(node, ast.ClassDef):
            methods = [
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            info.classes.append(
                ClassInfo(
                    name=node.name,
                    methods=methods,
                    docstring=normalize_docstring(ast.get_docstring(node)),
                )
            )

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.functions.append(node.name)

    return info


def analyze_project(root=".", ignore_dirs=None):
    root = Path(root).resolve()
    ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
    py_files = sorted(
        path
        for path in root.rglob("*.py")
        if not should_skip(path.relative_to(root), ignore_dirs)
    )
    return [
        analyze_python_file(path, display_path=path.relative_to(root))
        for path in py_files
    ]
