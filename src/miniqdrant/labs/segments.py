from __future__ import annotations

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
