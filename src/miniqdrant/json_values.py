from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType

from miniqdrant.errors import InvalidPointError

type JsonScalar = bool | int | float | str | None
type FrozenJson = JsonScalar | tuple[FrozenJson, ...] | Mapping[str, FrozenJson]
type FrozenJsonObject = Mapping[str, FrozenJson]


def freeze_json_object(value: object) -> FrozenJsonObject:
    if not isinstance(value, Mapping):
        raise InvalidPointError("point payload must be a JSON object")
    frozen = _freeze_json(value)
    assert isinstance(frozen, Mapping)
    return frozen


def _freeze_json(value: object) -> FrozenJson:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidPointError("point payload must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, FrozenJson] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidPointError("point payload JSON object keys must be strings")
            result[key] = _freeze_json(item)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise InvalidPointError("point payload must contain only JSON-compatible values")


def thaw_json(value: FrozenJson) -> object:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value
