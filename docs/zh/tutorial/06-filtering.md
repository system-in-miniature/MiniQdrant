# 第 6 章：过滤

> [English](../../tutorial/06-filtering.md) · 中文

向量相似度回答“哪些点彼此接近？”，payload 过滤又加了一问：“这些相近点中，哪些有资格进入结果？”MiniQdrant 刻意把两件事拆开：过滤器先变成有类型的条件树，payload 索引缩小可能的 point ID 范围，索引无法证明的条件则保留为 **residual（残余谓词）**。只有候选路径与 residual 求值一致，搜索才是正确的。

## 学习目标

完成本章后，你应当能够：

1. 构造并预测 `must`、`should`、`must_not` 过滤器；
2. 解释 MiniQdrant 自动展开数组的点路径语义；
3. 跟踪 `PayloadIndexSet.candidates()` 如何从索引子句得到 residual；
4. 区分精确候选集与基数估计；
5. 验证索引过滤与完整求值返回相同 ID。

## 1. 从条件树到布尔判断

公开的过滤词汇定义在 `src/miniqdrant/filters/ast.py`：`Match`、`Range`、`HasId`，以及可递归嵌套的 `Filter`。它们的 `__post_init__()` 会在构造阶段拒绝畸形路径、非有限数值、空 ID 集、互相矛盾的范围边界和不支持的条件对象。这样搜索循环就不必再次发现基础结构错误。

最终的布尔语义位于 `src/miniqdrant/filters/evaluate.py::matches_filter`：

```python
return (
    all(... for item in filter_.must)
    and not any(... for item in filter_.must_not)
    and (not filter_.should or any(... for item in filter_.should))
)
```

因此，每个 `must` 都必须匹配，任何 `must_not` 都不能匹配；当 `should` 非空时，至少要匹配一项。在这个教学实现里，`should` 不只是给分数加权。空 `should` 则自然成立。

字段查找同样重要。`src/miniqdrant/filters/evaluate.py::resolve_path` 把点路径拆开后交给 `_walk_path`。映射消费一个路径分量；序列则对每个元素递归应用尚未消费的同一路径；到达叶子后，数组还会再次摊平。因此 `Match("reviews.user", "bob")` 能在下面的 payload 中找到 Bob：

```python
{"reviews": [{"user": "alice"}, {"user": "bob"}]}
```

随后 `Match` 和 `Range` 使用“任一叶子匹配”语义。缺失路径解析为零个值，所以连 `Match("missing", None)` 也是 false。虽然 Python 的 `bool` 是 `int` 的子类，范围判断仍明确排除了布尔值。

这种路径规则很方便，却会丢失关联性。`reviews.user == "alice"` 与 `reviews.score >= 5` 可能分别被两个不同数组元素满足。MiniQdrant 没有“同一元素内”的 nested 条件算子。

## 2. Payload 索引只证明它知道的事

`src/miniqdrant/filters/index.py::PayloadFieldIndex` 支持四种 schema：`keyword`、`integer`、`float`、`bool`。`upsert()` 先删除该点的旧索引值，再解析配置路径、接收与 schema 兼容的值并更新等值映射。`range()` 可以扫描整数或浮点索引保存的值；对 keyword 索引请求范围会返回 `None`，意思是“该索引无法回答”，而不是“没有匹配项”。

`PayloadIndexSet` 拥有 live-ID 全集与所有字段索引。核心方法是 `PayloadIndexSet.candidates()`：

```python
resolved = self._resolve(filter_, universe)
if resolved.exact:
    return CandidateSet(resolved.ids, exact_count(len(resolved.ids)), True, None)
return CandidateSet(
    resolved.ids,
    CardinalityEstimate(0, len(resolved.ids) // 2, len(resolved.ids), False),
    False,
    filter_,
)
```

有索引的 `Match`、有索引的数值 `Range` 或 `HasId` 能产生精确集合。无索引条件返回当前全集并标记 `exact=False`。对 `must` 而言，即使另一条子句尚未解析，已经精确得到的集合仍可参与交集。这正是有用的中间状态：索引减少了工作量，却不会假装过滤已经完成。

未解析的 `should` 与 `must_not` 必须更谨慎。未解析的 `should` 不能安全缩小候选集，因为无索引分支可能放行某个点；未解析的 `must_not` 也不能安全减去任何点。因此 `PayloadIndexSet._resolve_filter()` 保留保守超集，并将其标记为非精确。

返回的 `CandidateSet` 携带四项事实：

- `ids`：匹配 live ID 的安全超集；
- `estimate`：基数的下界、期望值和上界；
- `exact`：`ids` 是否已经是完整答案；
- `residual`：无法精确证明时保留的原始过滤器。

非精确集合当前使用 `[0, N/2, N]` 启发式。这是可观察的教学算术，不是统计模型。

### 实用调试顺序

过滤搜索返回意外点时，应从语义向加速层调试。先用 point ID 和 payload 直接调用 `matches_filter()`。若结果已经意外，检查 `resolve_path()`，并记住数组会自动摊平。然后把 `PayloadIndexSet.candidates()` 的 ID 与“对每个 live 点调用 `matches_filter()`”的推导式比较。候选可以是超集，但绝不能漏掉真实匹配。最后检查 `exact` 与 `residual`：非精确候选却没有 residual 会构成正确性缺陷。

更新还提供了另一个探针。`PayloadFieldIndex.upsert()` 以 `delete(point.id)` 开头，所以把 `{"kind": "book"}` 替换为 `{"kind": "movie"}` 时，必须先把 ID 从 book posting set 删除，再加入 movie 集合。`tests/query/test_payload_index.py::test_index_update_removes_old_value` 守护这个转换。如果 collection 更新后仍出现陈旧索引成员，应从 `MutableSegment.apply_upsert()` 跟到它的 `PayloadIndexSet`，再检查 latest-version 可见性层是否拒绝了旧点镜像。这个顺序能分开三类 bug：过滤语义错误、索引维护错误、跨段版本可见性错误。

### 把候选证明当作接口合同

candidate/residual 拆分为未来索引实现提供了精确合同。新索引只有在能证明被移除的每个 ID 都不满足条件时，才可以返回更少 ID；否则必须保留这些 ID，并把解析标为非精确。返回更大的超集只改变成本，不改变结果；无正当理由返回更小集合会产生无法挽回的 false negative，因为 residual 永远看不到缺失点。

这种区别决定测试写法。索引测试应把候选集与完整求值比较，断言每个真实匹配都存在。若 `exact=True`，还应断言集合相等且 `residual is None`；若 `exact=False`，应在候选集上执行 residual，再把最终集合与完整求值比较。测试还要在 upsert 和 delete 后重复，因为静态 posting list 正确，不代表维护逻辑正确。该合同让 MiniQdrant 未来可以加入更快的 range 结构，而无需改变过滤语义或 planner 含义。

## 3. Residual 在哪里执行

`src/miniqdrant/segment/immutable.py::ImmutableSegment.search` 在调用查询规划器前，先向 payload 索引请求候选。如果规划器选择精确扫描，该段会用候选 ID 构造 `PlainVectorIndex`，并把 residual 传给 `PlainVectorIndex.search_with_stats()`。在量化分支，`src/miniqdrant/query/executor.py::execute_quantized_rescore` 把 residual 转成 `matches_filter()` 谓词。在图分支，`ImmutableSegment.search()` 也会在返回过采样候选前再次调用 `matches_filter()`。

看似重复的工作其实是正确性边界：候选生成可以保守，结果准入不能保守。[行为矩阵](../behavior-matrix.md)记录了这个不变量：索引候选加 residual 求值必须等价于完整求值。直接证据是 `tests/query/test_payload_index.py::test_payload_index_candidates_equal_scan` 与 `test_unindexed_condition_is_retained_as_residual`；`tests/query/test_plan_parity.py::test_indexed_and_unindexed_exact_search_return_same_hits` 则检查公开搜索结果。

## 4. 与真实 Qdrant 对照

真实 Qdrant 同样把 payload filter 建模为条件树，并用结构化 payload 索引估算、缩小候选集。在 Qdrant 源码树中，相近概念位于 `lib/segment/src/types.rs` 的过滤类型，以及 `lib/segment/src/index/struct_payload_index.rs` 一带。用户通过 collection API 创建 payload 索引，而且可配置的类型远多于 MiniQdrant 的四种 schema。

相似性到教学边界为止：

- Qdrant 支持更多字段索引族，包括 text、geo、datetime 与持久化后端；
- Qdrant 使用显式数组路径记法，并以 nested 条件把谓词约束在同一数组元素；MiniQdrant 自动展开数组，会丢失这种关联；
- Qdrant 将过滤与生产 HNSW 遍历结合；MiniQdrant 的“filtered HNSW”先遍历，再对固定倍数的过采样结果做后过滤；
- MiniQdrant 的非精确基数是固定中点启发式，不是生产统计。

这些不是微小语法差异；它们可能改变哪些点匹配以及搜索做多少工作。参见[完整差异文档](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)第 5 条、[行为矩阵](../behavior-matrix.md)的过滤与基数行，以及 [Qdrant 映射](../qdrant-mapping.md)的查询/索引行。

## 5. 动手实验

从仓库根目录运行。显式设置 `UV_CACHE_DIR`，让命令在默认 uv 缓存只读的沙箱中也能工作。

### 实验 A：观察公开过滤搜索

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python -m miniqdrant.labs.filtering
```

实测输出：

```text
Filtering lab: query=(1.0, 0.0), tenant='a', limit=10
Matching ids: [1, 3]
Selected plan: ('exact_full_scan',)

Interpretation:
- point 2 is vector-similar but excluded because its tenant is 'b'.
- the payload index lets the public collection API plan a filtered search.
```

fixture 很小，所以计划是精确扫描。过滤仍会在 point 2 进入最终 Top-K 前将它排除。

### 实验 B：暴露候选与 residual

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python - <<'PY'
from miniqdrant import CollectionConfig, Distance, Filter, Match, Point, Range
from miniqdrant.filters.index import PayloadIndexSet, PayloadSchema
from miniqdrant.models import validate_point

config = CollectionConfig(dimension=2, distance=Distance.DOT)
points = tuple(validate_point(point, config) for point in (
    Point(1, (1, 0), {"kind": "book", "price": 10.0}),
    Point(2, (0, 1), {"kind": "movie", "price": 20.0}),
    Point(3, (1, 1), {"kind": "book", "price": 30.0}),
))
indexes = PayloadIndexSet(point.id for point in points)
indexes.create("kind", PayloadSchema.KEYWORD, points)
query = Filter(must=(Match("kind", "book"), Range("price", lte=20.0)))
partial = indexes.candidates(query)
print("kind-only ids:", sorted(partial.ids))
print("exact:", partial.exact, "estimate:", partial.estimate)
print("residual retained:", partial.residual is query)
indexes.create("price", PayloadSchema.FLOAT, points)
complete = indexes.candidates(query)
print("fully indexed ids:", sorted(complete.ids))
print("exact:", complete.exact, "estimate:", complete.estimate)
print("residual:", complete.residual)
PY
```

实测输出：

```text
kind-only ids: [1, 3]
exact: False estimate: CardinalityEstimate(minimum=0, expected=1, maximum=2, exact=False)
residual retained: True
fully indexed ids: [1]
exact: True estimate: CardinalityEstimate(minimum=1, expected=1, maximum=1, exact=True)
residual: None
```

验收命令：

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/contract/test_filters.py tests/query/test_payload_index.py
```

实测结果：`15 passed in 0.08s`。

## 6. 练习

1. **理解题：**为什么无索引的 `must_not` 子句必须让候选全集保持不变？
2. **理解题：**`reviews.user == "alice"` 与 `reviews.score >= 5` 能证明 Alice 给了 5 分吗？
3. **动手设计题：**设计一个 `exists(path)` 条件。不要修改 `src/`；把 AST、扫描求值器与候选解析的改动写成 scratch patch。验收标准：缺失路径为 false、数组叶子可见、无索引 exists 会保留 residual，并列出三个聚焦测试名。

??? note "参考答案"

    1. 减去一个未解析集合可能误删合格点。保留全集得到安全超集，之后由 residual 精确执行排除。
    2. 不能。`_walk_path()` 会独立摊平两条路径，Alice 可能出现在一个对象，5 分出现在另一个对象。真实 Qdrant 的 nested 条件能保持元素内关联，MiniQdrant 不能。
    3. 合适的 scratch patch 可新增使用 `_validate_path` 的 frozen `Exists(path)` dataclass，把它加入 `Condition`，用 `bool(resolve_path(payload, path))` 求值；在 existence 索引出现前，`_resolve()` 返回 `_Resolved(universe, False)`。建议测试为 `test_exists_matches_present_null`、`test_exists_traverses_array_objects`、`test_unindexed_exists_is_retained_as_residual`。在一次性 worktree 应用 scratch patch 后，用 `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/contract/test_filters.py tests/query/test_payload_index.py` 验收。

## 小结

MiniQdrant 过滤并不是“查出一些 ID，然后祈祷结果正确”。AST 定义布尔语义，路径遍历定义字段含义，索引返回可证明安全的候选超集，residual 求值补齐所有证明缺口。候选集还会提供基数边界。第 7 章将沿着这些边界进入 `QueryPlanner`，观察它们如何决定一个段是扫描、先过滤、遍历 HNSW，还是进入量化分支。
