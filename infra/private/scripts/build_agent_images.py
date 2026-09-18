"""Run the repository hosted-agent image build hook."""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runpy.run_path(
        str(repository_root / "scripts" / "build_agent_images.py"),
        run_name="__main__",
    )


if __name__ == "__main__":
    main()