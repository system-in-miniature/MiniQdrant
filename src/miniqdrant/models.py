from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from uuid import UUID

from miniqdrant.config import CollectionConfig
from miniqdrant.errors import InvalidVectorError
from miniqdrant.ids import PointId, canonicalize_point_id
from miniqdrant.json_values import FrozenJsonObject, freeze_json_object

type Vector = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Point:
    id: int | UUID | str
    vector: Sequence[float]
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class StoredPoint:
    id: PointId
    vector: Vector
    payload: FrozenJsonObject
    version: int
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class SearchRequest:
    vector: Sequence[float]
    limit: int
    filter: object | None = None
    score_threshold: float | None = None
    exact: bool = False
    ef_search: int | None = None
    with_payload: bool = True
    with_vector: bool = False


@dataclass(frozen=True, slots=True)
class SearchHit:
    id: PointId
    score: float
    payload: FrozenJsonObject | None = None
    vector: Vector | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: tuple[SearchHit, ...]
    plan: object | None = None


def validate_vector(value: Sequence[float], dimension: int) -> Vector:
    if isinstance(value, (str, bytes)) or len(value) != dimension:
        raise InvalidVectorError(
            f"vector dimension must be {dimension}, received {len(value)}"
        )
    result: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, Real):
            raise InvalidVectorError("vector components must be finite real numbers")
        number = float(component)
        if not math.isfinite(number):
            raise InvalidVectorError("vector components must be finite real numbers")
        result.append(number)
    return tuple(result)


def normalize_cosine(vector: Vector) -> Vector:
    norm = math.sqrt(math.fsum(component * component for component in vector))
    if norm == 0.0:
        raise InvalidVectorError("zero vector is invalid for cosine distance")
    return tuple(component / norm for component in vector)


def validate_point(point: Point, config: CollectionConfig) -> StoredPoint:
    point_id = canonicalize_point_id(point.id)
    vector = validate_vector(point.vector, config.dimension)
    if config.distance.value == "cosine":
        vector = normalize_cosine(vector)
    payload = freeze_json_object(point.payload)
    return StoredPoint(
        id=point_id,
        vector=vector,
        payload=payload,
        version=0,
        deleted=False,
    )
