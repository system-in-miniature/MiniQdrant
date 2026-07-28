from __future__ import annotations

import pytest

from miniqdrant.persistence.manifest import Manifest, ManifestStore


class InjectedFailure(RuntimeError):
    pass


def test_failed_current_swap_keeps_old_manifest(tmp_path) -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "before_current_replace":
            raise InjectedFailure(stage)

    store = ManifestStore(tmp_path, failure_injector=fail)
    store.publish(Manifest(1, "schema", ("seg-a",), 10))
    armed = True

    with pytest.raises(InjectedFailure):
        store.publish(Manifest(2, "schema", ("seg-b",), 20))

    assert store.load_current() == Manifest(1, "schema", ("seg-a",), 10)

