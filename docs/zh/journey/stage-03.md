# Stage 03 · 结构化 Payload 过滤

### 目标

实现结构化 Payload 过滤，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/miniqdrant/__init__.py`
    - `src/miniqdrant/filters/__init__.py`
    - `src/miniqdrant/filters/ast.py`
    - `src/miniqdrant/filters/evaluate.py`
    - `tests/contract/test_filters.py`

### 当前遇到的问题

Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。

### 测试契约

#### 先看会坏在哪里

聚焦测试让结构化 Payload 过滤经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/contract/test_filters.py"
    ```diff
    diff --git a/tests/contract/test_filters.py b/tests/contract/test_filters.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9f71efe32fd5aa0366a239a98f6b05cc7a3c3fc6
    --- /dev/null
    +++ b/tests/contract/test_filters.py
    @@ -0,0 +1,87 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from miniqdrant.errors import InvalidFilterError
    +from miniqdrant.filters import Filter, HasId, Match, Range, matches_filter
    +
    +
    +def test_boolean_filter_and_array_any_semantics() -> None:
    +    payload = {"kind": "book", "price": 12.0, "tags": ["python", "db"]}
    +    condition = Filter(
    +        must=(Match("kind", "book"), Range("price", lte=20)),
    +        should=(Match("tags", "python"), Match("tags", "rust")),
    +        must_not=(Match("kind", "movie"),),
    +    )
    +
    +    assert matches_filter(1, payload, condition)
    +
    +
    +def test_should_requires_one_match_when_present() -> None:
    +    payload = {"kind": "book"}
    +
    +    assert matches_filter(1, payload, Filter(must=(Match("kind", "book"),)))
    +    assert not matches_filter(
    +        1,
    +        payload,
    +        Filter(
    +            must=(Match("kind", "book"),),
    +            should=(Match("language", "python"),),
    +        ),
    +    )
    +
    +
    +def test_nested_dot_path_traverses_arrays_of_objects() -> None:
    +    payload = {
    +        "reviews": [
    +            {"user": "alice", "score": 4},
    +            {"user": "bob", "score": 5},
    +        ]
    +    }
    +
    +    assert matches_filter(
    +        1,
    +        payload,
    +        Filter(must=(Match("reviews.user", "bob"), Range("reviews.score", gte=5))),
    +    )
    +
    +
    +def test_missing_path_does_not_match_range_or_match() -> None:
    +    assert not matches_filter(1, {}, Filter(must=(Range("price", gte=1),)))
    +    assert not matches_filter(1, {}, Filter(must=(Match("kind", None),)))
    +
    +
    +def test_has_id_and_nested_filter() -> None:
    +    condition = Filter(
    +        must=(
    +            HasId((1, 2)),
    +            Filter(must=(Match("visible", True),)),
    +        )
    +    )
    +
    +    assert matches_filter(2, {"visible": True}, condition)
    +    assert not matches_filter(3, {"visible": True}, condition)
    +
    +
    +def test_must_not_excludes_match() -> None:
    +    condition = Filter(must_not=(Match("status", "deleted"),))
    +
    +    assert matches_filter(1, {"status": "active"}, condition)
    +    assert not matches_filter(1, {"status": "deleted"}, condition)
    +
    +
    +@pytest.mark.parametrize(
    +    "condition",
    +    [
    +        lambda: Match("", "book"),
    +        lambda: Match("bad..path", "book"),
    +        lambda: Range("price"),
    +        lambda: Range("price", gt=float("nan")),
    +        lambda: Range("price", gt=2, lte=1),
    +        lambda: HasId(()),
    +    ],
    +)
    +def test_invalid_conditions_fail_at_construction(condition) -> None:
    +    with pytest.raises(InvalidFilterError):
    +        condition()
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让结构化 Payload 过滤经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matches_filter(1, payload, condition)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是结构化 Payload 过滤。Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。

### 为什么需要这个机制

Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

### 机制板块

#### 结构化 Payload 过滤机制

每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

??? note "文件差异：src/miniqdrant/filters/ast.py"
    ```diff
    diff --git a/src/miniqdrant/filters/ast.py b/src/miniqdrant/filters/ast.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4b024f0488a6727c57758fc956bfdbc780620cb8
    --- /dev/null
    +++ b/src/miniqdrant/filters/ast.py
    @@ -0,0 +1,98 @@
    +from __future__ import annotations
    +
    +import math
    +from dataclasses import dataclass
    +from numbers import Real
    +
    +from miniqdrant.errors import InvalidFilterError
    +from miniqdrant.ids import PointId, canonicalize_point_id
    +
    +type MatchScalar = bool | int | float | str | None
    +
    +
    +def _validate_path(path: str) -> None:
    +    if not path or any(not part for part in path.split(".")):
    +        raise InvalidFilterError("filter field path must contain non-empty components")
    +
    +
    +def _validate_scalar(value: object) -> None:
    +    if not isinstance(value, (bool, int, float, str)) and value is not None:
    +        raise InvalidFilterError("match value must be a JSON scalar")
    +    if isinstance(value, float) and not math.isfinite(value):
    +        raise InvalidFilterError("match number must be finite")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Match:
    +    path: str
    +    value: MatchScalar
    +
    +    def __post_init__(self) -> None:
    +        _validate_path(self.path)
    +        _validate_scalar(self.value)
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Range:
    +    path: str
    +    gt: float | int | None = None
    +    gte: float | int | None = None
    +    lt: float | int | None = None
    +    lte: float | int | None = None
    +
    +    def __post_init__(self) -> None:
    +        _validate_path(self.path)
    +        bounds = tuple(
    +            value for value in (self.gt, self.gte, self.lt, self.lte) if value is not None
    +        )
    +        if not bounds:
    +            raise InvalidFilterError("range must contain at least one bound")
    +        if any(
    +            isinstance(value, bool)
    +            or not isinstance(value, Real)
    +            or not math.isfinite(float(value))
    +            for value in bounds
    +        ):
    +            raise InvalidFilterError("range bounds must be finite numbers")
    +        lower = self.gt if self.gt is not None else self.gte
    +        upper = self.lt if self.lt is not None else self.lte
    +        if lower is not None and upper is not None and lower > upper:
    +            raise InvalidFilterError("range lower bound cannot exceed upper bound")
    +        if self.gt is not None and self.gte is not None:
    +            raise InvalidFilterError("range cannot contain both gt and gte")
    +        if self.lt is not None and self.lte is not None:
    +            raise InvalidFilterError("range cannot contain both lt and lte")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class HasId:
    +    ids: tuple[PointId, ...]
    +
    +    def __post_init__(self) -> None:
    +        if not self.ids:
    +            raise InvalidFilterError("has-id condition must contain at least one point id")
    +        try:
    +            canonical = tuple(canonicalize_point_id(value) for value in self.ids)
    +        except ValueError as error:
    +            raise InvalidFilterError("has-id condition contains an invalid point id") from error
    +        object.__setattr__(self, "ids", canonical)
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Filter:
    +    must: tuple[Match | Range | HasId | Filter, ...] = ()
    +    should: tuple[Match | Range | HasId | Filter, ...] = ()
    +    must_not: tuple[Match | Range | HasId | Filter, ...] = ()
    +
    +    def __post_init__(self) -> None:
    +        allowed = (Match, Range, HasId, Filter)
    +        for clause in (self.must, self.should, self.must_not):
    +            if any(not isinstance(condition, allowed) for condition in clause):
    +                raise InvalidFilterError("filter contains an unsupported condition")
    +        object.__setattr__(self, "must", tuple(self.must))
    +        object.__setattr__(self, "should", tuple(self.should))
    +        object.__setattr__(self, "must_not", tuple(self.must_not))
    +
    +
    +type Condition = Match | Range | HasId | Filter
    +
    ```

??? note "文件差异：src/miniqdrant/filters/evaluate.py"
    ```diff
    diff --git a/src/miniqdrant/filters/evaluate.py b/src/miniqdrant/filters/evaluate.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3671c4f50af710e15be4bc25bac8bf41431ab93d
    --- /dev/null
    +++ b/src/miniqdrant/filters/evaluate.py
    @@ -0,0 +1,81 @@
    +from __future__ import annotations
    +
    +from collections.abc import Mapping, Sequence
    +from numbers import Real
    +
    +from miniqdrant.filters.ast import Condition, Filter, HasId, Match, Range
    +from miniqdrant.ids import PointId
    +
    +
    +def matches_filter(
    +    point_id: PointId,
    +    payload: Mapping[str, object],
    +    filter_: Filter | None,
    +) -> bool:
    +    if filter_ is None:
    +        return True
    +    return (
    +        all(_matches_condition(point_id, payload, item) for item in filter_.must)
    +        and not any(_matches_condition(point_id, payload, item) for item in filter_.must_not)
    +        and (
    +            not filter_.should
    +            or any(_matches_condition(point_id, payload, item) for item in filter_.should)
    +        )
    +    )
    +
    +
    +def resolve_path(payload: Mapping[str, object], path: str) -> tuple[object, ...]:
    +    return tuple(_walk_path(payload, path.split(".")))
    +
    +
    +def _walk_path(value: object, parts: list[str]) -> list[object]:
    +    if not parts:
    +        if _is_array(value):
    +            result: list[object] = []
    +            for item in value:
    +                result.extend(_walk_path(item, []))
    +            return result
    +        return [value]
    +    if isinstance(value, Mapping):
    +        head, *tail = parts
    +        if head not in value:
    +            return []
    +        return _walk_path(value[head], tail)
    +    if _is_array(value):
    +        result = []
    +        for item in value:
    +            result.extend(_walk_path(item, parts))
    +        return result
    +    return []
    +
    +
    +def _is_array(value: object) -> bool:
    +    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    +
    +
    +def _matches_condition(
    +    point_id: PointId,
    +    payload: Mapping[str, object],
    +    condition: Condition,
    +) -> bool:
    +    if isinstance(condition, Filter):
    +        return matches_filter(point_id, payload, condition)
    +    if isinstance(condition, HasId):
    +        return point_id in condition.ids
    +    values = resolve_path(payload, condition.path)
    +    if isinstance(condition, Match):
    +        return any(value == condition.value for value in values)
    +    return any(_matches_range(value, condition) for value in values)
    +
    +
    +def _matches_range(value: object, condition: Range) -> bool:
    +    if isinstance(value, bool) or not isinstance(value, Real):
    +        return False
    +    if condition.gt is not None and not value > condition.gt:
    +        return False
    +    if condition.gte is not None and not value >= condition.gte:
    +        return False
    +    if condition.lt is not None and not value < condition.lt:
    +        return False
    +    return condition.lte is None or value <= condition.lte
    +
    ```

**是什么，为什么现在需要**

核心机制是结构化 Payload 过滤。Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较。

**在运行时做什么**

每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

**关键语句理解**

真正要守住的边界是：每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（2 个文件）"
    **`src/miniqdrant/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/__init__.py b/src/miniqdrant/__init__.py
    index ba71f390797f515553ff2c37ed4c6358d9763f66..c14c225211f54423ba62568adc841a2ba4cd970d 100644
    --- a/src/miniqdrant/__init__.py
    +++ b/src/miniqdrant/__init__.py
    @@ -18,6 +18,7 @@ from miniqdrant.errors import (
         SchemaMismatchError,
         SnapshotError,
     )
    +from miniqdrant.filters import Filter, HasId, Match, Range, matches_filter
     from miniqdrant.models import Point, SearchHit, SearchRequest, SearchResult, StoredPoint
     from miniqdrant.topk import Candidate, TopK

    @@ -29,14 +30,18 @@ __all__ = [
         "CollectionNotFoundError",
         "CorruptionError",
         "Distance",
    +    "Filter",
    +    "HasId",
         "HnswConfig",
         "InvalidFilterError",
         "InvalidPointError",
         "InvalidVectorError",
    +    "Match",
         "MiniQdrantError",
         "OptimizerConfig",
         "PayloadIndexError",
         "Point",
    +    "Range",
         "ScalarQuantizationConfig",
         "SchemaMismatchError",
         "SearchHit",
    @@ -45,4 +50,5 @@ __all__ = [
         "SnapshotError",
         "StoredPoint",
         "TopK",
    +    "matches_filter",
     ]
    ```

    **`src/miniqdrant/filters/__init__.py`**

    ```diff
    diff --git a/src/miniqdrant/filters/__init__.py b/src/miniqdrant/filters/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..aa71632273b06faa5ab4f811f672f7e114397838
    --- /dev/null
    +++ b/src/miniqdrant/filters/__init__.py
    @@ -0,0 +1,14 @@
    +from miniqdrant.filters.ast import Condition, Filter, HasId, Match, MatchScalar, Range
    +from miniqdrant.filters.evaluate import matches_filter, resolve_path
    +
    +__all__ = [
    +    "Condition",
    +    "Filter",
    +    "HasId",
    +    "Match",
    +    "MatchScalar",
    +    "Range",
    +    "matches_filter",
    +    "resolve_path",
    +]
    +
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/03-payload-filters/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/06-filtering.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/03-payload-filters/stage.patch)
