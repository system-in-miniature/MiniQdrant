from __future__ import annotations

from pathlib import Path

from miniqdrant import Database, Distance, Filter, Match, PayloadSchema, Point, SearchRequest


def run_filtering_lab(path: str | Path) -> dict[str, object]:
    database = Database.open(path)
    try:
        collection = database.create_collection(
            "items",
            dimension=2,
            distance=Distance.DOT,
        )
        collection.upsert(
            [
                Point(1, (1.0, 0.0), {"tenant": "a"}),
                Point(2, (0.9, 0.0), {"tenant": "b"}),
                Point(3, (0.8, 0.0), {"tenant": "a"}),
            ]
        )
        collection.create_payload_index("tenant", PayloadSchema.KEYWORD)
        result = collection.search(
            SearchRequest(
                (1.0, 0.0),
                10,
                filter=Filter(must=(Match("tenant", "a"),)),
            )
        )
        return {"matching_ids": [hit.id for hit in result.hits], "plan": result.plan}
    finally:
        database.close()
