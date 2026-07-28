from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
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


def config_to_dict(config: CollectionConfig) -> dict[str, object]:
    return {
        "dimension": config.dimension,
        "distance": config.distance.value,
        "hnsw": asdict(config.hnsw),
        "optimizer": asdict(config.optimizer),
        "quantization": (
            None if config.quantization is None else asdict(config.quantization)
        ),
    }


def config_from_dict(value: object) -> CollectionConfig:
    if not isinstance(value, dict):
        raise ValueError("collection config must be an object")
    quantization = value["quantization"]
    return CollectionConfig(
        dimension=int(value["dimension"]),
        distance=Distance(value["distance"]),
        hnsw=HnswConfig(**value["hnsw"]),
        optimizer=OptimizerConfig(**value["optimizer"]),
        quantization=(
            None
            if quantization is None
            else ScalarQuantizationConfig(**quantization)
        ),
    )


def config_fingerprint(config: CollectionConfig) -> str:
    encoded = json.dumps(
        config_to_dict(config),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
