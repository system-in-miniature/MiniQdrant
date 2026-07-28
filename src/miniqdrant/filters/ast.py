from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from miniqdrant.errors import InvalidFilterError
from miniqdrant.ids import PointId, canonicalize_point_id

type MatchScalar = bool | int | float | str | None


def _validate_path(path: str) -> None:
    if not path or any(not part for part in path.split(".")):
        raise InvalidFilterError("filter field path must contain non-empty components")


def _validate_scalar(value: object) -> None:
    if not isinstance(value, (bool, int, float, str)) and value is not None:
        raise InvalidFilterError("match value must be a JSON scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidFilterError("match number must be finite")


@dataclass(frozen=True, slots=True)
class Match:
    path: str
    value: MatchScalar

    def __post_init__(self) -> None:
        _validate_path(self.path)
        _validate_scalar(self.value)


@dataclass(frozen=True, slots=True)
class Range:
    path: str
    gt: float | int | None = None
    gte: float | int | None = None
    lt: float | int | None = None
    lte: float | int | None = None

    def __post_init__(self) -> None:
        _validate_path(self.path)
        bounds = tuple(
            value for value in (self.gt, self.gte, self.lt, self.lte) if value is not None
        )
        if not bounds:
            raise InvalidFilterError("range must contain at least one bound")
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            for value in bounds
        ):
            raise InvalidFilterError("range bounds must be finite numbers")
        lower = self.gt if self.gt is not None else self.gte
        upper = self.lt if self.lt is not None else self.lte
        if lower is not None and upper is not None and lower > upper:
            raise InvalidFilterError("range lower bound cannot exceed upper bound")
        if self.gt is not None and self.gte is not None:
            raise InvalidFilterError("range cannot contain both gt and gte")
        if self.lt is not None and self.lte is not None:
            raise InvalidFilterError("range cannot contain both lt and lte")


@dataclass(frozen=True, slots=True)
class HasId:
    ids: tuple[PointId, ...]

    def __post_init__(self) -> None:
        if not self.ids:
            raise InvalidFilterError("has-id condition must contain at least one point id")
        try:
            canonical = tuple(canonicalize_point_id(value) for value in self.ids)
        except ValueError as error:
            raise InvalidFilterError("has-id condition contains an invalid point id") from error
        object.__setattr__(self, "ids", canonical)


@dataclass(frozen=True, slots=True)
class Filter:
    must: tuple[Match | Range | HasId | Filter, ...] = ()
    should: tuple[Match | Range | HasId | Filter, ...] = ()
    must_not: tuple[Match | Range | HasId | Filter, ...] = ()

    def __post_init__(self) -> None:
        allowed = (Match, Range, HasId, Filter)
        for clause in (self.must, self.should, self.must_not):
            if any(not isinstance(condition, allowed) for condition in clause):
                raise InvalidFilterError("filter contains an unsupported condition")
        object.__setattr__(self, "must", tuple(self.must))
        object.__setattr__(self, "should", tuple(self.should))
        object.__setattr__(self, "must_not", tuple(self.must_not))


type Condition = Match | Range | HasId | Filter

