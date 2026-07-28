from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Distance(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"


@dataclass(frozen=True, slots=True)
class HnswConfig:
    m: int = 16
    ef_construct: int = 100
    ef_search: int = 64
    seed: int = 0

    def __post_init__(self) -> None:
        if self.m < 2:
            raise ValueError("hnsw m must be at least 2")
        if self.ef_construct < self.m:
            raise ValueError("ef_construct must be at least m")
        if self.ef_search < 1:
            raise ValueError("ef_search must be positive")


@dataclass(frozen=True, slots=True)
class OptimizerConfig:
    flush_threshold_points: int = 1_000
    indexing_threshold_points: int = 2_000
    target_segment_count: int = 4
    deleted_ratio_threshold: float = 0.2

    def __post_init__(self) -> None:
        if self.flush_threshold_points < 1:
            raise ValueError("flush threshold must be positive")
        if self.indexing_threshold_points < 1:
            raise ValueError("indexing threshold must be positive")
        if self.target_segment_count < 1:
            raise ValueError("target segment count must be positive")
        if not 0.0 < self.deleted_ratio_threshold <= 1.0:
            raise ValueError("deleted ratio threshold must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class ScalarQuantizationConfig:
    oversampling: int = 4

    def __post_init__(self) -> None:
        if self.oversampling < 1:
            raise ValueError("quantization oversampling must be positive")


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    dimension: int
    distance: Distance
    hnsw: HnswConfig = field(default_factory=HnswConfig)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    quantization: ScalarQuantizationConfig | None = None

    def __post_init__(self) -> None:
        if self.dimension < 1:
            raise ValueError("collection dimension must be positive")
        if not isinstance(self.distance, Distance):
            object.__setattr__(self, "distance", Distance(self.distance))
