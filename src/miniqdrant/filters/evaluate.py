from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Real

from miniqdrant.filters.ast import Condition, Filter, HasId, Match, Range
from miniqdrant.ids import PointId


def matches_filter(
    point_id: PointId,
    payload: Mapping[str, object],
    filter_: Filter | None,
) -> bool:
    if filter_ is None:
        return True
    return (
        all(_matches_condition(point_id, payload, item) for item in filter_.must)
        and not any(_matches_condition(point_id, payload, item) for item in filter_.must_not)
        and (
            not filter_.should
            or any(_matches_condition(point_id, payload, item) for item in filter_.should)
        )
    )


def resolve_path(payload: Mapping[str, object], path: str) -> tuple[object, ...]:
    return tuple(_walk_path(payload, path.split(".")))


def _walk_path(value: object, parts: list[str]) -> list[object]:
    if not parts:
        if _is_array(value):
            result: list[object] = []
            for item in value:
                result.extend(_walk_path(item, []))
            return result
        return [value]
    if isinstance(value, Mapping):
        head, *tail = parts
        if head not in value:
            return []
        return _walk_path(value[head], tail)
    if _is_array(value):
        result = []
        for item in value:
            result.extend(_walk_path(item, parts))
        return result
    return []


def _is_array(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _matches_condition(
    point_id: PointId,
    payload: Mapping[str, object],
    condition: Condition,
) -> bool:
    if isinstance(condition, Filter):
        return matches_filter(point_id, payload, condition)
    if isinstance(condition, HasId):
        return point_id in condition.ids
    values = resolve_path(payload, condition.path)
    if isinstance(condition, Match):
        return any(value == condition.value for value in values)
    return any(_matches_range(value, condition) for value in values)


def _matches_range(value: object, condition: Range) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    if condition.gt is not None and not value > condition.gt:
        return False
    if condition.gte is not None and not value >= condition.gte:
        return False
    if condition.lt is not None and not value < condition.lt:
        return False
    return condition.lte is None or value <= condition.lte

