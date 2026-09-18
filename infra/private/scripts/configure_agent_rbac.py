"""Run the repository hosted-agent RBAC hook."""

from __future__ import annotations

import runpy
from pathlib import Path

repository_root = Path(__file__).resolve().parents[3]
runpy.run_path(
    str(repository_root / "scripts" / "configure_agent_rbac.py"),
    run_name="__main__",
)