from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_sloc_report_is_deterministic_and_additive() -> None:
    command = [sys.executable, "tools/count_sloc.py"]
    root = Path(__file__).resolve().parents[1]
    first = json.loads(
        subprocess.run(
            command,
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    second = json.loads(
        subprocess.run(
            command,
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    assert first == second
    assert first["total"] == sum(first["files"].values())
    assert first["files"]["src/miniqdrant/collection.py"] > 100
    assert all(count > 0 for count in first["files"].values())
