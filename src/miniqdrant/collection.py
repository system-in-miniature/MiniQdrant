from __future__ import annotations

import math
import shutil
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from threading import RLock, Thread
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
from miniqdrant.optimizer.failures import OptimizationGate
from miniqdrant.optimizer.optimizer import build_replacement
from miniqdrant.persistence.manifest import Manifest, ManifestStore
from miniqdrant.persistence.metadata import (
    CollectionMetadata,
    read_collection_metadata,
    write_collection_metadata,
)
from miniqdrant.persistence.snapshot import create_collection_snapshot
from miniqdrant.persistence.wal import (
    DeleteOperation,
    Durability,
    UpsertOperation,
    Wal,
    WalRecord,
)
from miniqdrant.segment import ImmutableSegment, MutableSegment, SegmentSearchRequest
from miniqdrant.segment.codec import SegmentCodec, SegmentImage
from miniqdrant.segment.references import SegmentHandle
from miniqdrant.topk import TopK


@dataclass(frozen=True, slots=True)
class SegmentStatistics:
    segment_count: int
    live_points: int
    deleted_points: int


class CollectionView:
    """A stable search view whose segment files outlive the request."""

    def __init__(
        self,
        config: CollectionConfig,
        handles: tuple[SegmentHandle, ...],
        mutable: ImmutableSegment | None,
        latest: dict[PointId, StoredPoint],
    ) -> None:
        self._config = config
        self._handles = handles
        self._mutable = mutable
        self._latest = latest
        self._closed = False

    @property
    def segment_paths(self) -> tuple[Path, ...]:
        return tuple(handle.path for handle in self._handles)

    def search(self, request: SearchRequest) -> SearchResult:
        if self._closed:
            raise RuntimeError("collection view is closed")
        return _search(
            self._config,
            tuple(handle.segment for handle in self._handles)
            + (() if self._mutable is None else (self._mutable,)),
            self._latest,
            request,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for handle in self._handles:
            handle.release()

    def __enter__(self) -> CollectionView:
        return self

    def __exit__(self, *_error: object) -> None:
        self.close()


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
        segments: list[SegmentHandle],
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
        self._optimizer_lock = RLock()
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
        segments: list[SegmentHandle] = []
        for segment_id in manifest.segment_ids:
            segment_path = path / "segments" / segment_id
            image = SegmentCodec.read(segment_path)
            if image.config != metadata.config:
                raise CorruptionError(f"segment schema mismatch: {segment_id}")
            segments.append(
                SegmentHandle(segment_id, segment_path, image.to_segment())
            )
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

    @property
    def segment_paths(self) -> tuple[Path, ...]:
        with self._update_lock:
            return tuple(handle.path for handle in self._segments)

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
            for handle in self._segments:
                handle.segment.create_payload_index(path, normalized)

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
            segment_path = SegmentCodec.write_atomic(self._path / "segments", image)
            manifest = Manifest(
                generation=self._manifest.generation + 1,
                schema_fingerprint=self._manifest.schema_fingerprint,
                segment_ids=(*self._manifest.segment_ids, segment_id),
                replay_boundary=self._wal.last_sequence,
            )
            self._manifest_store.publish(manifest)
            self._segments.append(
                SegmentHandle(segment_id, segment_path, image.to_segment())
            )
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
        with self.capture_view() as view:
            return view.search(request)

    def capture_view(self) -> CollectionView:
        self._ensure_open()
        with self._update_lock:
            handles = tuple(handle.acquire() for handle in self._segments)
            mutable_records = self._mutable.iter_records()
            mutable = (
                ImmutableSegment.build(
                    self._config,
                    mutable_records,
                    payload_schemas=self._payload_schemas,
                )
                if mutable_records
                else None
            )
            latest = _latest_records(
                tuple(handle.segment for handle in handles),
                mutable_records,
            )
            return CollectionView(self._config, handles, mutable, latest)

    def segment_statistics(self) -> SegmentStatistics:
        self._ensure_open()
        with self._update_lock:
            records = tuple(
                record
                for handle in self._segments
                for record in handle.segment.iter_records()
            )
            return SegmentStatistics(
                segment_count=len(self._segments),
                live_points=sum(not record.deleted for record in records),
                deleted_points=sum(record.deleted for record in records),
            )

    def optimize(self, *, gate: OptimizationGate | None = None) -> None:
        self._ensure_open()
        with self._optimizer_lock:
            self._optimize(gate)

    def start_optimize(
        self,
        *,
        gate: OptimizationGate | None = None,
    ) -> Future[None]:
        self._ensure_open()
        result: Future[None] = Future()

        def run() -> None:
            if not result.set_running_or_notify_cancel():
                return
            try:
                self.optimize(gate=gate)
            except BaseException as error:
                result.set_exception(error)
            else:
                result.set_result(None)

        Thread(target=run, name=f"optimize-{self._name}", daemon=True).start()
        return result

    def merge(self) -> None:
        self.optimize()

    def vacuum(self) -> None:
        self.optimize()

    def create_snapshot(
        self,
        destination: str | Path,
        *,
        failure_injector: Callable[[str], None] | None = None,
    ) -> Path:
        self._ensure_open()
        with self._optimizer_lock, self._update_lock:
            self.flush()
            self._wal.flush()
            return create_collection_snapshot(
                self._path,
                Path(destination),
                self._manifest,
                failure_injector=failure_injector,
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
        return _latest_records(
            tuple(handle.segment for handle in self._segments),
            self._mutable.iter_records(),
        )

    def _optimize(self, gate: OptimizationGate | None) -> None:
        with self._update_lock:
            sources = tuple(handle.acquire() for handle in self._segments)
            captured_records = tuple(
                record
                for handle in sources
                for record in handle.segment.iter_records()
            ) + self._mutable.iter_records()
            replay_boundary = self._wal.last_sequence

        segment_id = f"seg-{uuid4().hex}"
        segment_path = self._path / "segments" / segment_id
        manifest: Manifest | None = None
        published = False
        try:
            if gate is not None:
                gate.arrive("sources_captured")
                gate.wait_for_release("finish_build")
            image = build_replacement(
                segment_id=segment_id,
                config=self._config,
                records=captured_records,
                payload_schemas=self._payload_schemas,
                drop_tombstones=True,
            )
            SegmentCodec.write_atomic(self._path / "segments", image)
            with self._update_lock:
                source_ids = {handle.segment_id for handle in sources}
                preserved = [
                    handle
                    for handle in self._segments
                    if handle.segment_id not in source_ids
                ]
                manifest = Manifest(
                    generation=self._manifest.generation + 1,
                    schema_fingerprint=self._manifest.schema_fingerprint,
                    segment_ids=(
                        *(handle.segment_id for handle in preserved),
                        segment_id,
                    ),
                    replay_boundary=replay_boundary,
                )
                late_records = tuple(
                    record
                    for record in self._mutable.iter_records()
                    if record.version > replay_boundary
                )
                replacement = SegmentHandle(
                    segment_id,
                    segment_path,
                    image.to_segment(),
                )
                next_mutable = self._mutable_from_records(late_records)
                self._manifest_store.publish(manifest)
                published = True
                self._segments = [
                    *preserved,
                    replacement,
                ]
                self._manifest = manifest
                self._mutable = next_mutable
                for handle in sources:
                    handle.retire()
        except BaseException:
            if manifest is not None and not published:
                (self._path / manifest.filename).unlink(missing_ok=True)
                (self._path / "CURRENT.tmp").unlink(missing_ok=True)
            if segment_path.exists() and not published:
                shutil.rmtree(segment_path)
            raise
        finally:
            for handle in sources:
                handle.release()

    def _mutable_from_records(
        self,
        records: Iterable[StoredPoint],
    ) -> MutableSegment:
        mutable = self._new_mutable()
        for record in records:
            if record.deleted:
                mutable.apply_delete(record.id, record.version)
            else:
                mutable.apply_upsert(
                    Point(record.id, record.vector, record.payload),
                    record.version,
                )
        return mutable

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


def _latest_records(
    segments: Iterable[ImmutableSegment],
    extra_records: Iterable[StoredPoint],
) -> dict[PointId, StoredPoint]:
    latest: dict[PointId, StoredPoint] = {}
    for segment in segments:
        for record in segment.iter_records():
            current = latest.get(record.id)
            if current is None or record.version > current.version:
                latest[record.id] = record
    for record in extra_records:
        current = latest.get(record.id)
        if current is None or record.version > current.version:
            latest[record.id] = record
    return latest


def _search(
    config: CollectionConfig,
    segments: tuple[ImmutableSegment, ...],
    latest: dict[PointId, StoredPoint],
    request: SearchRequest,
) -> SearchResult:
    if request.limit < 1:
        raise ValueError("search limit must be positive")
    if request.filter is not None and not isinstance(request.filter, Filter):
        raise InvalidFilterError("search filter must be a Filter")
    if request.score_threshold is not None and not math.isfinite(request.score_threshold):
        raise ValueError("score threshold must be finite")
    local_limit = request.limit + max(0, len(segments) - 1)
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
        for segment in segments
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
        Collection._project_hit(latest[item.point_id], item.score, request)
        for item in collector.results()
    )
    return SearchResult(
        hits,
        plan=tuple(result.strategy for result in segment_results),
    )
