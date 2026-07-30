# 第 8 章：量化

> [English](../../tutorial/08-quantization.md) · 中文

稠密向量通常以浮点数保存。标量量化把每个分量换成小整数 code，缩小候选打分阶段所用的表示。生产系统中有用的模式是两阶段检索：先用近似表示选出多于最终需要的候选，再用原始向量重打分。MiniQdrant 实现了这个形状，但候选阶段刻意采用“解码回浮点后的全扫描”，既没有 Qdrant 的整数 scorer，也没有 HNSW 加速。

## 学习目标

完成本章后，你应当能够：

1. 推导 MiniQdrant 逐维 int8 scale 与 code；
2. 解释常量维处理和误差界；
3. 跟踪 oversampling 后的精确重打分；
4. 从源码证明量化分支目前扫描全部合格 code，且绕过 HNSW；
5. 把 recall 证据与存储、延迟、兼容性主张分开。

## 1. 拟合标量量化器

`src/miniqdrant/index/quantization.py` 保留从 `-128` 到 `127` 的整数 code，共 255 个区间。`ScalarQuantizer.fit()` 物化训练向量，拒绝空、ragged、零维或非有限输入，并计算每一维的最小值与最大值。

若某维最小值为 \(a\)、最大值为 \(b\)，scale 为：

\[
s = \frac{b-a}{255}
\]

若 \(a=b\)，scale 为零。否则 `ScalarQuantizer.encode()` 计算：

```python
code = round((number - minimum) / scale) + _MIN_CODE
```

再把结果夹在 int8 范围内。`decode()` 做逆映射：

```python
minimum + (code - _MIN_CODE) * scale
```

向最近网格点取整，使单分量最大误差约为半个 scale。`ScalarQuantizer.max_error_bound` 返回各维 `scale / 2` 的最大值；它不是 dot product 误差界，也不是最终排名误差界。

常量维必须显式处理。编码总是输出 code 0，解码返回 minimum（也等于 maximum）。没有这个分支，拟合会除以零。注意，code 0 并不是一般量化区间的中点；它只是该维没有方差时的确定性哨兵。

## 2. 构建量化索引

`ScalarQuantizedIndex.__init__()` 保存原始 `StoredPoint` 字典，在所有向量上拟合一个量化器，再为每个点生成 code tuple。空索引会被拒绝。

`src/miniqdrant/segment/immutable.py::ImmutableSegment.__init__` 只在三个条件都成立时构建量化索引：

- 段以 `indexed=True` 构建；
- `CollectionConfig.quantization` 不是 `None`；
- 段至少有一个 live 点。

它可能在量化索引旁同时构建 HNSW，但当前量化执行路径不会组合这两个结构。段持久化也不会保存可复用 code。[行为矩阵](../behavior-matrix.md)明确写着：打开段时会重建 code。

配置刻意保持很小。`src/miniqdrant/config.py::ScalarQuantizationConfig` 只暴露正整数 `oversampling`，默认值 4。这里没有存储模式、quantile 选择、always-RAM 设置、压缩比或硬件 scorer 控制。

## 3. 先近似候选，再精确重打分

核心实现在 `src/miniqdrant/index/quantization.py::ScalarQuantizedIndex.search`。它先对查询编码并立刻解码：

```python
approximate_query = self._quantizer.decode(self._quantizer.encode(query))
capacity = min(len(self._points), limit * oversampling)
approximate = TopK(max(1, capacity))
```

随后循环 **每一个 code**。候选 ID 与 residual 谓词可以跳过点，但每个剩余点都会增加 `visited`，并在 code 解码回 Python 浮点 tuple 后打分。近似 Top-K 保留 `limit * oversampling` 个幸存者。

第二个 `TopK(limit)` 从 `self._points` 读取原始向量，只用原查询给幸存者打分：

```python
for candidate in approximate.results():
    point = self._points[candidate.point_id]
    rescored.offer(point.id, score(self._distance, query, point.vector))
```

所以，即使候选排序是近似的，最终 hit score 仍可等于精确浮点评分。但若量化打分没把某个真实近邻放进过采样候选，第二阶段无法把它找回来。提高 oversampling 通常能降低该风险，却会增加重打分工作。若 capacity 达到 collection 大小，全部合格点都进入精确重打分，recall 变为精确，代价是一次全扫描再加一次打分。

`src/miniqdrant/query/executor.py::execute_quantized_rescore` 是薄适配器：它转发 payload candidate ID，并把 residual filter 变成谓词。`ImmutableSegment.search()` 在 `Strategy.QUANTIZED_HNSW_RESCORE` 时选择该适配器，但既不传 `self._hnsw`，适配器签名也不接收 HNSW 索引。这一签名级证据证明图被绕过。

精确请求走另一条路径。`QueryPlanner.choose()` 把 `exact_requested` 放在最高优先级，因此段会使用 `PlainVectorIndex`，而非量化打分。

## 4. 测试究竟证明了什么

`tests/index/test_quantization.py::test_int8_round_trip_has_bounded_error` 对照 `max_error_bound` 检查分量重建。`test_constant_dimension_uses_zero_code_and_round_trips` 覆盖零 scale 分支，参数化拒绝测试覆盖空与 ragged 输入。

在 collection 层，`tests/query/test_quantized_rescore.py::test_quantized_candidates_are_rescored_with_original_vectors` 把返回 score 与 retrieved 原始向量上的 `metrics.score()` 比较；`test_exact_request_bypasses_quantized_candidate_scoring` 检查计划选择；固定 seed 的 200 点实验要求十个查询的最小 recall 不低于 0.95。

这些测试只为有限 fixture 建立确定性的本地行为。它们不证明磁盘压缩内存占用、整数算术、延迟加速、生产规模 recall 或 Qdrant 等价性。

### 诊断 recall 与 score 异常

近似和精确 hit ID 不同时，先确认最终 score 来自原始向量。若 hit 带着量化重建 score，说明重打分路径有 bug；若幸存者 score 正确但少了精确近邻，则是候选 recall 问题。在 scratch 实验中提高 oversampling：若 recall 改善，说明近似 Top-K 丢掉了该点；若没有改善，应比较 `allowed_ids` 和 residual 谓词，因为过滤可能在打分前排除了它。

接着检查 scale。一个 outlier 会扩大该维 `[minimum, maximum]` 范围，使中心密集区域的网格变粗。单一全局 fit 没有 quantile clipping，因此这是预期行为，不是数值损坏。对于 cosine collection，还要记住 `validate_point()` 存储的是归一化向量，`ImmutableSegment.search()` 也会在到达量化器前归一化查询；若隔离复现实验时使用未归一化输入，实验本身已经变了。

最后用 `visited_count` 确认执行形状。今天计数等于全部合格 ID 是预期行为。把它叫成“优化性能回退”，等于混淆已声明的教学实现与它所对照的生产设计。

### 分开表示、算术与遍历

“量化搜索”可能描述三个彼此独立、却很容易被揉成一件事的选择。第一是 **表示**：存储候选是否编码为小整数？MiniQdrant 在内存中这样做。第二是 **算术**：打分是否直接在整数 code 上运行，并使用合适修正项？MiniQdrant 没有，而是解码回浮点。第三是 **遍历**：近似索引是否避免给每个候选打分？MiniQdrant 该分支也没有，而是迭代全部合格 code dictionary。

这种分解使性能主张可测试。持久化 code tuple 会改变表示的 durability，却不会创造整数打分；把 decoded scoring 替换成 native int8 kernel 可能改变算术成本，却仍会扫描每个点；把该 scorer 接入 HNSW 才可能改变 traversal work，但仍需 recall 与 latency 实验。精确 float rescore 还是第四个独立决定。仓库目前只实现了这个更大设计空间中的一组选择，而不是一个不可拆分、名为“quantization”的功能。

## 5. 与真实 Qdrant 对照

真实 Qdrant 的标量量化集成进向量存储和打分栈，相关源码位于 `lib/segment/src/vector_storage/quantized/` 一带。Qdrant 可以保留量化表示，在 HNSW 遍历时使用 int8 scorer，选择候选，再按配置重打分原始向量；collection 配置也暴露更丰富的量化表面。

MiniQdrant 只保留概念流水线：

```text
拟合标量网格 → 编码 → 近似候选 Top-K
             → 过采样 → 原始浮点重打分
```

在性能关键的中间部分，它的运行行为语义相反：把 code 解码回浮点、扫描所有合格 code、绕过 HNSW，并在打开持久化段时重建 code。策略名中虽然含有 “HNSW”，HNSW 却没有执行。

参见 [`DIFFERENCES_FROM_QDRANT.md`](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md) 第 2、7 条、[行为矩阵](../behavior-matrix.md)的标量量化行，以及 [Qdrant 映射](../qdrant-mapping.md)中的 `ScalarQuantizedIndex` / `execute_quantized_rescore` 行。这是“接口名不能代替执行证据”的重要案例。

## 6. 动手实验

### 实验 A：检查量化网格

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python - <<'PY'
from miniqdrant.index.quantization import ScalarQuantizer

vectors = ((-4.0, 2.0), (0.0, 2.0), (7.0, 2.0))
quantizer = ScalarQuantizer.fit(vectors)
probe = (1.25, 2.0)
code = quantizer.encode(probe)
restored = quantizer.decode(code)
print("minima:", quantizer.minima)
print("scales:", tuple(round(x, 6) for x in quantizer.scales))
print("code:", code)
print("restored:", tuple(round(x, 6) for x in restored))
print("max_error_bound:", round(quantizer.max_error_bound, 6))
PY
```

实测输出：

```text
minima: (-4.0, 2.0)
scales: (0.043137, 0.0)
code: (-6, 0)
restored: (1.262745, 2.0)
max_error_bound: 0.021569
```

第一分量与 probe 相差约 0.012745，低于半 scale 误差界；常量第二分量精确 round-trip。

### 实验 B：验证重建、rescore、bypass 与 recall

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/index/test_quantization.py tests/query/test_quantized_rescore.py
```

实测输出：

```text
.......                                                                  [100%]
7 passed in 2.77s
```

若要把全扫描后果与图搜索并排观察，可重跑第 7 章 plan comparison。实测量化行在 64 点段上报告 `visited=64`。

## 7. 练习

1. **理解题：**为什么精确重打分不保证精确 recall？
2. **理解题：**`max_error_bound` 约束什么，又不约束什么？
3. **动手扩展题：**把持久化 `quantization.bin` 段组件设计成 scratch diff；不要修改 `src/`。说明 metadata、checksum、schema 校验，以及 `SegmentImage.to_segment()` 如何复用它。验收标准：列出 round-trip 测试和 corruption 测试，并说明当前哪条“打开时重建 code”的声明需要改变。

??? note "参考答案"

    1. Rescore 只能重排过采样幸存者。如果近似打分排除了真实 top-K 点，精确阶段永远看不到它。
    2. 它约束当前量化网格的最坏单分量重建误差；不约束向量度量误差、排名移动、recall、延迟或总内存。
    3. 合理的 scratch 设计可在段 codec 现有 framed/checksummed 发布边界后保存 format version、dimension、minima、scales、有序 point ID 与 code tuple。加载时先校验 collection fingerprint、code 范围、维度与 point-ID 集，再从受信 fitted state 构造 `ScalarQuantizedIndex`。测试可命名为 `test_quantized_codes_survive_segment_round_trip` 与 `test_corrupt_quantization_blob_rejects_open`。通过后可以修改行为矩阵“打开时重建 code”的声明，但仍不能证明 Qdrant 格式兼容。

## 小结

MiniQdrant 标量量化把每一维映射到 int8 网格，用解码后的近似向量收集过采样 Top-K，再为幸存者恢复精确浮点 score。该流水线教授候选/rescore 推理，但全扫描与 HNSW bypass 必须保持可见。第 9 章从查询时近似转向后台式状态替换：如何在不丢并发写、也不删除读者仍在使用的文件时，构建紧凑的索引段。
