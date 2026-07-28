from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from miniqdrant.config import Distance
from miniqdrant.ids import PointId
from miniqdrant.metrics import score
from miniqdrant.models import StoredPoint, Vector
from miniqdrant.segment.base import ScoredCandidate
from miniqdrant.topk import TopK

_MIN_CODE = -128
_MAX_CODE = 127
_LEVELS = _MAX_CODE - _MIN_CODE

type QuantizedVector = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ScalarQuantizer:
    minima: Vector
    scales: Vector

    @classmethod
    def fit(cls, vectors: Iterable[Sequence[float]]) -> ScalarQuantizer:
        materialized = tuple(tuple(float(value) for value in vector) for vector in vectors)
        if not materialized:
            raise ValueError("quantizer requires at least one vector")
        dimension = len(materialized[0])
        if dimension == 0 or any(len(vector) != dimension for vector in materialized):
            raise ValueError("quantizer vectors must have one non-zero dimension")
        if any(not math.isfinite(value) for vector in materialized for value in vector):
            raise ValueError("quantizer vectors must be finite")
        minima = tuple(min(vector[index] for vector in materialized) for index in range(dimension))
        maxima = tuple(max(vector[index] for vector in materialized) for index in range(dimension))
        scales = tuple(
            0.0 if maximum == minimum else (maximum - minimum) / _LEVELS
            for minimum, maximum in zip(minima, maxima, strict=True)
        )
        return cls(minima, scales)

    @property
    def dimension(self) -> int:
        return len(self.minima)

    @property
    def max_error_bound(self) -> float:
        return max(self.scales, default=0.0) / 2.0

    def encode(self, vector: Sequence[float]) -> QuantizedVector:
        self._validate_dimension(vector)
        codes: list[int] = []
        for value, minimum, scale in zip(
            vector,
            self.minima,
            self.scales,
            strict=True,
        ):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("quantizer vector components must be finite")
            if scale == 0.0:
                codes.append(0)
                continue
            code = round((number - minimum) / scale) + _MIN_CODE
            codes.append(min(_MAX_CODE, max(_MIN_CODE, code)))
        return tuple(codes)

    def decode(self, vector: Sequence[int]) -> Vector:
        self._validate_dimension(vector)
        return tuple(
            minimum if scale == 0.0 else minimum + (int(code) - _MIN_CODE) * scale
            for code, minimum, scale in zip(
                vector,
                self.minima,
                self.scales,
                strict=True,
            )
        )

    def _validate_dimension(self, vector: Sequence[object]) -> None:
        if len(vector) != self.dimension:
            raise ValueError(
                f"quantized vector dimension must be {self.dimension}, "
                f"received {len(vector)}"
            )


class ScalarQuantizedIndex:
    """Approximate candidate scoring followed by exact float rescoring."""

    def __init__(
        self,
        distance: Distance,
        points: Iterable[StoredPoint],
    ) -> None:
        self._distance = distance
        self._points = {point.id: point for point in points}
        if not self._points:
            raise ValueError("quantized index requires at least one point")
        self._quantizer = ScalarQuantizer.fit(
            point.vector for point in self._points.values()
        )
        self._codes = {
            point_id: self._quantizer.encode(point.vector)
            for point_id, point in self._points.items()
        }

    @property
    def quantizer(self) -> ScalarQuantizer:
        return self._quantizer

    def search(
        self,
        query: Vector,
        *,
        limit: int,
        oversampling: int,
        allowed_ids: frozenset[PointId] | None = None,
        predicate: Callable[[StoredPoint], bool] | None = None,
    ) -> tuple[tuple[ScoredCandidate, ...], int]:
        if limit < 1:
            raise ValueError("search limit must be positive")
        if oversampling < 1:
            raise ValueError("quantization oversampling must be positive")
        approximate_query = self._quantizer.decode(self._quantizer.encode(query))
        capacity = min(len(self._points), limit * oversampling)
        approximate = TopK(max(1, capacity))
        visited = 0
        for point_id, codes in self._codes.items():
            if allowed_ids is not None and point_id not in allowed_ids:
                continue
            point = self._points[point_id]
            if predicate is not None and not predicate(point):
                continue
            visited += 1
            approximate.offer(
                point_id,
                score(
                    self._distance,
                    approximate_query,
                    self._quantizer.decode(codes),
                ),
            )

        rescored = TopK(limit)
        for candidate in approximate.results():
            point = self._points[candidate.point_id]
            rescored.offer(point.id, score(self._distance, query, point.vector))
        return (
            tuple(
                ScoredCandidate(
                    candidate.point_id,
                    candidate.score,
                    self._points[candidate.point_id].version,
                )
                for candidate in rescored.results()
            ),
            visited,
        )
