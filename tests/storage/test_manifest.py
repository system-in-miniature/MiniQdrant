from __future__ import annotations

import pytest

from miniqdrant.errors import CorruptionError
from miniqdrant.persistence.manifest import Manifest, ManifestStore


def manifest(generation: int, *segments: str) -> Manifest:
    return Manifest(
        generation=generation,
        schema_fingerprint="schema-1",
        segment_ids=segments,
        replay_boundary=generation * 10,
    )


def test_manifest_publish_and_load_current(tmp_path) -> None:
    store = ManifestStore(tmp_path)

    store.publish(manifest(1, "seg-a"))
    store.publish(manifest(2, "seg-a", "seg-b"))

    assert store.load_current() == manifest(2, "seg-a", "seg-b")
    assert (tmp_path / "CURRENT").read_text() == "manifest-00000000000000000002.json\n"


def test_manifest_generation_must_increase(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    store.publish(manifest(2, "seg-a"))

    with pytest.raises(ValueError, match="generation"):
        store.publish(manifest(2, "seg-b"))


def test_missing_current_manifest_is_corruption(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    (tmp_path / "CURRENT").write_text("manifest-00000000000000000099.json\n")

    with pytest.raises(CorruptionError, match="manifest"):
        store.load_current()

