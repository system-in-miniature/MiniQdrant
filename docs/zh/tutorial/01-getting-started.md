# 第 1 章 · 认识 MiniQdrant

MiniQdrant 是一个为了便于阅读而构建的小型、direct-first 向量数据库。它既不是
Qdrant 的 Python 客户端，也不是仅仅缩小配置的生产服务器。它的目标是保留单节点
向量数据库的关键机制：你可以把一次写入从 API 调用一直追踪到持久存储，也可以把
一次查询从查询向量一直追踪到排序正确、版本正确的结果。

## 学习目标

学完本章后，你能够：

1. 通过直接 Python API 创建并重新打开 collection；
2. 解释 database、collection、point、payload、distance 和 search request 的职责；
3. 预判余弦分数为何会按实验中的顺序排列两个向量；
4. 找到负责 collection 生命周期、校验和搜索的源码；以及
5. 说出 MiniQdrant 与真实 Qdrant 的三个重要边界。

## 为什么研究教学内核？

生产向量数据库必须同时解决网络 API、认证、分布式元数据、副本、分片、后台任务、
存储引擎、遥测、兼容性和滚动升级等问题。这些能力都很重要，却也会遮住本书真正
想研究的少数机制。MiniQdrant 保留可辨认的数据路径，并移除大部分部署机械。

根目录 `README.md` 给出了最短的系统地图：

```text
已校验变更 -> WAL -> mutable segment
                            |
                            v flush
查询 -> 逐 segment 搜索 -> 版本解析 -> 全局 Top-K
```

这张图不只是文档。在 `src/miniqdrant/database.py` 中，
`Database.create_collection` 校验名字、冻结 `CollectionConfig`、创建 collection
目录并注册活跃的 `Collection`。`Database.open` 扫描 collection 目录，并把恢复
委托给 `Collection.open`。因此 database 对象拥有目录与生命周期，而 collection
拥有向量、变更、segment 和搜索。

公开值模型位于 `src/miniqdrant/models.py`。`Point` 包含整数或 UUID 标识、稠密
向量和 JSON payload。`SearchRequest` 包含查询向量、结果上限、可选过滤器和分数
阈值、投影开关、精确模式开关以及可选 HNSW 搜索宽度。`SearchResult` 返回命中项
以及每个 segment 的计划名。最后这个字段是教学观测面：实验可以借它暴露实际走了
哪条搜索路径。

### 创建操作固定向量空间

`Database.create_collection` 用 `dimension` 和 `distance` 构造
`CollectionConfig`。`src/miniqdrant/config.py` 中的
`CollectionConfig.__post_init__` 拒绝非正维度，并把字符串距离规范为 `Distance`
枚举。配置一旦持久化，就不是每个点都可随意选择的建议。
`src/miniqdrant/models.py::validate_vector` 会拒绝错误维度、布尔值和非有限分量；
`validate_point` 还会规范化 ID、冻结 payload，并归一化余弦向量。

余弦归一化在写路径的 `models.py::validate_point` 中完成，而不是每次搜索都反复
归一化存储向量；查询向量则在读路径归一化。点积保留原始向量模长。
`src/miniqdrant/metrics.py::score` 用负平方距离表示 Euclid，因而所有度量都能遵循
“分数越大越好”的统一约定。第 2 章会详细研究这个值模型。

### 一次写入与一次查询

`src/miniqdrant/collection.py` 中的 `Collection.upsert` 先把输入批次物化，在写入
任何数据前校验全部点，然后获取更新锁、追加一个 WAL 操作，最后把记录应用到
mutable segment。返回值是 WAL 序列号。在默认持久性策略下，内存变更可见前，WAL
帧已经越过本地 `fsync` 边界。

`Collection.search` 捕获稳定的 `CollectionView`，再调用其 `search`。内部
`collection.py::_search` 向每个非空 segment 请求候选，排除旧版本和 tombstone，
应用分数阈值，并把唯一的可见 ID 交给 `TopK`。所以即便第一次微型查询，也使用与
跨多个 immutable segment 查询相同的高层边界。

这里没有 HTTP 请求、序列化往返或客户端/服务器进程边界，这就是 API 被称为
direct-first 的原因。薄 CLI 只是同一批对象上的另一个适配器，不是协议服务器。

### 如何阅读仓库

不要按字母顺序读，而要按所有权和数据流读。从 `Database.create_collection`、
`Collection.upsert` 或 `Collection.search` 这样的公开方法开始，每次只跟随交给
下一个所有者的值。第一次写入的路径是 `Point` 校验、`Wal.append`、
`Collection._apply_wal_record` 与 `MutableSegment.apply_upsert`；第一次读取则是
`Collection.capture_view`、`CollectionView.search`、`collection.py::_search`、
segment search 与 `TopK`。

在每个边界问四个问题：谁拥有状态、检查什么不变量、发布前什么可能失败、什么证据
能观察结果？这样可以避免常见误读——把类名当作生产行为的证明。例如，存在
`HnswIndex` 只能证明实现了一种 graph type；只有 search 代码、测试和明确差异才能
说明 traversal 是否与 Qdrant 一致。

读完机制后再把测试当作可执行规格，而不是用测试替代机制。
`tests/contract/` 关注公开状态转换，`tests/storage/` 关注编码结构，
`tests/reliability/` 关注崩溃边界，`tests/acceptance/` 关注端到端结果。
[行为矩阵](../behavior-matrix.md)把保留声明连接到这些测试。本章的 direct 小实验是
第一次端到端 trace；后续章节会缩小 fixture，每次暴露一个内部机制。
阅读时可以画一张所有者与发布边界草图；到第 10 章，它会变成整个数据库的紧凑
心智模型。

### 生命周期也是正确性的一部分

即使临时目录马上会消失，示例仍显式关闭 `Database`，这不是装饰。
`Database.close` 先把 catalogue 标成 closed，在 catalogue lock 下移除 live
collection 引用，再关闭每个 collection。`Collection.close` 与 optimization、
active view 协调，flush WAL 并关闭 stream。
`src/miniqdrant/lifecycle.py::Lifecycle._ensure_open` 让后续操作明确失败，而不是触碰
半关闭状态。

`Database` 没有 context manager，因此调用者拥有这个边界。长程序应以
`try/finally` 包住 database lifetime，不能依赖解释器退出建立经过测试的持久点。
相反，`Database.simulate_process_loss` 专为恢复测试绕过正常 flush 路径而存在，
它不是更快的 clean close 同义词。

Collection 创建也有 filesystem lifetime。`Collection.create` 写带校验和的
collection metadata、创建 WAL、发布初始空 manifest，然后才返回对象。
`Database.drop_collection` 在删除目录前关闭 live collection。该过程依赖文档化的
single-writer 边界；另一个进程同时持有同一路径不在安全合同内。把对象寿命、持久
寿命和文件系统寿命分别思考，会让后续稳定 view 与 snapshot 更容易理解。

## MiniQdrant 对照真实 Qdrant

真实 Qdrant 提供 REST 和 gRPC API，运行 collection 与 shard 服务，协调副本，
并使用生产级存储和索引组件。MiniQdrant 的 `Database` 是进程内 collection
目录；`Collection` 合并了 Qdrant 中分散在 collection、shard、replica-set、
update 和 search 服务里的职责。参见
[`Database` 与 `Collection` 映射](../qdrant-mapping.md#运行时与存储)。

首先要记住三个差异：

- MiniQdrant 每个 collection 只有一个固定稠密向量 schema；没有 named vector、
  sparse vector 或 multivector。
- 它提供 Python API 与 CLI，但没有兼容 Qdrant 的 REST 或 gRPC 服务器。直接调用
  成功只能证明本地语义，不能证明线上协议兼容。
- 它是单进程、单写者参考运行时。“持久”指选定的本地 WAL 策略，不表示副本确认
  或分布式一致性。

这些是显式范围决策，不是隐藏遗漏。[`固定 collection schema`](../behavior-matrix.md#行为矩阵)
和[`薄适配器与实验`](../behavior-matrix.md#行为矩阵)条目列出了相应测试，
[与 Qdrant 的差异](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)则列出不支持的部署面。本书始终
用这些页面区分“保留下来的不变量”和“生产系统能力”。

## 动手实验：第一次对话

在仓库根目录运行。临时目录使实验可重复，也不会留下数据库。

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as tmp:
    db = Database.open(Path(tmp) / "db")
    c = db.create_collection(
        "books", dimension=3, distance=Distance.COSINE
    )
    sequence = c.upsert([
        Point(1, (1, 0, 0), {"title": "Systems"}),
        Point(2, (0, 1, 0), {"title": "Cinema"}),
    ])
    result = c.search(
        SearchRequest((1, 0, 0), limit=2, exact=True)
    )
    print("sequence:", sequence)
    print("hits:", [
        (h.id, round(h.score, 3), h.payload["title"])
        for h in result.hits
    ])
    print("plan:", result.plan)
    db.close()
PY
```

实测输出：

```text
sequence: 1
hits: [(1, 1.0, 'Systems'), (2, 0.0, 'Cinema')]
plan: ('exact_full_scan',)
```

一次调用产生一个 WAL 序列。第一个已存单位向量与归一化查询相同，所以余弦分数
为 `1.0`；第二个与之正交，分数为 `0.0`。这里只有一个内存 segment 视图，精确
模式选择了 `exact_full_scan`。由于 `SearchRequest.with_payload` 默认为真，结果
包含 payload。

这个实验不使用 socket，已在本仓库实跑。它经过真正的直接适配器、校验、WAL
追加、mutable segment、精确打分、版本解析和 Top-K 路径；它没有测试 Qdrant
客户端或服务器。

## 练习

### 理解题

1. 为什么 `Database` 拥有命名 collection，而 `Collection` 拥有搜索？
2. 用户通常期待正距离，为什么负平方 Euclid 仍然有用？

??? note "参考答案"

    1. `Database` 是目录和生命周期边界。一个 `Collection` 拥有一个固定向量
       schema 及其写入、segment、恢复和查询状态。分开后，重开和删除无需了解
       向量搜索内部实现。
    2. 三种度量可以共用“越大越好”的 Top-K 实现，平方还避免开方。代价是面向
       用户的分数和阈值解释不同，因此必须明确声明。

### 动手题

3. 不改 `src/`，把实验复制到 `/tmp/ch01.py`，把查询改成 `(0, 1, 0)`，并断言
   点 2 排第一。验收：运行
   `UV_CACHE_DIR=/tmp/miniqdrant-uv-cache uv run python /tmp/ch01.py` 退出码为 0，
   且先打印点 2。
4. 在临时脚本中加入故意错误的三维度。验收：捕获 `ValueError` 并打印原始消息，
   collection 的 count 仍必须是 2。

??? note "参考解法"

    第 3 题使用 `SearchRequest((0, 1, 0), limit=2, exact=True)`，再写
    `assert result.hits[0].id == 2`。

    第 4 题在 `try/except ValueError` 中调用
    `c.upsert([Point(3, (1, 2), {})])`，再断言 `c.count() == 2`。校验发生在
    `Wal.append` 前，错误批次不会部分进入 collection。

## 小结

MiniQdrant 保留了向量数据库的教学主干：校验变更、写日志、应用到 mutable
segment、搜索 segment 内候选、解析版本、合并确定性全局 Top-K。direct API
让这条主干不受网络栈遮挡，而映射与差异文档让生产能力声明保持诚实。下一章将放大
point、payload、距离度量，以及之后所有存储与索引机制都必须保持的精确语义。
