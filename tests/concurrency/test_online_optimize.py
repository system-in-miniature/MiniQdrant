from __future__ import annotations

from miniqdrant import Database, Distance, Point, SearchRequest
from miniqdrant.optimizer.failures import OptimizationGate


def test_write_during_build_wins_after_publish(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {"version": "old"})])
    gate = OptimizationGate()

    handle = collection.start_optimize(gate=gate)
    gate.wait_until("sources_captured")
    collection.upsert([Point(1, (0.0, 1.0), {"version": "new"})])
    assert collection.retrieve([1])[0].payload["version"] == "new"
    gate.release("finish_build")
    handle.result(timeout=5)

    point = collection.retrieve([1])[0]
    assert point.payload["version"] == "new"
    assert collection.search(SearchRequest((1.0, 0.0), 10, exact=True)).hits[0].score == 0.0


def test_existing_view_can_finish_after_merge(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {})])
    collection.flush(indexed=True)
    old_view = collection.capture_view()
    old_paths = old_view.segment_paths

    collection.optimize()

    assert old_view.search(SearchRequest((1.0, 0.0), 1)).hits[0].id == 1
    assert all(path.exists() for path in old_paths)
    old_view.close()
    assert all(not path.exists() for path in old_paths)

