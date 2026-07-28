from __future__ import annotations

import pytest

from miniqdrant.errors import InvalidFilterError
from miniqdrant.filters import Filter, HasId, Match, Range, matches_filter


def test_boolean_filter_and_array_any_semantics() -> None:
    payload = {"kind": "book", "price": 12.0, "tags": ["python", "db"]}
    condition = Filter(
        must=(Match("kind", "book"), Range("price", lte=20)),
        should=(Match("tags", "python"), Match("tags", "rust")),
        must_not=(Match("kind", "movie"),),
    )

    assert matches_filter(1, payload, condition)


def test_should_requires_one_match_when_present() -> None:
    payload = {"kind": "book"}

    assert matches_filter(1, payload, Filter(must=(Match("kind", "book"),)))
    assert not matches_filter(
        1,
        payload,
        Filter(
            must=(Match("kind", "book"),),
            should=(Match("language", "python"),),
        ),
    )


def test_nested_dot_path_traverses_arrays_of_objects() -> None:
    payload = {
        "reviews": [
            {"user": "alice", "score": 4},
            {"user": "bob", "score": 5},
        ]
    }

    assert matches_filter(
        1,
        payload,
        Filter(must=(Match("reviews.user", "bob"), Range("reviews.score", gte=5))),
    )


def test_missing_path_does_not_match_range_or_match() -> None:
    assert not matches_filter(1, {}, Filter(must=(Range("price", gte=1),)))
    assert not matches_filter(1, {}, Filter(must=(Match("kind", None),)))


def test_has_id_and_nested_filter() -> None:
    condition = Filter(
        must=(
            HasId((1, 2)),
            Filter(must=(Match("visible", True),)),
        )
    )

    assert matches_filter(2, {"visible": True}, condition)
    assert not matches_filter(3, {"visible": True}, condition)


def test_must_not_excludes_match() -> None:
    condition = Filter(must_not=(Match("status", "deleted"),))

    assert matches_filter(1, {"status": "active"}, condition)
    assert not matches_filter(1, {"status": "deleted"}, condition)


@pytest.mark.parametrize(
    "condition",
    [
        lambda: Match("", "book"),
        lambda: Match("bad..path", "book"),
        lambda: Range("price"),
        lambda: Range("price", gt=float("nan")),
        lambda: Range("price", gt=2, lte=1),
        lambda: HasId(()),
    ],
)
def test_invalid_conditions_fail_at_construction(condition) -> None:
    with pytest.raises(InvalidFilterError):
        condition()

