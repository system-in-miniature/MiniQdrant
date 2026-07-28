from __future__ import annotations

import pytest

from miniqdrant.config import Distance
from miniqdrant.errors import InvalidVectorError
from miniqdrant.metrics import score


def test_dot_score_is_dot_product() -> None:
    assert score(Distance.DOT, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(11.0)


def test_cosine_score_uses_normalized_vectors() -> None:
    assert score(Distance.COSINE, (0.6, 0.8), (0.6, 0.8)) == pytest.approx(1.0)


def test_euclid_score_is_negative_squared_distance() -> None:
    assert score(Distance.EUCLID, (1.0, 2.0), (3.0, 4.0)) == pytest.approx(-8.0)


def test_metric_rejects_dimension_mismatch() -> None:
    with pytest.raises(InvalidVectorError, match="dimension"):
        score(Distance.DOT, (1.0,), (1.0, 2.0))

