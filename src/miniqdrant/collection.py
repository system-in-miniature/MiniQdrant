from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from pathlib import Path
from threading import RLock
from uuid import uuid4

from miniqdrant.config import CollectionConfig, config_fingerprint
from miniqdrant.errors import CorruptionError, InvalidFilterError
from miniqdrant.filters import Filter
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.ids import PointId, canonicalize_point_id
from miniqdrant.lifecycle import Lifecycle
from miniqdrant.models import (
    Point,
    SearchHit,
    SearchRequest,
    SearchResult,
    StoredPoint,
    validate_point,
)
from miniqdrant.persistence.manifest import Manifest, ManifestStore
from miniqdrant.persistence.metadata import (
    CollectionMetadata,
    read_collection_metadata,
    write_collection_metadata,
)
from miniqdrant.persistence.wal import (
    DeleteOperation,
    Durability,
    UpsertOperation,
    Wal,
    WalRecord,
)
from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
from miniqdrant.segment.codec import SegmentCodec, SegmentImage
from miniqdrant.topk import TopK


class Collection(Lifecycle):
    def __init__(
        self,
        name: str,
        path: Path,
        config: CollectionConfig,
        *,
        wal: Wal,
        manifest_store: ManifestStore,
        manifest: Manifest,
        segments: list[ImmutableSegment],
        payload_schemas: dict[str, PayloadSchema],
        failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._name = name
        self._path = path
        self._config = config
        self._wal = wal
        self._manifest_store = manifest_store
        self._manifest = manifest
        self._segments = segments
        self._payload_schemas = payload_schemas
        self._failure_injector = failure_injector or (lambda _stage: None)
        self._update_lock = RLock()
        self._mutable = self._new_mutable()

    @classmethod
    def create(
        cls,
        name: str,
        path: Path,
        config: CollectionConfig,
        *,
        durability: Durability,
        failure_injector: Callable[[str], None] | None = None,
    ) -> Collection:
        path.mkdir(parents=True, exist_ok=False)
        (path / "segments").mkdir()
        metadata = CollectionMetadata(name, config, {})
        write_collection_metadata(path / "collection.json", metadata)
        wal = Wal.create(path / "wal", durability)
        initial_store = ManifestStore(path)
        manifest = Manifest(
            generation=1,
            schema_fingerprint=config_fingerprint(config),
            segment_ids=(),
            replay_boundary=0,
        )
        initial_store.publish(manifest)
        store = ManifestStore(path, failure_injector=failure_injector)
        return cls(
            name,
            path,
            config,
            wal=wal,
            manifest_store=store,
            manifest=manifest,
            segments=[],
            payload_schemas={},
            failure_injector=failure_injector,
        )

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        durability: Durability,
        failure_injector: Callable[[str], None] | None = None,
    ) -> Collection:
        metadata = read_collection_metadata(path / "collection.json")
        store = ManifestStore(path, failure_injector=failure_injector)
        manifest = store.load_current()
        if manifest.schema_fingerprint != config_fingerprint(metadata.config):
            raise CorruptionError("manifest schema fingerprint does not match collection")
        segments: list[ImmutableSegment] = []
        for segment_id in manifest.segment_ids:
            image = SegmentCodec.read(path / "segments" / segment_id)
            if image.config != metadata.config:
                raise CorruptionError(f"segment schema mismatch: {segment_id}")
            segments.append(image.to_segment())
        wal = Wal.open(path / "wal", durability)
        collection = cls(
            metadata.name,
            path,
            metadata.config,
            wal=wal,
            manifest_store=store,
            manifest=manifest,
            segments=segments,
            payload_schemas=metadata.payload_schemas,
            failure_injector=failure_injector,
        )
        for record in wal.replay(after_sequence=manifest.replay_boundary):
            collection._apply_wal_record(record)
        return collection

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> CollectionConfig:
        return self._config

    @property
    def payload_index_schemas(self) -> dict[str, str]:
        return {
            path: schema.value for path, schema in sorted(self._payload_schemas.items())
        }

    def count(self) -> int:
        self._ensure_open()
        with self._update_lock:
            return sum(not point.deleted for point in self._latest_records().values())

    def upsert(self, points: Iterable[Point]) -> int:
        self._ensure_open()
        batch = tuple(points)
        if not batch:
            raise ValueError("upsert batch must not be empty")
        for point in batch:
            validate_point(point, self._config)
        with self._update_lock:
            record = self._wal.append(UpsertOperation(batch))
            self._failure_injector("after_wal_fsync")
            self._apply_wal_record(record)
            return record.sequence

    def delete(self, point_ids: Iterable[object]) -> int:
        self._ensure_open()
        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
        if not identifiers:
            raise ValueError("delete batch must not be empty")
        with self._update_lock:
            record = self._wal.append(DeleteOperation(identifiers))
            self._failure_injector("after_wal_fsync")
            self._apply_wal_record(record)
            return record.sequence

    def create_payload_index(self, path: str, schema: PayloadSchema | str) -> None:
        self._ensure_open()
        normalized = PayloadSchema(schema)
        with self._update_lock:
            schemas = {**self._payload_schemas, path: normalized}
            write_collection_metadata(
                self._path / "collection.json",
                CollectionMetadata(self._name, self._config, schemas),
            )
            self._payload_schemas = schemas
            self._mutable.create_payload_index(path, normalized)
            for segment in self._segments:
                segment.create_payload_index(path, normalized)

    def flush(self, *, indexed: bool = False) -> None:
        self._ensure_open()
        with self._update_lock:
            if self._mutable.total_count == 0:
                return
            segment_id = f"seg-{uuid4().hex}"
            image = SegmentImage.build(
                segment_id=segment_id,
                config=self._config,
                records=self._mutable.iter_records(),
                payload_schemas=self._payload_schemas,
                indexed=indexed,
            )
            SegmentCodec.write_atomic(self._path / "segments", image)
            manifest = Manifest(
                generation=self._manifest.generation + 1,
                schema_fingerprint=self._manifest.schema_fingerprint,
                segment_ids=(*self._manifest.segment_ids, segment_id),
                replay_boundary=self._wal.last_sequence,
            )
            self._manifest_store.publish(manifest)
            self._segments.append(image.to_segment())
            self._manifest = manifest
            self._mutable = self._new_mutable()

    def retrieve(self, point_ids: Iterable[object]) -> tuple[StoredPoint, ...]:
        self._ensure_open()
        identifiers = tuple(canonicalize_point_id(item) for item in point_ids)
        with self._update_lock:
            latest = self._latest_records()
            return tuple(
                point
                for point_id in identifiers
                if (point := latest.get(point_id)) is not None and not point.deleted
            )

    def search(self, request: SearchRequest) -> SearchResult:
        self._ensure_open()
        if request.limit < 1:
            raise ValueError("search limit must be positive")
        if request.filter is not None and not isinstance(request.filter, Filter):
            raise InvalidFilterError("search filter must be a Filter")
        if request.score_threshold is not None and not math.isfinite(request.score_threshold):
            raise ValueError("score threshold must be finite")
        with self._update_lock:
            latest = self._latest_records()
            search_segments = [*self._segments, self._mutable]
            local_limit = request.limit + max(0, len(search_segments) - 1)
            segment_results = tuple(
                segment.search(
                    SegmentSearchRequest(
                        vector=tuple(request.vector),
                        limit=local_limit,
                        filter=request.filter,
                        exact=request.exact,
                        ef_search=request.ef_search,
                    )
                )
                for segment in search_segments
            )
            collector = TopK(request.limit)
            for result in segment_results:
                for candidate in result.candidates:
                    visible = latest.get(candidate.point_id)
                    if (
                        visible is None
                        or visible.deleted
                        or visible.version != candidate.version
                    ):
                        continue
                    if (
                        request.score_threshold is not None
                        and candidate.score < request.score_threshold
                    ):
                        continue
                    collector.offer(candidate.point_id, candidate.score)
            hits = tuple(
                self._project_hit(latest[item.point_id], item.score, request)
                for item in collector.results()
            )
            return SearchResult(
                hits,
                plan=tuple(result.strategy for result in segment_results),
            )

    def close(self) -> None:
        if not self._mark_closed():
            return
        self._wal.flush()
        self._wal.close()

    def simulate_process_loss(self) -> None:
        if not self._mark_closed():
            return
        self._wal.close()

    def _new_mutable(self) -> MutableSegment:
        mutable = MutableSegment(self._config)
        for path, schema in self._payload_schemas.items():
            mutable.create_payload_index(path, schema)
        return mutable

    def _apply_wal_record(self, record: WalRecord) -> None:
        if isinstance(record.operation, UpsertOperation):
            for point in record.operation.points:
                validate_point(point, self._config)
            for point in record.operation.points:
                self._mutable.apply_upsert(point, record.sequence)
        else:
            for point_id in record.operation.point_ids:
                self._mutable.apply_delete(point_id, record.sequence)

    def _latest_records(self) -> dict[PointId, StoredPoint]:
        latest: dict[PointId, StoredPoint] = {}
        for segment in self._segments:
            for record in segment.iter_records():
                current = latest.get(record.id)
                if current is None or record.version > current.version:
                    latest[record.id] = record
        for record in self._mutable.iter_records():
            current = latest.get(record.id)
            if current is None or record.version > current.version:
                latest[record.id] = record
        return latest

    @staticmethod
    def _project_hit(
        point: StoredPoint,
        score: float,
        request: SearchRequest,
    ) -> SearchHit:
        return SearchHit(
            id=point.id,
            score=score,
            payload=point.payload if request.with_payload else None,
            vector=point.vector if request.with_vector else None,
        )
