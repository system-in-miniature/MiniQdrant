from __future__ import annotations

import math

from miniqdrant.config import Distance
from miniqdrant.errors import InvalidVectorError
from miniqdrant.models import Vector


def score(distance: Distance, left: Vector, right: Vector) -> float:
    if len(left) != len(right):
        raise InvalidVectorError("vector dimension mismatch during scoring")
    if distance in (Distance.DOT, Distance.COSINE):
        return math.fsum(a * b for a, b in zip(left, right, strict=True))
    if distance is Distance.EUCLID:
        return -math.fsum((a - b) ** 2 for a, b in zip(left, right, strict=True))
    raise ValueError(f"unsupported distance: {distance}")

