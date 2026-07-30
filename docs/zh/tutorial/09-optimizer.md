# 第 9 章：优化器

> [English](../../tutorial/09-optimizer.md) · 中文

随着更新继续，段会积累旧点版本和 tombstone，索引也可能需要重建。优化器把捕获的记录集变成紧凑 replacement，但最难的不是排序或复制，而是在写者和读者继续运行时发布 replacement。MiniQdrant 用“短锁捕获—长时间构建—短锁发布”协议、晚写保留和引用计数回收教授这一机制。

## 学习目标

完成本章后，你应当能够：

1. 区分 merge、vacuum、index 三种策略决策；
2. 跟踪 `Collection._optimize()` 的捕获、构建、发布、回收阶段；
3. 解释 captured WAL boundary 如何保护已确认的晚写；
4. 解释 retired segment path 为何会活得比旧 `CollectionView` 更久；
5. 指出哪些看似优化器的配置与策略尚未接入运行时自动化。

## 1. 策略词汇与运行行为

`src/miniqdrant/optimizer/policy.py` 定义四个 `OptimizationKind`：`VACUUM`、`MERGE`、`INDEX`、`NONE`。`SegmentCandidate` 暴露 live count、deleted count、total count 与 deleted ratio。`choose_optimization()` 按顺序应用三条确定性规则：

1. vacuum 达到阈值且 deleted ratio 最大的候选；
2. 段过多时 merge 最小的两个；
3. index 最大且达到阈值的 plain 段，否则不做操作。

该函数适合教学与单元测试，但 **`Collection` 从不调用它**。`OptimizerConfig.flush_threshold_points` 也不会触发自动 flush。公开的 `Collection.merge()`、`vacuum()`、`optimize()` 都调用同一个 `optimize()`，实现会以 `drop_tombstones=True` 重写全部捕获段。

因此，三个公开动词目前并不选择三种不同算法。[`DIFFERENCES_FROM_QDRANT.md`](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md) 第 10 条记录了这一点，[Qdrant 映射](../qdrant-mapping.md)把它标为“语义相反”。

## 2. 构建一个 replacement image

`src/miniqdrant/optimizer/optimizer.py::select_latest` 扫描记录，为每个外部 point ID 保留最大版本。`build_replacement()` 随后用这些最新记录调用 `SegmentImage.build()`，按需去除 tombstone，复制 payload-index schema，并设置 `indexed=True`。

一个函数组合了三种概念操作：

- **merge：**多个源段镜像变成一个；
- **vacuum：**旧版本和（按要求）tombstone 消失；
- **rebuild/index：**在 replacement segment image 中构建 payload 结构、HNSW 与已配置量化。

replacement 此时尚不可见。`SegmentCodec.write_atomic()` 把它写入新 segment ID；只有之后发布 manifest，才会改变可见性。

## 3. 短锁、长构建、短锁

`src/miniqdrant/collection.py::Collection.optimize` 用 `_optimizer_lock` 串行化优化器，再调用 `_optimize()`。后者由两个临界区夹住一次无锁构建。

### 在 update lock 下捕获

第一个 `with self._update_lock` 会：

- acquire 当前全部 `SegmentHandle`；
- 把所有 immutable 与 mutable 记录复制到 `captured_records`；
- 记录 `replay_boundary = self._wal.last_sequence`。

离开该块后，写者可以 acquire `_update_lock`，在优化器构建期间追加更新的 WAL 记录。已 acquire 的 handle 则让源路径继续存活。

### 在 update lock 外构建

`build_replacement()` 与 `SegmentCodec.write_atomic()` 不持有 update lock。这就是“长构建”阶段。搜索可以捕获 view，写入也可以推进，而不必等待索引构建。测试可用 `src/miniqdrant/optimizer/failures.py::OptimizationGate` 确定性暂停该阶段。

### 在 update lock 下发布

优化器重新 acquire `_update_lock`，找出捕获源集中不存在的其他段，并构造新 `Manifest`。关键是它会保留：

```python
late_records = tuple(
    record
    for record in self._mutable.iter_records()
    if record.version > replay_boundary
)
```

replacement 已包含 boundary 及其之前的状态；严格更新的记录进入下一个 mutable segment。只有 replacement 与 late-record 状态同时存在后，`ManifestStore.publish()` 才让新 generation 成为 current。collection 随后交换 segment handle、manifest 和 mutable state，并 retire 旧 handle。

WAL sequence 同时担任 mutation version 与 capture boundary。若优化器只是清空 `_mutable`，长构建期间到达且已确认的写入可能在发布时消失。

## 4. 读者与延迟回收

`src/miniqdrant/collection.py::Collection.capture_view` 持有 `_update_lock` 时 acquire 全部当前 segment handle、快照 mutable 记录，并构造 latest-version map。即使优化发布新 generation，该 view 仍会搜索它捕获的那些段。

`src/miniqdrant/segment/references.py::SegmentHandle` 保护物理路径。`acquire()` 增加引用计数；`retire()` 将 handle 标为 obsolete，但只在引用为零时删除目录；`release()` 在最后一个旧读者关闭时执行延迟删除。

这拆开了 **逻辑退休** 与 **物理回收**。没有该机制，发布可能删除某个 in-flight view 即将读取的文件。它只是进程内机制，不是 epoch-based、分布式或 crash-recoverable 回收系统。

`Collection.close()` 还会等待 `_active_views`，而 `_optimizer_lock` 防止 close、flush、snapshot creation、optimization 跨越不兼容发布边界。特别是 `flush()` 先 acquire `_optimizer_lock` 再 acquire `_update_lock`，所以优化构建期间开始的 flush 会等待，而不是发布重叠状态。

## 5. 失败原子性

若 manifest 发布失败，`_optimize()` 删除尚未发布的 manifest 文件、`CURRENT.tmp` 与新 segment 目录。旧的内存 segment set 仍是 current。`tests/reliability/test_optimizer_publish.py::test_failed_optimizer_publish_keeps_old_segments_searchable` 在替换 `CURRENT` 前注入失败，并验证了这一点。

若发布成功，旧 handle 被 retire，最终删除。manifest pointer 是 commit record：没有 current manifest 的完整 replacement 目录不是 searchable state。

这里是本地文件系统原子性，不是跨机器事务。[行为矩阵](../behavior-matrix.md)把临时文件、fsync、`CURRENT` replacement 明确列为证据边界。

### 按发布阶段调试

若按“最后完成了哪个阶段”分类，优化器失败就容易推理得多。`sources_captured` 之前不存在 replacement state；构建期间，当前读写应继续看到旧 generation，失败只应删除未发布新目录；segment 写完但 `ManifestStore.publish()` 之前，新路径只是 orphan candidate，不是 current state；`CURRENT` 替换后，新 manifest 成为恢复权威，旧路径只有在 view 仍引用时才可继续存在。

排查“丢写”时，记录晚写 WAL sequence 与 captured `replay_boundary`。大于 boundary 的 sequence 必须出现在 `next_mutable`；小于或等于它的 sequence 必须已在 replacement image。路径意外缺失时，应检查 `SegmentHandle` 引用计数与 retirement 时机，而不是 planner 或 WAL。flush 阻塞时检查 `_optimizer_lock`：本实现中等待长构建是有意的，但普通 upsert 仍可通过 `_update_lock` 推进。

`OptimizationGate` 可以不用 sleep 就复现这些状态。测试等待命名事件 `sources_captured`，执行并发动作，再 release `finish_build`。这比寄希望于线程调度恰好落入脆弱窗口更可靠。

## 6. 与真实 Qdrant 对照

真实 Qdrant 在 `lib/collection/src/collection_manager/optimizers/` 等源码模块下拥有独立 vacuum、merge、indexing optimizer。optimizer worker 根据配置与段条件调度后台工作；proxy segment 和 change tracking 在 replacement 构建时协调更新；segment holder 管理更丰富的 searchable segment set。

MiniQdrant 保留并发课程，却简化了几乎所有规模维度：

- 优化必须显式调用，从不自动调度；
- 所有公开 optimizer 动词执行同一种全量重写；
- policy 函数在运行时是 test-only dead code；
- 一个进程和一个 writer 拥有 collection；
- 晚记录通过简单 WAL-boundary 比较恢复；
- 引用计数只保护当前进程中的读者；
- replacement 总是构建 indexed segment，而不是选择聚焦优化操作。

参见[行为矩阵](../behavior-matrix.md)的 online optimization 与 safe reclamation 行、[完整差异文档](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)的 optimizer 差异，以及 [Qdrant 映射](../qdrant-mapping.md)中的 `build_replacement`、`choose_optimization`、`_optimize` 行。

## 7. 动手实验

### 实验 A：压缩两个段

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python -m miniqdrant.labs.segments
```

实测输出：

```text
Segments lab: two upsert+flush rounds followed by optimize
Segments before optimize: 2
Segments after optimize: 1

Interpretation:
- each flush publishes an immutable segment, so the count first reaches two.
- optimize compacts those segments into one while preserving collection contents.
```

这证明可见压缩效果，本身不证明并发不变量。

### 实验 B：运行 merge、vacuum、并发与发布失败

```bash
UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/storage/test_merge.py tests/storage/test_vacuum.py tests/concurrency/test_online_optimize.py tests/reliability/test_optimizer_publish.py
```

实测输出：

```text
......                                                                   [100%]
6 passed in 2.28s
```

六个测试覆盖最新版本保留、tombstone 删除、构建期间写入、flush 串行化、活得比 replacement 更久的旧读者，以及失败的 manifest 发布。

## 8. 练习

1. **理解题：**晚写判断为何是 `version > replay_boundary`，而不是 `>=`？
2. **理解题：**优化器为何能立即 retire handle，却不一定能立即删除其路径？
3. **动手并发设计题：**在 scratch diff 中，让 `merge()` 与 `vacuum()` 传入显式 `drop_tombstones` 意图，同时保留一个共享 `_optimize` 发布协议。不要修改 `src/`。验收标准：命名能证明 merge 保留所需 tombstone、vacuum 删除安全 tombstone、两种模式下晚写获胜、旧 view 保持可读的测试。

??? note "参考答案"

    1. captured boundary 上的记录已包含于 `captured_records`，也就包含于 replacement image。再次保留会复制状态；只有严格更新的版本是在捕获快照之后到达的。
    2. Retirement 让未来 generation 不再使用该段；已有 view 已 acquire 旧 handle，必须安全完成。`release()` 只在最后引用归零后删除路径。
    3. 清晰的 scratch 设计为 `_optimize()` 与 `build_replacement()` 调用添加 `drop_tombstones` 参数，`vacuum()` 传 true，`merge()` 使用已写明的安全规则；manifest、boundary、late-record、handle-retirement 代码保持共享。建议验收测试：`test_merge_tombstone_prevents_resurrection`、`test_vacuum_drops_tombstone_after_full_capture`、参数化 `test_late_write_wins_by_mode`、`test_old_view_survives_replacement_by_mode`。命令：`UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run pytest -q tests/storage tests/concurrency/test_online_optimize.py`。

## 小结

MiniQdrant 优化是原子状态替换协议：短锁下捕获有版本的源集合，不持 update lock 构建紧凑索引镜像，保留 boundary 之后的写，发布一个 manifest，并延迟删除文件直到旧 view 释放 handle。它的 policy-shaped 模块不是运行时自动化，公开 optimizer 动词也共享一次全量重写。第 10 章会在更大边界复用同一发布纪律：把整个 collection 打包成带 checksum 的 snapshot，在 staging 验证，并在失败时不替换健康 target。
