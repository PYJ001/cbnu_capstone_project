#!/usr/bin/env python3
"""
Run an overnight Codex improvement pass on this repository.

Usage:
    python3 ralph.py

The script prepares a local `ralph` branch, then runs `codex exec` with a
project-specific prompt. It does not commit or push changes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_BRANCH = "ralph"
DEFAULT_MODEL = "gpt-5"


PROMPT = """
You are working overnight on this OpenManipulatorX capstone robot project.

Objective:
Improve the project in small, reviewable steps, then leave a clear report for
the human developer to inspect tomorrow.

Hard rules:
- Work only inside this repository.
- Do not push to GitHub.
- Do not commit automatically unless explicitly asked by the user.
- Do not modify main.py unless absolutely necessary.
- Keep RobotApp.py as a thin framework/wiring layer.
- Put behavior in relevant src modules/classes.
- Do not touch trash, trash0604, trash0608, __pycache__, calibration image
  dumps, generated sample images, or model weight files.
- Do not delete user data.
- Do not run destructive git commands such as reset --hard, checkout --,
  clean -fd, or force push.
- Prefer simple KISS changes over broad rewrites.
- Hardware-dependent robot/camera behavior must remain conservative.

Project context:
- main.py should stay minimal and instantiate RobotApp.
- PyQt5 interface lives in src/interface_pyqt5.py.
- Robot execution is coordinated by src/RobotCommandController.py.
- RGBD camera, YOLO robot detection, YOLO-World classes, depth, and
  calibration prediction live in src/RGBD.py.
- VLM world class updates live in src/VLM.py and src/VLMWorldClassUpdater.py.
- Robot action definitions live in src/robot_actions.py.
- Robot low-level movement and calibration model helpers live in
  src/RobotManager.py.
- Calibration data collection lives in collect_calibration_samples.py.
- Teleoperation motion recording/replay lives in test_record_motion.py and
  src/MotionTrajectory.py.

Suggested work order:
1. Inspect the repository structure and read the important files.
2. Run:
   python3 -m py_compile main.py collect_calibration_samples.py test_record_motion.py src/*.py
3. Fix concrete bugs, missing imports, brittle edge cases, and small design
   inconsistencies.
4. Improve documentation only where it helps future operation.
5. Add or update docs/ralph_report.md with:
   - What you changed
   - Why you changed it
   - Commands/tests run
   - Remaining risks
   - Recommended next manual checks on the real robot
6. Stop with changes left in the working tree for human review.

When uncertain, make the smallest useful change and explain the uncertainty in
docs/ralph_report.md.
""".strip()


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, text=True, check=check)


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def ensure_git_repo(project_dir: Path) -> None:
    try:
        inside = output(["git", "rev-parse", "--is-inside-work-tree"], project_dir)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Not a git repository: {project_dir}") from exc

    if inside != "true":
        raise SystemExit(f"Not a git repository: {project_dir}")


def ensure_branch(project_dir: Path, branch: str, allow_dirty: bool) -> None:
    status_lines = output(["git", "status", "--porcelain"], project_dir).splitlines()
    meaningful_status = [
        line for line in status_lines
        if line[3:] not in {"ralph.py", "./ralph.py"}
    ]

    if meaningful_status and not allow_dirty:
        raise SystemExit(
            "Working tree is dirty. Review or commit/stash changes first, "
            "or rerun with --allow-dirty."
        )

    current = output(["git", "branch", "--show-current"], project_dir)
    exists = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=project_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    ).returncode == 0

    if current == branch:
        return

    if exists:
        run(["git", "checkout", branch], project_dir)
        return

    run(["git", "checkout", "-b", branch], project_dir)


def build_codex_command(project_dir: Path, model: str | None) -> list[str]:
    cmd = [
        "codex",
        "exec",
        "-C",
        str(project_dir),
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
    ]

    if model:
        cmd.extend(["--model", model])

    cmd.append("-")
    return cmd


def run_codex(project_dir: Path, model: str | None) -> int:
    if shutil.which("codex") is None:
        raise SystemExit("codex CLI was not found in PATH.")

    logs_dir = project_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"ralph_{stamp}.log"

    cmd = build_codex_command(project_dir, model)
    print("+", " ".join(cmd[:-1]), "< prompt", flush=True)
    print(f"[ralph] log: {log_path}", flush=True)

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert process.stdin is not None
        assert process.stdout is not None

        process.stdin.write(PROMPT)
        process.stdin.close()

        for line in process.stdout:
            print(line, end="")
            log_file.write(line)

        return process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ralph overnight Codex pass.")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Repository to improve. Defaults to the directory containing ralph.py.",
    )
    parser.add_argument(
        "--branch",
        default=DEFAULT_BRANCH,
        help=f"Working branch to create/use. Default: {DEFAULT_BRANCH}",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Codex model to use. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow starting even if the working tree already has changes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()

    ensure_git_repo(project_dir)
    ensure_branch(project_dir, args.branch, args.allow_dirty)

    code = run_codex(project_dir, args.model)

    print("\n[ralph] finished")
    run(["git", "status", "--short", "--branch"], project_dir, check=False)
    return code


if __name__ == "__main__":
    sys.exit(main())
