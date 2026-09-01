"""Evaluation dataset utilities."""

from __future__ import annotations

from pathlib import Path
import json


def load_jsonl_dataset(path: str | Path) -> list[dict]:
    dataset_path = Path(path)
    return [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
