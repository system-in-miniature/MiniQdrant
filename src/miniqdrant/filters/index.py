from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real

from miniqdrant.filters.ast import Condition, Filter, HasId, Match, Range
from miniqdrant.filters.cardinality import CardinalityEstimate
from miniqdrant.filters.evaluate import resolve_path
from miniqdrant.ids import PointId
from miniqdrant.models import StoredPoint


class PayloadSchema(StrEnum):
    KEYWORD = "keyword"
    INTEGER = "integer"
    FLOAT = "float"
    BOOL = "bool"


@dataclass(frozen=True, slots=True)
class CandidateSet:
    ids: frozenset[PointId]
    estimate: CardinalityEstimate
    exact: bool
    residual: Filter | None


@dataclass(frozen=True, slots=True)
class _Resolved:
    ids: frozenset[PointId]
    exact: bool


class PayloadFieldIndex:
    def __init__(self, path: str, schema: PayloadSchema) -> None:
        self.path = path
        self.schema = PayloadSchema(schema)
        self._values_by_id: dict[PointId, tuple[object, ...]] = {}
        self._equals: dict[object, set[PointId]] = defaultdict(set)

    def upsert(self, point: StoredPoint) -> None:
        self.delete(point.id)
        values = tuple(
            value
            for value in resolve_path(point.payload, self.path)
            if self._accepts(value)
        )
        self._values_by_id[point.id] = values
        for value in values:
            self._equals[value].add(point.id)

    def delete(self, point_id: PointId) -> None:
        for value in self._values_by_id.pop(point_id, ()):
            identifiers = self._equals[value]
            identifiers.discard(point_id)
            if not identifiers:
                del self._equals[value]

    def match(self, value: object) -> frozenset[PointId] | None:
        if not self._accepts(value):
            return frozenset()
        return frozenset(self._equals.get(value, ()))

    def range(self, condition: Range) -> frozenset[PointId] | None:
        if self.schema not in (PayloadSchema.INTEGER, PayloadSchema.FLOAT):
            return None
        return frozenset(
            point_id
            for point_id, values in self._values_by_id.items()
            if any(_in_range(value, condition) for value in values)
        )

    def _accepts(self, value: object) -> bool:
        if self.schema is PayloadSchema.KEYWORD:
            return isinstance(value, str)
        if self.schema is PayloadSchema.BOOL:
            return isinstance(value, bool)
        if self.schema is PayloadSchema.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        return (
            isinstance(value, Real)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )


class PayloadIndexSet:
    def __init__(self, live_ids: Iterable[PointId] = ()) -> None:
        self._live_ids = set(live_ids)
        self._indexes: dict[str, PayloadFieldIndex] = {}

    @property
    def schemas(self) -> dict[str, PayloadSchema]:
        return {path: index.schema for path, index in self._indexes.items()}

    def create(
        self,
        path: str,
        schema: PayloadSchema,
        points: Iterable[StoredPoint],
    ) -> None:
        index = PayloadFieldIndex(path, schema)
        for point in points:
            if not point.deleted:
                index.upsert(point)
                self._live_ids.add(point.id)
        self._indexes[path] = index

    def upsert(self, point: StoredPoint) -> None:
        self._live_ids.add(point.id)
        for index in self._indexes.values():
            index.upsert(point)

    def delete(self, point_id: PointId) -> None:
        self._live_ids.discard(point_id)
        for index in self._indexes.values():
            index.delete(point_id)

    def candidates(self, filter_: Filter | None) -> CandidateSet:
        universe = frozenset(self._live_ids)
        if filter_ is None:
            estimate = CardinalityEstimate.exact_count(len(universe))
            return CandidateSet(universe, estimate, True, None)
        resolved = self._resolve(filter_, universe)
        if resolved.exact:
            estimate = CardinalityEstimate.exact_count(len(resolved.ids))
            return CandidateSet(resolved.ids, estimate, True, None)
        estimate = CardinalityEstimate(0, len(resolved.ids) // 2, len(resolved.ids), False)
        return CandidateSet(resolved.ids, estimate, False, filter_)

    def _resolve(self, condition: Condition, universe: frozenset[PointId]) -> _Resolved:
        if isinstance(condition, HasId):
            return _Resolved(universe.intersection(condition.ids), True)
        if isinstance(condition, Match):
            index = self._indexes.get(condition.path)
            if index is None:
                return _Resolved(universe, False)
            identifiers = index.match(condition.value)
            assert identifiers is not None
            return _Resolved(universe.intersection(identifiers), True)
        if isinstance(condition, Range):
            index = self._indexes.get(condition.path)
            if index is None:
                return _Resolved(universe, False)
            identifiers = index.range(condition)
            if identifiers is None:
                return _Resolved(universe, False)
            return _Resolved(universe.intersection(identifiers), True)
        return self._resolve_filter(condition, universe)

    def _resolve_filter(self, filter_: Filter, universe: frozenset[PointId]) -> _Resolved:
        current = universe
        exact = True
        for condition in filter_.must:
            resolved = self._resolve(condition, universe)
            current = current.intersection(resolved.ids)
            exact = exact and resolved.exact
        if filter_.should:
            resolved_should = tuple(
                self._resolve(condition, universe) for condition in filter_.should
            )
            if all(item.exact for item in resolved_should):
                allowed = frozenset().union(*(item.ids for item in resolved_should))
                current = current.intersection(allowed)
            else:
                exact = False
        for condition in filter_.must_not:
            resolved = self._resolve(condition, universe)
            if resolved.exact:
                current = current.difference(resolved.ids)
            else:
                exact = False
        return _Resolved(frozenset(current), exact)


def _in_range(value: object, condition: Range) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    if condition.gt is not None and value <= condition.gt:
        return False
    if condition.gte is not None and value < condition.gte:
        return False
    if condition.lt is not None and value >= condition.lt:
        return False
    return condition.lte is None or value <= condition.lte
