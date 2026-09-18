"""Run the repository azd environment validation hook."""

from __future__ import annotations

import runpy
from pathlib import Path

repository_root = Path(__file__).resolve().parents[3]
runpy.run_path(
    str(repository_root / "scripts" / "validate_azd_environment.py"),
    run_name="__main__",
)