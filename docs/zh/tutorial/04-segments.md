# 第 4 章 · 段生命周期

Segment 让向量数据库把短小、适合更新的写路径与稳定、面向搜索的数据分开。分离也
产生正确性问题：一个 ID 可能出现在多个 segment，新 delete 可能覆盖旧 vector，
optimizer 可能在查询仍读取文件时替换它们。MiniQdrant 用版本、tombstone、稳定
view 与引用计数 handle 显式表达这些状态。

## 学习目标

学完本章后，你能够：

1. 追踪 record 从 mutable segment 经 flush 到 immutable segment；
2. 用最高版本可见性解析重复 point ID；
3. 解释 tombstone 为何必须遮住所有旧 live image；
4. 描述 `CollectionView` 与 `SegmentHandle` 如何保护旧读者；以及
5. 区分 MiniQdrant segment 文件与 Qdrant 生产存储。

## Mutable 状态：每个 ID 一个最高镜像

`src/miniqdrant/segment/mutable.py::MutableSegment` 拥有从规范 point ID 到
`StoredPoint` 的内存字典及 payload index。`apply_upsert` 校验 point 和正版本；
若同 ID 已有相等或更新版本就忽略，否则替换记录并更新 payload index。

`MutableSegment.apply_delete` 使用相同 guard。它写入空 vector、空 payload、指定
版本且 `deleted=True` 的 tombstone，再从 payload index 移除 ID。`get` 与
`iter_live` 隐藏 tombstone；`iter_records` 则保留它们供持久化和版本解析。

Mutable segment 不是可随意丢弃的 cache，而是 manifest replay boundary 之后 WAL
记录的当前表示。本教学实现让它常驻内存；真实 Qdrant 有更丰富的 appendable
segment 存储。

## Flush：冻结 record 并发布 inventory

`Collection.flush` 同时持有 optimizer/update lock。若 mutable 为空就返回；否则
创建唯一 segment ID，用全部 mutable records 调用 `SegmentImage.build`，原子写入
image，发布含新增 ID 和当前 WAL 边界的 manifest，安装 `SegmentHandle`，再创建
新 mutable segment。

`src/miniqdrant/segment/codec.py::SegmentCodec.write_atomic` 写临时目录中的组件文件，
fsync 文件与目录，再 rename 到 segment root。文件分别保存 ID/vector、payload、
version、deleted ID、graph 与 payload-index metadata。虽然扩展名是 `.bin`，内容
仍是 framed canonical JSON，不是 Qdrant 的原生 mmap 格式。`SegmentCodec.read`
校验 checksum 并重建 `SegmentImage`。

`src/miniqdrant/segment/immutable.py::ImmutableSegment` 构造时应用
`_highest_versions`，所以单个 segment 每个 ID 至多一个最高镜像。它为 live point
构建 payload index，按需构建 HNSW 与可选 quantization index；发布后 API 不再
修改 records。

`indexed=False` 的 flush 产生 plain immutable segment；`indexed=True` 且有 live
point 时，image 与运行时 segment 含 HNSW。`flush_threshold_points` 不会自动触发
flush：policy 模块只供教学/测试，`Collection` 没有调用它。这与后台管理的生产
系统不同。

## Collection 范围可见性

不可变性本身不能决定谁可见。假设：

1. segment A 有版本 3 的 live point 7；
2. segment B 有版本 8 的新 vector；
3. mutable segment 有版本 11 的 delete tombstone。

唯一可见状态是“已删除”。`collection.py::_latest_records` 扫描所有发布 segment
及额外 mutable record，每个 ID 保留最高版本。`Collection.retrieve` 只返回未删除
latest record，`Collection.count` 也统计同一 latest map。

搜索还有陷阱：segment 内 Top-K 可能被旧 live 版本填满，随后被 collection 可见性
拒绝。请求候选前，`collection.py::_stale_live_count` 统计旧记录并增加本地 limit。
然后 `_search` 只接受 latest map 中版本相同且未删除的 candidate。正确性 buffer
需要每次搜索扫描 segment record；它是显式教学代码，不是生产性能声明。

Tombstone 即使不参与打分，也必须进入最高版本 map。如果 delete 只是从 mutable
移除，旧 immutable vector 就会复活。Tombstone 把“缺失”变成有序历史事实。

### 为什么本地 Top-K 需要可见性 buffer

假设用户请求两个结果。旧 segment 的前两名可能都是已在别处更新的 ID 的 stale
版本。若该 segment 只返回两个 candidate，collection 级检查会拒绝二者，也无法
找回其第三名但仍可见的 point。因此版本重叠时，每个 segment 只请求用户 limit
并不够。

MiniQdrant 计算 `_stale_live_count(segment, latest)`，请求
`limit + stale_count`，上限为 segment live count。最坏情况下，每个 stale
candidate 都排在每个 visible candidate 前，所以每个 stale live record 多一个
slot 足以暴露可能需要的可见点；全局 collector 仍只保留用户 limit。

这也解释 segment search 为什么返回 candidate version。若只匹配 ID，就可能接受
obsolete score，却投影 newest payload/vector，拼出来自不同历史镜像的结果。
`_search` 要求 `visible.version == candidate.version`，让 score、vector、payload
与 visibility 都指向同一 point image。

该解法刻意直接但昂贵。维护增量 ID tracker、让搜索绕过 obsolete version，可以
避免每个 view 重建 map 和扫描 stale count。MiniQdrant 选择可检查的正确性证明；
映射文档明确阻止读者把它误解成 Qdrant 的存储算法。

## 稳定 view 与安全回收

`Collection.search` 不直接搜索变化中的 segment list。`Collection.capture_view`
持 update lock，acquire 每个 `SegmentHandle`，把 mutable records 快照成临时
`ImmutableSegment`，构造 latest-version map，增加 active-view 计数并返回
`CollectionView`。

View 只搜索捕获的 tuple；context manager 退出时 release handle 并减少 active-view
计数。`Collection.close` 等待 active view，不能在飞行中读者下方关闭状态。

`src/miniqdrant/segment/references.py::SegmentHandle` 管理物理文件寿命。`acquire`
增加受锁保护的引用数；`retire` 标记 obsolete，但只有计数为零才删路径；最后一个
读者 `release` 时才删除 retired 路径。因此逻辑发布和物理回收是不同事件：

```text
发布新 manifest -> 新读者使用 replacement
旧 view 仍打开   -> 旧路径保留
旧 view 关闭     -> retired 路径可删除
```

这个进程内机制在优化期间保持稳定读者。Qdrant 的 segment holder/proxy segment
职责更广，还会调解更丰富的并发更新。

## 优化压缩历史

`Collection._optimize` 在 update lock 下捕获 source handle、records、mutable
records 与 WAL boundary，然后释放锁执行耗时的
`optimizer/optimizer.py::build_replacement`。Replacement 保留最高版本，并因完整
替换捕获的旧镜像而可以丢 tombstone。

长 build 期间新写仍可进入 mutable。发布阶段重新取得 update lock，保留版本严格
大于捕获 replay boundary 的 records，发布新 manifest，交换 handle/mutable 状态，
retire source handle。“短锁、长构建、协调晚写”不可缺少，否则已确认并发写会消失。

`merge()` 与 `vacuum()` 都调用同一个显式 `optimize()` 全量重写，只是便利名，不是
独立生产策略。第 9 章会完整研究策略与并发；这里关键是只有保持最新版本可见性后，
compaction 才能删除 obsolete image。

## MiniQdrant 对照真实 Qdrant

[映射表](../qdrant-mapping.md#运行时与存储)把 `MutableSegment`、
`ImmutableSegment`、版本解析、codec 文件和 `SegmentHandle` 标为有意简化。语义
骨架仍可迁移：appendable/stable 数据、版本化 point 可见性、tombstone、不可变
发布、稳定 read guard 和延迟回收。

真实 Qdrant 使用原生/mmap、RocksDB-backed 组件，更复杂的 segment holder/proxy、
后台 optimizer 和增量 ID tracking。MiniQdrant 为每个 view 扫描 records 重建
latest-ID map，把全部 segment 数据载入 Python 对象；它还会写 HNSW graph，却在
重开时重建运行时图，这个语义相反点也写在映射表。

参见[行为矩阵](../behavior-matrix.md#行为矩阵)的“mutable/immutable 生命周期”
“版本与 tombstone”“安全回收”，以及
[与 Qdrant 的差异](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)中的存储限制。

## 动手实验：观察历史安全消失

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as tmp:
    db = Database.open(Path(tmp) / "db")
    c = db.create_collection(
        "items", dimension=2, distance=Distance.DOT
    )
    c.upsert([
        Point(1, (1, 0), {"state": "v1"}),
        Point(2, (0, 1), {}),
    ])
    c.flush()
    c.upsert([Point(1, (2, 0), {"state": "v2"})])
    c.flush()
    c.delete([1])
    print("segments:", c.segment_statistics())
    print("retrieve-1:", c.retrieve([1]))
    print("search:", [
        h.id for h in c.search(
            SearchRequest((1, 0), limit=5, exact=True)
        ).hits
    ])
    c.flush()
    c.optimize()
    print("after-optimize:", c.segment_statistics())
    db.close()
PY
```

实测输出：

```text
segments: SegmentStatistics(segment_count=2, live_points=3, deleted_points=0)
retrieve-1: ()
search: [2]
after-optimize: SegmentStatistics(segment_count=1, live_points=1, deleted_points=0)
```

Tombstone flush 前，statistics 统计物理 immutable records：point 1 在两个 segment
都显得 live。逻辑 retrieve/search 仍服从较新的 mutable tombstone。Flush 与优化
后，一个紧凑 segment 只含 point 2；捕获的 tombstone 和所有旧 image 可一起丢弃。
本实验不使用 socket，已在本仓库实跑。

## 练习

### 理解题

1. 为什么物理 segment statistics 会与逻辑 collection count 不同？
2. 为什么 optimizer 只有在替换全部被覆盖旧 image 时才能丢 tombstone？

??? note "参考答案"

    1. Statistics 统计 immutable 文件中的 records，包括旧版本；collection count
       在 immutable/mutable 状态间解析最高版本并隐藏 tombstone。
    2. 若任何旧 segment 保留，移除最新 delete 事实就会让其 live vector 重现。
       完整替换覆盖集合后，才可用“省略”安全表达不存在。

### 动手题

3. 捕获 view 后 optimize，验证旧 segment 路径在 `view.close()` 前存在。验收：
   使用临时数据库，断言通过，不改 `src/`。
4. 同一 ID 跨三次 flush upsert 后 retrieve。验收：重开前后都返回最终 payload/
   version。

??? note "参考解法"

    第 3 题记录 `view.segment_paths`，调用 `c.optimize()`，断言旧路径仍存在；
    close view 后断言 retired 旧路径消失。至少创建两个 source segment。

    第 4 题依次使用 payload `v1`、`v2`、`v3`。最新 WAL sequence 必须获胜，重开
    不得改变结果。

## 小结

Mutable segment 保存最新内存 image 和 tombstone；flush 把它们冻结为带校验和的
immutable segment 并通过 manifest 发布。最高版本解析阻止旧数据复活，稳定 view
与引用计数 handle 则把逻辑替换和物理删除分开。第 5 章将在 segment 的 live
vector 上加入近似 HNSW 索引。
