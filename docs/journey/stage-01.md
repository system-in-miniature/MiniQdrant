# Stage 01 · Domain contracts

### Goal

Build domain contracts and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `pyproject.toml`
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/config.py`
    - `src/miniqdrant/errors.py`
    - `src/miniqdrant/ids.py`
    - `src/miniqdrant/json_values.py`
    - `src/miniqdrant/models.py`
    - `tests/test_project_contract.py`
    - `tests/unit/test_domain.py`
    - `uv.lock`

### The problem at this point

Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them.

### Test contract

#### See the failure first

The focused tests force domain contracts through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/test_project_contract.py"
    ```diff
    diff --git a/tests/test_project_contract.py b/tests/test_project_contract.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c0b0de8ae2feed30e0029339c77349da9dbbf880
    --- /dev/null
    +++ b/tests/test_project_contract.py
    @@ -0,0 +1,20 @@
    +from __future__ import annotations
    +
    +import tomllib
    +from pathlib import Path
    +
    +ROOT = Path(__file__).resolve().parents[1]
    +
    +
    +def test_project_identity_is_frozen() -> None:
    +    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    +
    +    assert metadata["project"]["name"] == "miniqdrant"
    +    assert metadata["project"]["requires-python"] == ">=3.12"
    +    assert metadata["project"]["scripts"] == {"miniqdrant": "miniqdrant.cli:main"}
    +    assert metadata["project"]["dependencies"] == []
    +
    +
    +def test_project_and_course_are_separate() -> None:
    +    assert not (ROOT / "course").exists()
    +    assert not list(ROOT.glob("day[0-9][0-9].md"))
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force domain contracts through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert isinstance(frozen, Mapping)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/test_domain.py"
    ```diff
    diff --git a/tests/unit/test_domain.py b/tests/unit/test_domain.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c3d1ddd096953038e6c0642c5aea8f060ed6252f
    --- /dev/null
    +++ b/tests/unit/test_domain.py
    @@ -0,0 +1,82 @@
    +from __future__ import annotations
    +
    +import math
    +from uuid import UUID
    +
    +import pytest
    +
    +from miniqdrant.config import CollectionConfig, Distance
    +from miniqdrant.errors import InvalidPointError, InvalidVectorError
    +from miniqdrant.models import Point, validate_point
    +
    +
    +def test_cosine_point_is_normalized_once() -> None:
    +    config = CollectionConfig(dimension=2, distance=Distance.COSINE)
    +
    +    stored = validate_point(Point(1, (3.0, 4.0), {"kind": "book"}), config)
    +    validated_again = validate_point(
    +        Point(stored.id, stored.vector, dict(stored.payload)),
    +        config,
    +    )
    +
    +    assert stored.vector == pytest.approx((0.6, 0.8))
    +    assert validated_again.vector == pytest.approx(stored.vector)
    +
    +
    +@pytest.mark.parametrize(
    +    "vector",
    +    [
    +        (math.nan,),
    +        (math.inf,),
    +        (-math.inf,),
    +    ],
    +)
    +def test_non_finite_vector_is_rejected(vector: tuple[float]) -> None:
    +    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    +
    +    with pytest.raises(InvalidVectorError, match="finite"):
    +        validate_point(Point(1, vector, {}), config)
    +
    +
    +def test_wrong_dimension_and_zero_cosine_vector_are_rejected() -> None:
    +    config = CollectionConfig(dimension=2, distance=Distance.COSINE)
    +
    +    with pytest.raises(InvalidVectorError, match="dimension"):
    +        validate_point(Point(1, (1.0,), {}), config)
    +    with pytest.raises(InvalidVectorError, match="zero"):
    +        validate_point(Point(1, (0.0, 0.0), {}), config)
    +
    +
    +def test_non_json_payload_is_rejected_without_mutating_input() -> None:
    +    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    +    payload = {"nested": [{"value": 1}], "bad": object()}
    +
    +    with pytest.raises(InvalidPointError, match="JSON"):
    +        validate_point(Point(1, (1.0,), payload), config)
    +
    +    assert payload["nested"] == [{"value": 1}]
    +
    +
    +def test_point_ids_are_canonicalized() -> None:
    +    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    +    uuid = UUID("936da01f-9abd-4d9d-80c7-02af85c822a8")
    +
    +    integer = validate_point(Point(42, (1.0,), {}), config)
    +    identifier = validate_point(Point(str(uuid), (1.0,), {}), config)
    +
    +    assert integer.id == 42
    +    assert identifier.id == uuid
    +
    +
    +@pytest.mark.parametrize("point_id", [-1, 2**64, "", "not-a-uuid", True])
    +def test_invalid_point_ids_are_rejected(point_id: object) -> None:
    +    config = CollectionConfig(dimension=1, distance=Distance.DOT)
    +
    +    with pytest.raises(InvalidPointError, match="point id"):
    +        validate_point(Point(point_id, (1.0,), {}), config)
    +
    +
    +def test_config_rejects_invalid_parameters() -> None:
    +    with pytest.raises(ValueError, match="dimension"):
    +        CollectionConfig(dimension=0, distance=Distance.DOT)
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force domain contracts through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert isinstance(frozen, Mapping)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is domain contracts. Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them.

### Why this mechanism is necessary

Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

### Mechanism blocks

#### Domain contracts mechanism

accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

??? note "File diff: src/miniqdrant/config.py"
    ```diff
    diff --git a/src/miniqdrant/config.py b/src/miniqdrant/config.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8308e82cfaa10e0ae0aa33e26f15d248bb80887f
    --- /dev/null
    +++ b/src/miniqdrant/config.py
    @@ -0,0 +1,68 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass, field
    +from enum import StrEnum
    +
    +
    +class Distance(StrEnum):
    +    COSINE = "cosine"
    +    DOT = "dot"
    +    EUCLID = "euclid"
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class HnswConfig:
    +    m: int = 16
    +    ef_construct: int = 100
    +    ef_search: int = 64
    +    seed: int = 0
    +
    +    def __post_init__(self) -> None:
    +        if self.m < 2:
    +            raise ValueError("hnsw m must be at least 2")
    +        if self.ef_construct < self.m:
    +            raise ValueError("ef_construct must be at least m")
    +        if self.ef_search < 1:
    +            raise ValueError("ef_search must be positive")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class OptimizerConfig:
    +    flush_threshold_points: int = 1_000
    +    indexing_threshold_points: int = 2_000
    +    target_segment_count: int = 4
    +    deleted_ratio_threshold: float = 0.2
    +
    +    def __post_init__(self) -> None:
    +        if self.flush_threshold_points < 1:
    +            raise ValueError("flush threshold must be positive")
    +        if self.indexing_threshold_points < 1:
    +            raise ValueError("indexing threshold must be positive")
    +        if self.target_segment_count < 1:
    +            raise ValueError("target segment count must be positive")
    +        if not 0.0 < self.deleted_ratio_threshold <= 1.0:
    +            raise ValueError("deleted ratio threshold must be in (0, 1]")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ScalarQuantizationConfig:
    +    oversampling: int = 4
    +
    +    def __post_init__(self) -> None:
    +        if self.oversampling < 1:
    +            raise ValueError("quantization oversampling must be positive")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class CollectionConfig:
    +    dimension: int
    +    distance: Distance
    +    hnsw: HnswConfig = field(default_factory=HnswConfig)
    +    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    +    quantization: ScalarQuantizationConfig | None = None
    +
    +    def __post_init__(self) -> None:
    +        if self.dimension < 1:
    +            raise ValueError("collection dimension must be positive")
    +        if not isinstance(self.distance, Distance):
    +            object.__setattr__(self, "distance", Distance(self.distance))
    ```

??? note "File diff: src/miniqdrant/errors.py"
    ```diff
    diff --git a/src/miniqdrant/errors.py b/src/miniqdrant/errors.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1f70071ca9d97b7bcf1a379fe5e4723c1e79f5f2
    --- /dev/null
    +++ b/src/miniqdrant/errors.py
    @@ -0,0 +1,46 @@
    +from __future__ import annotations
    +
    +
    +class MiniQdrantError(Exception):
    +    """Base class for public MiniQdrant errors."""
    +
    +
    +class CollectionExistsError(MiniQdrantError):
    +    """Raised when creating a collection that already exists."""
    +
    +
    +class CollectionNotFoundError(MiniQdrantError):
    +    """Raised when a collection cannot be found."""
    +
    +
    +class SchemaMismatchError(MiniQdrantError):
    +    """Raised when persisted and requested collection schemas differ."""
    +
    +
    +class InvalidPointError(MiniQdrantError, ValueError):
    +    """Raised when a point identifier or payload is invalid."""
    +
    +
    +class InvalidVectorError(InvalidPointError):
    +    """Raised when a vector violates its collection contract."""
    +
    +
    +class InvalidFilterError(MiniQdrantError, ValueError):
    +    """Raised when a payload filter is malformed."""
    +
    +
    +class PayloadIndexError(MiniQdrantError):
    +    """Raised when a payload index operation is invalid."""
    +
    +
    +class CorruptionError(MiniQdrantError):
    +    """Raised when durable data fails structural or checksum validation."""
    +
    +
    +class ClosedResourceError(MiniQdrantError):
    +    """Raised when work is submitted to a closed resource."""
    +
    +
    +class SnapshotError(MiniQdrantError):
    +    """Raised when snapshot creation or restore cannot complete safely."""
    +
    ```

??? note "File diff: src/miniqdrant/ids.py"
    ```diff
    diff --git a/src/miniqdrant/ids.py b/src/miniqdrant/ids.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4c9824f94581c394a5fb899bba3a718cba8797e9
    --- /dev/null
    +++ b/src/miniqdrant/ids.py
    @@ -0,0 +1,37 @@
    +from __future__ import annotations
    +
    +from uuid import UUID
    +
    +from miniqdrant.errors import InvalidPointError
    +
    +PointId = int | UUID
    +PointIdInput = int | UUID | str
    +
    +
    +def canonicalize_point_id(value: object) -> PointId:
    +    if isinstance(value, bool):
    +        raise InvalidPointError("point id must be an unsigned 64-bit integer or UUID")
    +    if isinstance(value, int):
    +        if 0 <= value < 2**64:
    +            return value
    +        raise InvalidPointError("point id integer is outside unsigned 64-bit range")
    +    if isinstance(value, UUID):
    +        return value
    +    if isinstance(value, str) and value:
    +        try:
    +            return UUID(value)
    +        except ValueError as error:
    +            raise InvalidPointError("point id string must contain a UUID") from error
    +    raise InvalidPointError("point id must be an unsigned 64-bit integer or UUID")
    +
    +
    +def point_id_sort_key(value: PointId) -> tuple[int, int]:
    +    if isinstance(value, int):
    +        return (0, value)
    +    return (1, value.int)
    +
    +
    +def point_id_bytes(value: PointId) -> bytes:
    +    if isinstance(value, int):
    +        return b"\x00" + value.to_bytes(8, "big")
    +    return b"\x01" + value.bytes
    ```

??? note "File diff: src/miniqdrant/json_values.py"
    ```diff
    diff --git a/src/miniqdrant/json_values.py b/src/miniqdrant/json_values.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3b35fe0b530b321274f2ba9943b0afdd3b9845c3
    --- /dev/null
    +++ b/src/miniqdrant/json_values.py
    @@ -0,0 +1,48 @@
    +from __future__ import annotations
    +
    +import math
    +from collections.abc import Mapping
    +from types import MappingProxyType
    +
    +from miniqdrant.errors import InvalidPointError
    +
    +type JsonScalar = bool | int | float | str | None
    +type FrozenJson = JsonScalar | tuple[FrozenJson, ...] | Mapping[str, FrozenJson]
    +type FrozenJsonObject = Mapping[str, FrozenJson]
    +
    +
    +def freeze_json_object(value: object) -> FrozenJsonObject:
    +    if not isinstance(value, Mapping):
    +        raise InvalidPointError("point payload must be a JSON object")
    +    frozen = _freeze_json(value)
    +    assert isinstance(frozen, Mapping)
    +    return frozen
    +
    +
    +def _freeze_json(value: object) -> FrozenJson:
    +    if value is None or isinstance(value, (bool, str)):
    +        return value
    +    if isinstance(value, int):
    +        return value
    +    if isinstance(value, float):
    +        if not math.isfinite(value):
    +            raise InvalidPointError("point payload must contain finite JSON numbers")
    +        return value
    +    if isinstance(value, Mapping):
    +        result: dict[str, FrozenJson] = {}
    +        for key, item in value.items():
    +            if not isinstance(key, str):
    +                raise InvalidPointError("point payload JSON object keys must be strings")
    +            result[key] = _freeze_json(item)
    +        return MappingProxyType(result)
    +    if isinstance(value, (list, tuple)):
    +        return tuple(_freeze_json(item) for item in value)
    +    raise InvalidPointError("point payload must contain only JSON-compatible values")
    +
    +
    +def thaw_json(value: FrozenJson) -> object:
    +    if isinstance(value, Mapping):
    +        return {key: thaw_json(item) for key, item in value.items()}
    +    if isinstance(value, tuple):
    +        return [thaw_json(item) for item in value]
    +    return value
    ```

??? note "File diff: src/miniqdrant/models.py"
    ```diff
    diff --git a/src/miniqdrant/models.py b/src/miniqdrant/models.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..85760a544bea859bd3e27fc182d41ceb0b91d08c
    --- /dev/null
    +++ b/src/miniqdrant/models.py
    @@ -0,0 +1,94 @@
    +from __future__ import annotations
    +
    +import math
    +from collections.abc import Mapping, Sequence
    +from dataclasses import dataclass
    +from numbers import Real
    +from uuid import UUID
    +
    +from miniqdrant.config import CollectionConfig
    +from miniqdrant.errors import InvalidVectorError
    +from miniqdrant.ids import PointId, canonicalize_point_id
    +from miniqdrant.json_values import FrozenJsonObject, freeze_json_object
    +
    +type Vector = tuple[float, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Point:
    +    id: int | UUID | str
    +    vector: Sequence[float]
    +    payload: Mapping[str, object]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class StoredPoint:
    +    id: PointId
    +    vector: Vector
    +    payload: FrozenJsonObject
    +    version: int
    +    deleted: bool = False
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SearchRequest:
    +    vector: Sequence[float]
    +    limit: int
    +    filter: object | None = None
    +    score_threshold: float | None = None
    +    exact: bool = False
    +    ef_search: int | None = None
    +    with_payload: bool = True
    +    with_vector: bool = False
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SearchHit:
    +    id: PointId
    +    score: float
    +    payload: FrozenJsonObject | None = None
    +    vector: Vector | None = None
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class SearchResult:
    +    hits: tuple[SearchHit, ...]
    +    plan: object | None = None
    +
    +
    +def validate_vector(value: Sequence[float], dimension: int) -> Vector:
    +    if isinstance(value, (str, bytes)) or len(value) != dimension:
    +        raise InvalidVectorError(
    +            f"vector dimension must be {dimension}, received {len(value)}"
    +        )
    +    result: list[float] = []
    +    for component in value:
    +        if isinstance(component, bool) or not isinstance(component, Real):
    +            raise InvalidVectorError("vector components must be finite real numbers")
    +        number = float(component)
    +        if not math.isfinite(number):
    +            raise InvalidVectorError("vector components must be finite real numbers")
    +        result.append(number)
    +    return tuple(result)
    +
    +
    +def normalize_cosine(vector: Vector) -> Vector:
    +    norm = math.sqrt(math.fsum(component * component for component in vector))
    +    if norm == 0.0:
    +        raise InvalidVectorError("zero vector is invalid for cosine distance")
    +    return tuple(component / norm for component in vector)
    +
    +
    +def validate_point(point: Point, config: CollectionConfig) -> StoredPoint:
    +    point_id = canonicalize_point_id(point.id)
    +    vector = validate_vector(point.vector, config.dimension)
    +    if config.distance.value == "cosine":
    +        vector = normalize_cosine(vector)
    +    payload = freeze_json_object(point.payload)
    +    return StoredPoint(
    +        id=point_id,
    +        vector=vector,
    +        payload=payload,
    +        version=0,
    +        deleted=False,
    +    )
    ```

**What it is and why it appears**

The central mechanism is domain contracts. Points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them.

**Runtime role**

accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

**Statement understanding**

The durable boundary is this: accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (3 files)"
    **`pyproject.toml`**

    ```diff
    diff --git a/pyproject.toml b/pyproject.toml
    new file mode 100644
    index 0000000000000000000000000000000000000000..972a6ac4333f0d302fedebca9a8b04771816320b
    --- /dev/null
    +++ b/pyproject.toml
    @@ -0,0 +1,35 @@
    +[build-system]
    +requires = ["hatchling"]
    +build-backend = "hatchling.build"
    +
    +[project]
    +name = "miniqdrant"
    +version = "0.1.0"
    +description = "Build the mechanisms behind filtered vector search."
    +readme = "README.md"
    +requires-python = ">=3.12"
    +dependencies = []
    +
    +[project.scripts]
    +miniqdrant = "miniqdrant.cli:main"
    +
    +[dependency-groups]
    +dev = [
    +  "pytest>=8.4.1",
    +  "ruff>=0.12.5",
    +]
    +
    +[tool.hatch.build.targets.wheel]
    +packages = ["src/miniqdrant"]
    +
    +[tool.pytest.ini_options]
    +addopts = "-ra"
    +testpaths = ["tests"]
    +
    +[tool.ruff]
    +target-version = "py312"
    +line-length = 100
    +
    +[tool.ruff.lint]
    +select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
    +
    ```

    **`src/miniqdrant/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/__init__.py b/src/miniqdrant/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..32e926045fbc464d15dedcca79e9ff2d9919691c
    --- /dev/null
    +++ b/src/miniqdrant/__init__.py
    @@ -0,0 +1,46 @@
    +from miniqdrant.config import (
    +    CollectionConfig,
    +    Distance,
    +    HnswConfig,
    +    OptimizerConfig,
    +    ScalarQuantizationConfig,
    +)
    +from miniqdrant.errors import (
    +    ClosedResourceError,
    +    CollectionExistsError,
    +    CollectionNotFoundError,
    +    CorruptionError,
    +    InvalidFilterError,
    +    InvalidPointError,
    +    InvalidVectorError,
    +    MiniQdrantError,
    +    PayloadIndexError,
    +    SchemaMismatchError,
    +    SnapshotError,
    +)
    +from miniqdrant.models import Point, SearchHit, SearchRequest, SearchResult, StoredPoint
    +
    +__all__ = [
    +    "ClosedResourceError",
    +    "CollectionConfig",
    +    "CollectionExistsError",
    +    "CollectionNotFoundError",
    +    "CorruptionError",
    +    "Distance",
    +    "HnswConfig",
    +    "InvalidFilterError",
    +    "InvalidPointError",
    +    "InvalidVectorError",
    +    "MiniQdrantError",
    +    "OptimizerConfig",
    +    "PayloadIndexError",
    +    "Point",
    +    "ScalarQuantizationConfig",
    +    "SchemaMismatchError",
    +    "SearchHit",
    +    "SearchRequest",
    +    "SearchResult",
    +    "SnapshotError",
    +    "StoredPoint",
    +]
    +
    ```

    **`uv.lock`**

    ```diff
    diff --git a/uv.lock b/uv.lock
    new file mode 100644
    index 0000000000000000000000000000000000000000..f0ae1a99de3bbfd7e7f7be5fecbad8f7baa3d982
    --- /dev/null
    +++ b/uv.lock
    @@ -0,0 +1,108 @@
    +version = 1
    +revision = 3
    +requires-python = ">=3.12"
    +
    +[[package]]
    +name = "colorama"
    +version = "0.4.6"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz", hash = "sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44", size = 27697, upload-time = "2022-10-25T02:36:22.414Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/d1/d6/3965ed04c63042e047cb6a3e6ed1a63a35087b6a609aa3a15ed8ac56c221/colorama-0.4.6-py2.py3-none-any.whl", hash = "sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6", size = 25335, upload-time = "2022-10-25T02:36:20.889Z" },
    +]
    +
    +[[package]]
    +name = "iniconfig"
    +version = "2.3.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/72/34/14ca021ce8e5dfedc35312d08ba8bf51fdd999c576889fc2c24cb97f4f10/iniconfig-2.3.0.tar.gz", hash = "sha256:c76315c77db068650d49c5b56314774a7804df16fee4402c1f19d6d15d8c4730", size = 20503, upload-time = "2025-10-18T21:55:43.219Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl", hash = "sha256:f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12", size = 7484, upload-time = "2025-10-18T21:55:41.639Z" },
    +]
    +
    +[[package]]
    +name = "miniqdrant"
    +version = "0.1.0"
    +source = { editable = "." }
    +
    +[package.dev-dependencies]
    +dev = [
    +    { name = "pytest" },
    +    { name = "ruff" },
    +]
    +
    +[package.metadata]
    +
    +[package.metadata.requires-dev]
    +dev = [
    +    { name = "pytest", specifier = ">=8.4.1" },
    +    { name = "ruff", specifier = ">=0.12.5" },
    +]
    +
    +[[package]]
    +name = "packaging"
    +version = "26.2"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/d7/f1/e7a6dd94a8d4a5626c03e4e99c87f241ba9e350cd9e6d75123f992427270/packaging-26.2.tar.gz", hash = "sha256:ff452ff5a3e828ce110190feff1178bb1f2ea2281fa2075aadb987c2fb221661", size = 228134, upload-time = "2026-04-24T20:15:23.917Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/df/b2/87e62e8c3e2f4b32e5fe99e0b86d576da1312593b39f47d8ceef365e95ed/packaging-26.2-py3-none-any.whl", hash = "sha256:5fc45236b9446107ff2415ce77c807cee2862cb6fac22b8a73826d0693b0980e", size = 100195, upload-time = "2026-04-24T20:15:22.081Z" },
    +]
    +
    +[[package]]
    +name = "pluggy"
    +version = "1.6.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz", hash = "sha256:7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3", size = 69412, upload-time = "2025-05-15T12:30:07.975Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl", hash = "sha256:e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746", size = 20538, upload-time = "2025-05-15T12:30:06.134Z" },
    +]
    +
    +[[package]]
    +name = "pygments"
    +version = "2.20.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz", hash = "sha256:6757cd03768053ff99f3039c1a36d6c0aa0b263438fcab17520b30a303a82b5f", size = 4955991, upload-time = "2026-03-29T13:29:33.898Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/f4/7e/a72dd26f3b0f4f2bf1dd8923c85f7ceb43172af56d63c7383eb62b332364/pygments-2.20.0-py3-none-any.whl", hash = "sha256:81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176", size = 1231151, upload-time = "2026-03-29T13:29:30.038Z" },
    +]
    +
    +[[package]]
    +name = "pytest"
    +version = "9.1.1"
    +source = { registry = "https://pypi.org/simple" }
    +dependencies = [
    +    { name = "colorama", marker = "sys_platform == 'win32'" },
    +    { name = "iniconfig" },
    +    { name = "packaging" },
    +    { name = "pluggy" },
    +    { name = "pygments" },
    +]
    +sdist = { url = "https://files.pythonhosted.org/packages/e4/47/b9efed96c114afcfa3c9d3fe98a76a1d14c74a9e266d397cf6eb64be5e01/pytest-9.1.1.tar.gz", hash = "sha256:1088fbde8f2b49d95a549a195707afa7a76a3ce9bcadc26b6d71f0ffda5fe313", size = 1636369, upload-time = "2026-06-19T10:58:32.857Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl", hash = "sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c", size = 386536, upload-time = "2026-06-19T10:58:31.347Z" },
    +]
    +
    +[[package]]
    +name = "ruff"
    +version = "0.16.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/4d/94/1e5e4967626faf12fa56999cd6222dff6992ceb086ad7945756baf70c7a7/ruff-0.16.0.tar.gz", hash = "sha256:e460aafd5495ec89efaa6ced2e4a9a581116451e1c88b9d37ef497e0f8e93982", size = 4790557, upload-time = "2026-07-23T19:11:30.981Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/4b/81/1c8818fee7ce1a04cd7d1b3172e0a8f8e4f1dc4feb7fc390e16daa8af323/ruff-0.16.0-py3-none-linux_armv6l.whl", hash = "sha256:e5115729eb08c585e5121978ba5d5b60caeae394ce21b9fb5e6cd33a1c6c9b1e", size = 10754633, upload-time = "2026-07-23T19:10:46.415Z" },
    +    { url = "https://files.pythonhosted.org/packages/23/df/beaf59c09d68db84304d555f188b276a77132a5d5b0b67a5c762aa143628/ruff-0.16.0-py3-none-macosx_10_12_x86_64.whl", hash = "sha256:3c954b1d580bfa035b41654f7858cc7e71d5fc3ac5b723dd62bd9133830ed522", size = 10969164, upload-time = "2026-07-23T19:10:50.271Z" },
    +    { url = "https://files.pythonhosted.org/packages/42/ce/741cd197496a1abbf51352710fd15ed995d2a2be87189c1da26a450d6e83/ruff-0.16.0-py3-none-macosx_11_0_arm64.whl", hash = "sha256:e01c21d10eb1b29f47b7454e1f4056db9a3f0260c646aa88457c610291db9f81", size = 10488846, upload-time = "2026-07-23T19:10:52.639Z" },
    +    { url = "https://files.pythonhosted.org/packages/52/2a/a2db8e88cade358f5cdcb05674a917751074109315d014eb6352d9a893f7/ruff-0.16.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:6e364e5ed22ed8dc05082fd78e35308618260907ac2d3c1d637b2e682415b6c9", size = 10889729, upload-time = "2026-07-23T19:10:54.89Z" },
    +    { url = "https://files.pythonhosted.org/packages/42/65/62a771694ebd63029dc953e27dbad40e1588bd4860ff9fe881018fddaa49/ruff-0.16.0-py3-none-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:d327b8fc113a1d4421a04f3839d3752057c8dd1ee320223a6f3f52d04ada462a", size = 10568275, upload-time = "2026-07-23T19:10:56.993Z" },
    +    { url = "https://files.pythonhosted.org/packages/3f/e2/ced249fe8af5f086c5c58cc21cc3356d50f32f7401c5df87050c999620a7/ruff-0.16.0-py3-none-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:a9b50c55e263103586b3dcf5f73d479eb8cb5fdb6098fec59a62891dab653717", size = 11385112, upload-time = "2026-07-23T19:10:59.615Z" },
    +    { url = "https://files.pythonhosted.org/packages/87/0b/05154977a8fd69eeb6c103271f55403bfd8711f5c0f8ed07489d95a504e7/ruff-0.16.0-py3-none-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:0ff4a79ce3ec0172f3241943835de1c4cb4e2dcd07f0f8c2d02603dbbbee4b17", size = 12207008, upload-time = "2026-07-23T19:11:02.154Z" },
    +    { url = "https://files.pythonhosted.org/packages/fb/29/98225831a3a1eab0e02f4acc6ca6559a98611dcc68b6965ff4b7234627c1/ruff-0.16.0-py3-none-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:e95c448fca1fb2a18372a9440926c5a6ee789639bb975c72e7ae6d0b04218ab4", size = 11650842, upload-time = "2026-07-23T19:11:04.557Z" },
    +    { url = "https://files.pythonhosted.org/packages/91/66/6bd3cf90500653d55dc0ffc8507aa8300bd49d0214b2e8cb4d3fef2943ba/ruff-0.16.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:4f11a8d11010301d0a398a2fdef67691feca7294da6aef55e2150e8fa2cd520b", size = 11400718, upload-time = "2026-07-23T19:11:09.233Z" },
    +    { url = "https://files.pythonhosted.org/packages/8e/a2/a54eb4eae05d66364050a5d3b8a9c5ef88196531b3cbe7109d873f87f819/ruff-0.16.0-py3-none-manylinux_2_31_riscv64.whl", hash = "sha256:48044c678e9cb8698246c99b14aaccfa6601dea7379eb48a6f8f73f7a6d86cd0", size = 11426177, upload-time = "2026-07-23T19:11:11.994Z" },
    +    { url = "https://files.pythonhosted.org/packages/1a/be/16e3eea4b2a478a496919f5e36f17c4559e54620bd3bbac5d6affa068006/ruff-0.16.0-py3-none-musllinux_1_2_aarch64.whl", hash = "sha256:7aa0959bad8eb8bef50340154fc9b58678dae31fa4293afa38b44b6e552c0213", size = 10856126, upload-time = "2026-07-23T19:11:14.221Z" },
    +    { url = "https://files.pythonhosted.org/packages/a2/84/252eb8b868a16eec7257c14f504f77537e734b2d69c762e639e588e304a3/ruff-0.16.0-py3-none-musllinux_1_2_armv7l.whl", hash = "sha256:28ea2b7df8ebf7f9da6b7d47b230ab48f387c0a29be3b474c4d0740e197bb9af", size = 10571208, upload-time = "2026-07-23T19:11:16.378Z" },
    +    { url = "https://files.pythonhosted.org/packages/21/09/817a482f542f7570cbb4554b26e896610c7114f539b1d9e2d2145bf6bef6/ruff-0.16.0-py3-none-musllinux_1_2_i686.whl", hash = "sha256:33a3dfac8c35f81498dea9181bccc2f4c4bc8f1521a1dd9406e77643e0f0fb09", size = 11063329, upload-time = "2026-07-23T19:11:19.173Z" },
    +    { url = "https://files.pythonhosted.org/packages/2e/23/9403c180ca1cb9b1f7335f5c3e5305c09d49ea5b345196682a36028bde4a/ruff-0.16.0-py3-none-musllinux_1_2_x86_64.whl", hash = "sha256:a5237a0bda500d30d81b8e07a6973a5cbc772864cbf746ae2f4e8a2e01c9f4ed", size = 11489751, upload-time = "2026-07-23T19:11:21.74Z" },
    +    { url = "https://files.pythonhosted.org/packages/b2/1d/1b2ef7bcde851c78d7f17f1cca13fd6dc695fc4b3d6197941e72cae5b132/ruff-0.16.0-py3-none-win32.whl", hash = "sha256:7fab76fa065c873f41ff744347c6e77bcc3dfec4bcc754dc26b63d23c0f7f5fb", size = 10785885, upload-time = "2026-07-23T19:11:23.947Z" },
    +    { url = "https://files.pythonhosted.org/packages/b2/a3/d5e4ef7a56be3f928ffb90b94c25ba7d3cb9c7fe0736aeaaedf361770712/ruff-0.16.0-py3-none-win_amd64.whl", hash = "sha256:429c117f022bf481fabd9d551e7a3952b24c65e6ef44337ea09d90bebef14472", size = 11923141, upload-time = "2026-07-23T19:11:26.409Z" },
    +    { url = "https://files.pythonhosted.org/packages/cb/9a/8415f2657cbe200f41a4531ccededf135505a92d4a012229121f885b26f9/ruff-0.16.0-py3-none-win_arm64.whl", hash = "sha256:14296fedcd2705c77ab8235439278bbb38f285cf7da5528b00b3e330c3d4872d", size = 11273407, upload-time = "2026-07-23T19:11:28.705Z" },
    +]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/01-domain-contracts/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/tutorial/02-points-payload.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/01-domain-contracts/stage.patch)
