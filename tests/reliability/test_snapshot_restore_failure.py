from __future__ import annotations

import json

import pytest

from miniqdrant import Database, Distance, Point, SnapshotError


def test_invalid_snapshot_never_replaces_live_collection(tmp_path) -> None:
    database_path = tmp_path / "db"
    database = Database.open(database_path)
    live = database.create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    live.upsert([Point(1, (1.0, 0.0), {"source": "live"})])
    live.flush()

    source = Database.open(tmp_path / "source").create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    source.upsert([Point(2, (0.0, 1.0), {"source": "snapshot"})])
    snapshot = source.create_snapshot(tmp_path / "snapshot")
    metadata_path = snapshot / "snapshot.json"
    metadata = json.loads(metadata_path.read_text())
    first_file = next(iter(metadata["files"]))
    (snapshot / "collection" / first_file).write_bytes(b"corrupt")

    with pytest.raises(SnapshotError):
        Database.restore_collection(
            snapshot,
            database_path,
            "items",
            replace=True,
        )

    assert live.retrieve([1])[0].payload["source"] == "live"
    assert (database_path / "collections" / "items").is_dir()


def test_snapshot_publish_failure_leaves_no_partial_target(tmp_path) -> None:
    collection = Database.open(tmp_path / "db").create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    collection.upsert([Point(1, (1.0, 0.0), {})])
    destination = tmp_path / "backups" / "sp-1"

    def fail(stage: str) -> None:
        if stage == "before_snapshot_publish":
            raise RuntimeError(stage)

    with pytest.raises(RuntimeError, match="before_snapshot_publish"):
        collection.create_snapshot(destination, failure_injector=fail)

    assert not destination.exists()


def test_restore_publish_failure_rolls_back_previous_collection(tmp_path) -> None:
    database_path = tmp_path / "db"
    database = Database.open(database_path)
    original = database.create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    original.upsert([Point(1, (1.0, 0.0), {"source": "original"})])
    original.flush()
    database.close()

    replacement = Database.open(tmp_path / "replacement").create_collection(
        "items",
        dimension=2,
        distance=Distance.DOT,
    )
    replacement.upsert([Point(2, (0.0, 1.0), {"source": "replacement"})])
    snapshot = replacement.create_snapshot(tmp_path / "valid-snapshot")

    def fail(stage: str) -> None:
        if stage == "before_restore_publish":
            raise RuntimeError(stage)

    with pytest.raises(RuntimeError, match="before_restore_publish"):
        Database.restore_collection(
            snapshot,
            database_path,
            "items",
            replace=True,
            failure_injector=fail,
        )

    reopened = Database.open(database_path).collection("items")
    assert reopened.retrieve([1])[0].payload["source"] == "original"
    assert reopened.retrieve([2]) == ()
