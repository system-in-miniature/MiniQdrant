from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError

import pytest

from miniqdrant import (
    ClosedResourceError,
    Database,
    Distance,
    Point,
    SearchRequest,
)
from miniqdrant.optimizer.failures import OptimizationGate


def test_close_is_idempotent_and_rejects_new_collection_work(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.close()
    collection.close()

    with pytest.raises(ClosedResourceError):
        collection.upsert([Point(1, (1.0, 0.0), {})])
    with pytest.raises(ClosedResourceError):
        collection.search(SearchRequest((1.0, 0.0), 1))


def test_database_close_closes_owned_collections(tmp_path) -> None:
    database = Database.open(tmp_path)
    collection = database.create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )

    database.close()
    database.close()

    with pytest.raises(ClosedResourceError):
        database.collection("items")
    with pytest.raises(ClosedResourceError):
        collection.retrieve([1])


def test_close_waits_for_active_optimizer_before_closing_wal(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {})])
    gate = OptimizationGate()
    optimizer = collection.start_optimize(gate=gate)
    gate.wait_until("sources_captured")

    with ThreadPoolExecutor(max_workers=1) as executor:
        close = executor.submit(collection.close)
        with pytest.raises(TimeoutError):
            close.result(timeout=0.05)
        gate.release("finish_build")
        close.result(timeout=5)

    optimizer.result(timeout=5)
    reopened = Database.open(tmp_path).collection("items")
    assert reopened.retrieve([1])[0].id == 1


def test_close_waits_for_owned_collection_views(tmp_path) -> None:
    collection = Database.open(tmp_path).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {})])
    view = collection.capture_view()

    with ThreadPoolExecutor(max_workers=1) as executor:
        close = executor.submit(collection.close)
        with pytest.raises(TimeoutError):
            close.result(timeout=0.05)
        view.close()
        close.result(timeout=5)

    assert collection.closed
