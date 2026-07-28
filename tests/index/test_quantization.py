from __future__ import annotations

import pytest

from miniqdrant.index.quantization import ScalarQuantizer


def test_int8_round_trip_has_bounded_error() -> None:
    vectors = (
        (-4.0, 2.0, 9.0),
        (0.0, 2.0, 3.0),
        (7.0, 2.0, -1.0),
    )
    quantizer = ScalarQuantizer.fit(vectors)

    for vector in vectors:
        restored = quantizer.decode(quantizer.encode(vector))
        error = max(abs(left - right) for left, right in zip(vector, restored, strict=True))
        assert error <= quantizer.max_error_bound + 1e-12


def test_constant_dimension_uses_zero_code_and_round_trips() -> None:
    quantizer = ScalarQuantizer.fit(((1.0, 5.0), (3.0, 5.0)))

    assert quantizer.scales[1] == 0.0
    assert quantizer.encode((2.0, 5.0))[1] == 0
    assert quantizer.decode((0, 0))[1] == pytest.approx(5.0)


@pytest.mark.parametrize("value", [(), ((1.0,), (1.0, 2.0))])
def test_fit_rejects_empty_or_ragged_vectors(value) -> None:
    with pytest.raises(ValueError):
        ScalarQuantizer.fit(value)
