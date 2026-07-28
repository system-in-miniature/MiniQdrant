from __future__ import annotations

import pytest

from miniqdrant import Database, Distance, Point


class InjectedFailure(RuntimeError):
    pass


class ArmedFailure:
    def __init__(self) -> None:
        self.armed = False

    def __call__(self, stage: str) -> None:
        if self.armed and stage == "before_current_replace":
            self.armed = False
            raise InjectedFailure(stage)


def test_failed_optimizer_publish_keeps_old_segments_searchable(tmp_path) -> None:
    failure = ArmedFailure()
    collection = Database.open(tmp_path, failure_injector=failure).create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {})])
    collection.flush()
    old_paths = collection.segment_paths
    failure.armed = True

    with pytest.raises(InjectedFailure):
        collection.optimize()

    assert collection.retrieve([1])[0].id == 1
    assert collection.segment_paths == old_paths
    assert all(path.exists() for path in old_paths)

