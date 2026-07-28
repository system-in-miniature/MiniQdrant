from __future__ import annotations

import math
from uuid import UUID

import pytest

from miniqdrant.config import CollectionConfig, Distance
from miniqdrant.errors import InvalidPointError, InvalidVectorError
from miniqdrant.models import Point, validate_point


def test_cosine_point_is_normalized_once() -> None:
    config = CollectionConfig(dimension=2, distance=Distance.COSINE)

    stored = validate_point(Point(1, (3.0, 4.0), {"kind": "book"}), config)
    validated_again = validate_point(
        Point(stored.id, stored.vector, dict(stored.payload)),
        config,
    )

    assert stored.vector == pytest.approx((0.6, 0.8))
    assert validated_again.vector == pytest.approx(stored.vector)


@pytest.mark.parametrize(
    "vector",
    [
        (math.nan,),
        (math.inf,),
        (-math.inf,),
    ],
)
def test_non_finite_vector_is_rejected(vector: tuple[float]) -> None:
    config = CollectionConfig(dimension=1, distance=Distance.DOT)

    with pytest.raises(InvalidVectorError, match="finite"):
        validate_point(Point(1, vector, {}), config)


def test_wrong_dimension_and_zero_cosine_vector_are_rejected() -> None:
    config = CollectionConfig(dimension=2, distance=Distance.COSINE)

    with pytest.raises(InvalidVectorError, match="dimension"):
        validate_point(Point(1, (1.0,), {}), config)
    with pytest.raises(InvalidVectorError, match="zero"):
        validate_point(Point(1, (0.0, 0.0), {}), config)


def test_non_json_payload_is_rejected_without_mutating_input() -> None:
    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    payload = {"nested": [{"value": 1}], "bad": object()}

    with pytest.raises(InvalidPointError, match="JSON"):
        validate_point(Point(1, (1.0,), payload), config)

    assert payload["nested"] == [{"value": 1}]


def test_point_ids_are_canonicalized() -> None:
    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    uuid = UUID("936da01f-9abd-4d9d-80c7-02af85c822a8")

    integer = validate_point(Point(42, (1.0,), {}), config)
    identifier = validate_point(Point(str(uuid), (1.0,), {}), config)

    assert integer.id == 42
    assert identifier.id == uuid


@pytest.mark.parametrize("point_id", [-1, 2**64, "", "not-a-uuid", True])
def test_invalid_point_ids_are_rejected(point_id: object) -> None:
    config = CollectionConfig(dimension=1, distance=Distance.DOT)

    with pytest.raises(InvalidPointError, match="point id"):
        validate_point(Point(point_id, (1.0,), {}), config)


def test_config_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="dimension"):
        CollectionConfig(dimension=0, distance=Distance.DOT)

