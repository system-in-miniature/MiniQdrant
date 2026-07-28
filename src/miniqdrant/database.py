from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from uuid import uuid4

from miniqdrant.collection import Collection
from miniqdrant.config import (
    CollectionConfig,
    Distance,
    HnswConfig,
    OptimizerConfig,
    ScalarQuantizationConfig,
)
from miniqdrant.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
)
from miniqdrant.lifecycle import Lifecycle
from miniqdrant.persistence.fsync import fsync_directory
from miniqdrant.persistence.metadata import (
    CollectionMetadata,
    read_collection_metadata,
    write_collection_metadata,
)
from miniqdrant.persistence.snapshot import validate_collection_snapshot
from miniqdrant.persistence.wal import Durability

_COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class Database(Lifecycle):
    def __init__(
        self,
        path: Path,
        *,
        durability: Durability,
        failure_injector: Callable[[str], None] | None,
    ) -> None:
        super().__init__()
        self._path = path
        self._durability = Durability(durability)
        self._failure_injector = failure_injector
        self._collections_path = path / "collections"
        self._collections_path.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._collections: dict[str, Collection] = {}
        for collection_path in sorted(self._collections_path.iterdir()):
            if collection_path.is_dir() and (collection_path / "collection.json").is_file():
                collection = Collection.open(
                    collection_path,
                    durability=self._durability,
                    failure_injector=failure_injector,
                )
                self._collections[collection.name] = collection

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        durability: Durability = Durability.ALWAYS,
        failure_injector: Callable[[str], None] | None = None,
    ) -> Database:
        return cls(
            Path(path),
            durability=durability,
            failure_injector=failure_injector,
        )

    @property
    def path(self) -> Path:
        return self._path

    def create_collection(
        self,
        name: str,
        *,
        dimension: int,
        distance: Distance | str,
        hnsw: HnswConfig | None = None,
        optimizer: OptimizerConfig | None = None,
        quantization: ScalarQuantizationConfig | None = None,
    ) -> Collection:
        self._ensure_open()
        _validate_collection_name(name)
        config = CollectionConfig(
            dimension=dimension,
            distance=Distance(distance),
            hnsw=hnsw or HnswConfig(),
            optimizer=optimizer or OptimizerConfig(),
            quantization=quantization,
        )
        with self._lock:
            if name in self._collections:
                raise CollectionExistsError(f"collection already exists: {name}")
            path = self._collections_path / name
            if path.exists():
                raise CollectionExistsError(f"collection directory already exists: {name}")
            collection = Collection.create(
                name,
                path,
                config,
                durability=self._durability,
                failure_injector=self._failure_injector,
            )
            self._collections[name] = collection
            return collection

    @classmethod
    def restore_collection(
        cls,
        snapshot: str | Path,
        database_path: str | Path,
        name: str,
        *,
        replace: bool = False,
        durability: Durability = Durability.ALWAYS,
        failure_injector: Callable[[str], None] | None = None,
    ) -> Path:
        _validate_collection_name(name)
        failure = failure_injector or (lambda _stage: None)
        source = validate_collection_snapshot(Path(snapshot))
        root = Path(database_path)
        collections = root / "collections"
        collections.mkdir(parents=True, exist_ok=True)
        target = collections / name
        if target.exists() and not replace:
            raise CollectionExistsError(f"collection already exists: {name}")

        stage = Path(tempfile.mkdtemp(prefix=f".{name}-restore-", dir=collections))
        backup: Path | None = None
        try:
            shutil.copytree(source, stage, dirs_exist_ok=True)
            metadata = read_collection_metadata(stage / "collection.json")
            write_collection_metadata(
                stage / "collection.json",
                CollectionMetadata(name, metadata.config, metadata.payload_schemas),
            )
            restored = Collection.open(stage, durability=durability)
            restored.close()
            fsync_directory(stage)
            if target.exists():
                backup = collections / f".{name}-backup-{uuid4().hex}"
                os.replace(target, backup)
            try:
                failure("before_restore_publish")
                os.replace(stage, target)
                fsync_directory(collections)
            except BaseException:
                if backup is not None and backup.exists() and not target.exists():
                    os.replace(backup, target)
                raise
            if backup is not None:
                shutil.rmtree(backup)
            return target
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def collection(self, name: str) -> Collection:
        self._ensure_open()
        with self._lock:
            try:
                return self._collections[name]
            except KeyError as error:
                raise CollectionNotFoundError(f"collection not found: {name}") from error

    def drop_collection(self, name: str) -> None:
        self._ensure_open()
        with self._lock:
            try:
                collection = self._collections.pop(name)
            except KeyError as error:
                raise CollectionNotFoundError(f"collection not found: {name}") from error
            collection.close()
            shutil.rmtree(collection.path)

    def close(self) -> None:
        if not self._mark_closed():
            return
        with self._lock:
            collections = tuple(self._collections.values())
            self._collections.clear()
        for collection in collections:
            collection.close()

    def simulate_process_loss(self) -> None:
        if not self._mark_closed():
            return
        with self._lock:
            collections = tuple(self._collections.values())
            self._collections.clear()
        for collection in collections:
            collection.simulate_process_loss()


def _validate_collection_name(name: str) -> None:
    if not _COLLECTION_NAME.fullmatch(name):
        raise ValueError("collection name must contain only letters, digits, '_' or '-'")
