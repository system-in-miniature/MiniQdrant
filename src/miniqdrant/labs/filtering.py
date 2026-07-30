"""Public API lab: observe payload filtering and the selected search plan.

The experiment uses only symbols exported by ``miniqdrant``. It demonstrates
the filtering mechanism without reaching into planner or segment internals.
"""

from __future__ import annotations

import tempfile
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="miniqdrant-filtering-") as path:
        result = run_filtering_lab(path)

    print("Filtering lab: query=(1.0, 0.0), tenant='a', limit=10")
    print(f"Matching ids: {result['matching_ids']}")
    print(f"Selected plan: {result['plan']}")
    print()
    print("Interpretation:")
    print("- point 2 is vector-similar but excluded because its tenant is 'b'.")
    print("- the payload index lets the public collection API plan a filtered search.")


if __name__ == "__main__":
    main()
