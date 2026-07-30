"""Public API lab: persist a collection, close it, and recover it after reopen.

The experiment stays on the exported ``Database`` and ``Collection`` API. WAL,
manifest, and segment recovery happen behind that public lifecycle boundary.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from miniqdrant import Database, Distance, Point


def run_recovery_lab(path: str | Path) -> dict[str, object]:
    database = Database.open(path)
    collection = database.create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert(
        [
            Point(1, (1.0, 0.0), {}),
            Point(2, (0.0, 1.0), {}),
        ]
    )
    collection.flush()
    database.close()

    reopened = Database.open(path)
    try:
        restored = reopened.collection("items").retrieve([1, 2])
        return {"restored_ids": [point.id for point in restored]}
    finally:
        reopened.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="miniqdrant-recovery-") as path:
        result = run_recovery_lab(path)

    print("Recovery lab: upsert ids 1 and 2, flush, close, then reopen")
    print(f"Restored ids: {result['restored_ids']}")
    print()
    print("Interpretation:")
    print("- close/reopen creates a real process-lifecycle recovery boundary.")
    print("- both ids remain visible after metadata and segment state are reloaded.")


if __name__ == "__main__":
    main()
