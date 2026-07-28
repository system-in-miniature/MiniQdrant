from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_project_identity_is_frozen() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert metadata["project"]["name"] == "miniqdrant"
    assert metadata["project"]["requires-python"] == ">=3.12"
    assert metadata["project"]["scripts"] == {"miniqdrant": "miniqdrant.cli:main"}
    assert metadata["project"]["dependencies"] == []


def test_project_and_course_are_separate() -> None:
    assert not (ROOT / "course").exists()
    assert not list(ROOT.glob("day[0-9][0-9].md"))
