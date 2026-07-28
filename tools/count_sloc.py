from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count_python_sloc(*, include_tests: bool = False) -> dict[str, object]:
    roots = [ROOT / "src"]
    if include_tests:
        roots.extend((ROOT / "tests", ROOT / "tools"))
    files = sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    counts = {
        path.relative_to(ROOT).as_posix(): _count_file(path)
        for path in files
    }
    return {"files": counts, "total": sum(counts.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Count nonblank Python source lines.")
    parser.add_argument("--include-tests", action="store_true")
    options = parser.parse_args()
    print(
        json.dumps(
            count_python_sloc(include_tests=options.include_tests),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _count_file(path: Path) -> int:
    return sum(
        bool(stripped) and not stripped.startswith("#")
        for line in path.read_text().splitlines()
        if (stripped := line.strip())
    )


if __name__ == "__main__":
    raise SystemExit(main())
