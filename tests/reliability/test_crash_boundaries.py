from __future__ import annotations

import pytest

from miniqdrant import Database, Distance, Point


class InjectedFailure(RuntimeError):
    pass


class OneShotFailure:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.armed = True

    def __call__(self, stage: str) -> None:
        if self.armed and stage == self.stage:
            self.armed = False
            raise InjectedFailure(stage)


def test_crash_after_wal_fsync_before_apply_recovers_once(tmp_path) -> None:
    failure = OneShotFailure("after_wal_fsync")
    database = Database.open(tmp_path, failure_injector=failure)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)

    with pytest.raises(InjectedFailure):
        collection.upsert([Point(1, (1.0, 0.0), {})])

    database.simulate_process_loss()
    reopened = Database.open(tmp_path).collection("items")

    assert reopened.count() == 1
    assert reopened.retrieve([1])[0].version == 1


def test_failed_manifest_publish_replays_wal_without_half_segment(tmp_path) -> None:
    failure = OneShotFailure("before_current_replace")
    database = Database.open(tmp_path, failure_injector=failure)
    collection = database.create_collection("items", dimension=2, distance=Distance.DOT)
    collection.upsert([Point(1, (1.0, 0.0), {})])

    with pytest.raises(InjectedFailure):
        collection.flush(indexed=True)

    database.simulate_process_loss()
    reopened = Database.open(tmp_path).collection("items")

    assert reopened.count() == 1
    assert reopened.retrieve([1])[0].version == 1

