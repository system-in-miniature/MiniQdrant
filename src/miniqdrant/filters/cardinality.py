from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CardinalityEstimate:
    minimum: int
    expected: int
    maximum: int
    exact: bool

    def __post_init__(self) -> None:
        if not 0 <= self.minimum <= self.expected <= self.maximum:
            raise ValueError("cardinality bounds must be ordered and non-negative")
        if self.exact and not self.minimum == self.expected == self.maximum:
            raise ValueError("exact cardinality must have equal bounds")

    @classmethod
    def exact_count(cls, count: int) -> CardinalityEstimate:
        return cls(count, count, count, True)

