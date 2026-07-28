from __future__ import annotations

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
