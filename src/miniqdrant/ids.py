from __future__ import annotations

from uuid import UUID

from miniqdrant.errors import InvalidPointError

PointId = int | UUID
PointIdInput = int | UUID | str


def canonicalize_point_id(value: object) -> PointId:
    if isinstance(value, bool):
        raise InvalidPointError("point id must be an unsigned 64-bit integer or UUID")
    if isinstance(value, int):
        if 0 <= value < 2**64:
            return value
        raise InvalidPointError("point id integer is outside unsigned 64-bit range")
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return UUID(value)
        except ValueError as error:
            raise InvalidPointError("point id string must contain a UUID") from error
    raise InvalidPointError("point id must be an unsigned 64-bit integer or UUID")


def point_id_sort_key(value: PointId) -> tuple[int, int]:
    if isinstance(value, int):
        return (0, value)
    return (1, value.int)


def point_id_bytes(value: PointId) -> bytes:
    if isinstance(value, int):
        return b"\x00" + value.to_bytes(8, "big")
    return b"\x01" + value.bytes
