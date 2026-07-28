from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from miniqdrant.config import config_fingerprint
from miniqdrant.errors import SnapshotError
from miniqdrant.persistence.fsync import fsync_directory
from miniqdrant.persistence.manifest import Manifest, ManifestStore
from miniqdrant.persistence.metadata import read_collection_metadata
from miniqdrant.segment.codec import SegmentCodec

_FORMAT_VERSION = 1


def create_collection_snapshot(
    source: Path,
    destination: Path,
    manifest: Manifest,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> Path:
    failure = failure_injector or (lambda _stage: None)
    destination = destination.resolve()
    if destination.exists():
        raise SnapshotError(f"snapshot destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        collection = temporary / "collection"
        collection.mkdir()
        _copy_file(source / "collection.json", collection / "collection.json")
        _copy_file(source / "CURRENT", collection / "CURRENT")
        _copy_file(
            source / manifest.filename,
            collection / manifest.filename,
        )
        shutil.copytree(source / "wal", collection / "wal")
        (collection / "segments").mkdir()
        for segment_id in manifest.segment_ids:
            shutil.copytree(
                source / "segments" / segment_id,
                collection / "segments" / segment_id,
            )
        files = {
            path.relative_to(collection).as_posix(): _sha256(path)
            for path in sorted(collection.rglob("*"))
            if path.is_file()
        }
        metadata = {
            "format_version": _FORMAT_VERSION,
            "files": files,
        }
        snapshot_metadata = temporary / "snapshot.json"
        snapshot_metadata.write_bytes(_canonical_json(metadata))
        _fsync_tree(temporary)
        failure("before_snapshot_publish")
        os.replace(temporary, destination)
        fsync_directory(destination.parent)
        return destination
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def validate_collection_snapshot(snapshot: Path) -> Path:
    snapshot = snapshot.resolve()
    try:
        metadata = json.loads((snapshot / "snapshot.json").read_bytes())
        if metadata["format_version"] != _FORMAT_VERSION:
            raise SnapshotError("unsupported snapshot format")
        expected = metadata["files"]
        if not isinstance(expected, dict):
            raise SnapshotError("snapshot file index must be an object")
        collection = snapshot / "collection"
        actual_files = {
            path.relative_to(collection).as_posix()
            for path in collection.rglob("*")
            if path.is_file()
        }
        if actual_files != set(expected):
            raise SnapshotError("snapshot file set does not match its index")
        for relative, checksum in expected.items():
            if _sha256(collection / relative) != checksum:
                raise SnapshotError(f"snapshot checksum mismatch: {relative}")

        collection_metadata = read_collection_metadata(collection / "collection.json")
        manifest = ManifestStore(collection).load_current()
        if manifest.schema_fingerprint != config_fingerprint(
            collection_metadata.config
        ):
            raise SnapshotError("snapshot schema fingerprint mismatch")
        for segment_id in manifest.segment_ids:
            image = SegmentCodec.read(collection / "segments" / segment_id)
            if image.config != collection_metadata.config:
                raise SnapshotError(f"snapshot segment schema mismatch: {segment_id}")
        return collection
    except SnapshotError:
        raise
    except BaseException as error:
        raise SnapshotError(f"invalid collection snapshot: {snapshot}") from error


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        elif path.is_dir():
            fsync_directory(path)
    fsync_directory(root)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
