from __future__ import annotations

from miniqdrant.labs.filtering import run_filtering_lab
from miniqdrant.labs.recall import run_recall_lab
from miniqdrant.labs.recovery import run_recovery_lab
from miniqdrant.labs.segments import run_segments_lab


def test_labs_are_deterministic_and_report_the_mechanism(tmp_path) -> None:
    first = run_recall_lab(seed=11, points=80, queries=5)
    second = run_recall_lab(seed=11, points=80, queries=5)

    assert first == second
    assert 0.0 <= first["recall_at_5"] <= 1.0
    assert run_filtering_lab(tmp_path / "filter")["matching_ids"] == [1, 3]
    assert run_segments_lab(tmp_path / "segments")["after_segments"] == 1
    assert run_recovery_lab(tmp_path / "recovery")["restored_ids"] == [1, 2]
