"""Public API lab: observe immutable segment creation and compaction.

The experiment uses exported ``Database`` and ``Collection`` operations.
``segment_statistics`` exposes the mechanism's shape without directly
constructing or mutating internal segment objects.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from miniqdrant import Database, Distance, Point


def run_segments_lab(path: str | Path) -> dict[str, int]:
    database = Database.open(path)
    try:
        collection = database.create_collection(
            "items",
            dimension=2,
            distance=Distance.DOT,
        )
        collection.upsert([Point(1, (1.0, 0.0), {})])
        collection.flush()
        collection.upsert([Point(2, (0.0, 1.0), {})])
        collection.flush()
        before = collection.segment_statistics().segment_count
        collection.optimize()
        after = collection.segment_statistics().segment_count
        return {"before_segments": before, "after_segments": after}
    finally:
        database.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="miniqdrant-segments-") as path:
        result = run_segments_lab(path)

    print("Segments lab: two upsert+flush rounds followed by optimize")
    print(f"Segments before optimize: {result['before_segments']}")
    print(f"Segments after optimize: {result['after_segments']}")
    print()
    print("Interpretation:")
    print("- each flush publishes an immutable segment, so the count first reaches two.")
    print("- optimize compacts those segments into one while preserving collection contents.")


if __name__ == "__main__":
    main()
