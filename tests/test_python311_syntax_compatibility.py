"""Compile project modules on the actual CI interpreter before frontend assertions.
GitHub runs this on Python 3.11; a newer interpreter alone is not a 3.11 syntax check.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_project_modules_compile_on_supported_ci_runtime():
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {"__pycache__", ".pytest_cache", ".git", ".venv"} for part in path.relative_to(ROOT).parts):
            continue
        compile(path.read_bytes(), str(path), "exec")
