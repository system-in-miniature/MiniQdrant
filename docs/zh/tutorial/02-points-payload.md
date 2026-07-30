# 第 2 章 · 点与负载

向量数据库存储的不只是向量。它还需要每个对象的稳定身份、用于过滤与投影的
元数据、定义相似度的度量，以及决定哪个版本可见的更新规则。MiniQdrant 把这些
关注点集中在一个刻意缩小的值模型中。现在理解它可以避免后续混淆：WAL 帧、
segment、HNSW 节点、过滤器和 optimizer 重写都必须保持同一个逻辑 point。

## 学习目标

学完本章后，你能够：

1. 区分 `Point`、`StoredPoint`、`SearchRequest` 与 `SearchHit`；
2. 解释 WAL 追加前的校验和余弦归一化；
3. 计算 cosine、dot 与 MiniQdrant Euclid 分数；
4. 描述 payload 完整替换、浅合并和键删除；以及
5. 找出 MiniQdrant 值/payload 模型与 Qdrant 的差异。

## 进入系统的 point

`src/miniqdrant/models.py::Point` 是调用者面对的变更值：

```python
@dataclass(frozen=True, slots=True)
class Point:
    id: PointId
    vector: Vector
    payload: FrozenJsonObject = field(default_factory=lambda: freeze_json_object({}))
```

冻结 dataclass 阻止字段被重新绑定，
`src/miniqdrant/json_values.py::freeze_json_object` 则递归地把 payload 转为不可变
JSON 形状的值。ID 由 `src/miniqdrant/ids.py::canonicalize_point_id` 规范化；
MiniQdrant 接受非负 64 位整数和 UUID。限制让排序、序列化和相等性只有一种稳定
含义。

`models.py::validate_point` 把 `Point` 转为 `StoredPoint`。后者增加 `version` 和
`deleted`，这是跨 segment 可见性所需的两个字段。校验时版本先是零，变更路径在
`MutableSegment.apply_upsert` 中用正 WAL 序列替换它。删除沿用相同 ID 和版本
模型，但通过 `MutableSegment.apply_delete` 存储空向量、空 payload 且
`deleted=True` 的 tombstone。

这种分离很有用：调用者描述期望状态，存储记录描述有序历史镜像。`Point` 不能
自己选择版本，否则会破坏 WAL 提供的单进程单调顺序。

### 向量校验与归一化

`models.py::validate_vector` 先把序列物化为 float，再检查维度、拒绝布尔分量，并
要求每个分量有限。`Collection.upsert` 会在更新锁追加批次前对全部点执行校验。
因此一个无效点会在持久历史扩展前拒绝整个批次。

这个顺序提供校验原子性，而不是通用事务。十点批次要么通过预检并成为一个
`UpsertOperation`，要么不追加任何 frame。越过 WAL 持久边界后的故障语义不同：
即使调用者观察到注入的进程故障，恢复仍可能 replay 已记录操作。第 3 章会严格
区分 append 前拒绝、持久确认与 replay。

对于 `Distance.COSINE`，`validate_point` 调用
`models.py::normalize_cosine`。零向量没有方向，其余弦相似度未定义，因此会抛出
`ValueError`。有效向量除以 Euclid 范数，存储归一化 tuple。查询向量在
`MutableSegment.search` 和 `ImmutableSegment.search` 中校验与归一化，所以
`metrics.py::score` 可以直接用点积计算 cosine。

对于 `Distance.DOT`，不会归一化，模长会影响分数：针对 `(1, 0)` 查询，
`(2, 0)` 的分数是 `(1, 0)` 的两倍。对于 `Distance.EUCLID`，
`metrics.py::score` 返回 `-sum((left-right)**2)`。相同向量得负零，相距 5 的
向量得 `-25`，越高仍表示越近。这是排序分数，不是真实 Qdrant 常见的正距离展示。

## Payload：带显式变更的不可变 JSON

Payload 把语义元数据连接到向量。MiniQdrant 接受 JSON object：字符串键，值可以
是 null、boolean、integer、有限 float、string、array 或嵌套 object。冻结操作
避免调用者在 upsert 后修改原字典，使存储状态在没有 WAL 记录时偷偷变化。
需要转换或序列化时，`thaw_json` 会生成新的普通对象。

`Collection.replace_payload` 完整替换每个已存在目标点的 payload。
`Collection.merge_payload` 做等价于 `{**current, **patch}` 的顶层浅合并，不递归
合并嵌套字典。`Collection.delete_payload_keys` 删除指定顶层键。三者都委托给
`Collection._mutate_payload`，其步骤是：

1. 规范化并去重 ID；
2. 解析最新可见记录；
3. 跳过缺失或已删除的点；
4. 构造向量不变的完整新 `Point` 镜像；
5. 校验镜像；然后
6. 追加一个包含这些完整镜像的 `UpsertOperation`。

所以 payload 变更在 WAL 中不是特殊的局部记录，而是 point 的新完整版本。如果
目标中没有任何 live point，方法返回 `None` 且不追加记录；否则所有被修改点共用
返回的 WAL 序列。

### 跨表示的身份与相等性

Point identity 刻意独立于 vector/payload 相等性。同一 ID 的 upsert 表示“发布更新
完整镜像”，即使新 vector 恰好等于旧 vector。两个不同 ID 即使其他字段完全相同，
仍是两个 Top-K candidate。因此 version map、tombstone、payload index 与 HNSW
node 都按规范 ID 索引，而不是按对象 hash 或 vector bytes。

整数和 UUID ID 共用公开类型，却需要确定的混合排序。
`src/miniqdrant/ids.py::point_id_sort_key` 提供带 tag 的 key，`point_id_bytes` 为
确定性 HNSW level 提供稳定 bytes。这些 helper 保持 tie-breaking 与 graph
construction 可复现，但不声称两类 ID 可直接数值比较。

冻结 payload 的相等性是结构化的：object key 顺序不产生新含义，array 顺序则会。
JSON 校验拒绝不支持的 Python object 和非有限 float，因为规范持久化与 filter
comparison 都不能依赖临时表示。Payload 变更的 thaw/freeze 循环也阻止 transform
保留调用者拥有的 mutable alias。

这些规则会成为横切不变量：WAL encoding 必须保持 ID kind 与 JSON value，segment
codec 必须恢复它们，filter 必须检查同一结构，snapshot 必须 checksum 最终文件。
因此值模型中看似很小的放宽，也需要整个数据库协调修改。

`SearchHit` 中的 payload 是可选的。`SearchRequest.with_payload` 默认为真，
`with_vector` 默认为假。`Collection._project_hit` 只在可见性与 Top-K 选择完成后
应用投影开关。关闭 payload 输出只改变结果物化，不改变过滤、排名或存储数据。

## SearchRequest 是语义合同

`models.py::SearchRequest` 有意把部分校验留给执行所有者。
`collection.py::_search` 要求正 limit、检查过滤器确实是 `Filter`，并拒绝非有限
分数阈值；segment 搜索按 collection 维度校验向量。分数阈值在旧版本排除之后
应用，且所有距离都遵循“越高越好”。

`SearchHit` 包含 ID、score 和可选 payload/vector。`SearchResult` 包含不可变
hits tuple 与 plan 字符串 tuple。平分时顺序仍然确定：
`src/miniqdrant/topk.py::TopK` 按规范 point ID 排序。确定性让测试与教材可复现，
但不表示近似索引会与生产 Qdrant 访问相同图节点。

## MiniQdrant 对照真实 Qdrant

[行为矩阵](../behavior-matrix.md#行为矩阵)把“固定 collection schema”“精确确定性
Top-K”和“payload 变更”列成不同声明。正确打分不能证明 payload 与 Qdrant 兼容，
持久 payload 更新也不能证明支持 Qdrant 的向量类型。

真实 Qdrant 支持 named dense vector、sparse vector、multivector、更丰富的 payload
索引/条件以及 point 操作的网络 schema。MiniQdrant 每个点只有一个固定维度稠密
向量；其嵌套字段遍历和后续过滤规则是教学子集。Payload 合并与删除是顶层浅操作，
不构成 Qdrant API 兼容。参见
[`models.py` 与 `metrics.py` 映射](../qdrant-mapping.md#查询与索引)和
[与 Qdrant 的差异](https://github.com/system-in-miniature/mini-qdrant/blob/main/DIFFERENCES_FROM_QDRANT.md)。

Euclid 差异尤其需要谨慎。MiniQdrant 报告负平方距离，以复用“越高越好”的 Top-K
与阈值逻辑。阈值 `-9` 表示“平方距离不超过 9”，而不是“正距离至少为 -9”。不能
不经换算就把分数阈值复制到 Qdrant 部署。

MiniQdrant 还为 payload 编辑存储完整 point 镜像。生产 Qdrant 有更丰富的更新 API
和内部存储路径。共同教训是身份、向量、payload 与顺序必须产生一个无歧义可见点；
具体网络与存储表示则有意不同。

## 动手实验：检查值合同

在仓库根目录运行：

```bash
export UV_CACHE_DIR=/tmp/miniqdrant-uv-cache
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from miniqdrant import Database, Distance, Point, SearchRequest

with TemporaryDirectory() as tmp:
    db = Database.open(Path(tmp) / "db")
    c = db.create_collection(
        "vectors", dimension=2, distance=Distance.EUCLID
    )
    c.upsert([
        Point(1, (0, 0), {"tag": "old"}),
        Point(2, (3, 4), {"tag": "far"}),
    ])
    c.merge_payload([1], {"tag": "new", "year": 2026})
    print("point-1:", dict(c.retrieve([1])[0].payload))
    print("scores:", [
        (h.id, h.score)
        for h in c.search(
            SearchRequest((0, 0), limit=2, exact=True)
        ).hits
    ])
    try:
        c.upsert([Point(3, (1,), {})])
    except ValueError as error:
        print("validation:", error)
    db.close()
PY
```

实测输出：

```text
point-1: {'tag': 'new', 'year': 2026}
scores: [(1, -0.0), (2, -25.0)]
validation: vector dimension must be 2, received 1
```

浅合并覆盖 `tag` 并增加 `year`，但内部会创建完整的新 point 版本。点 1 与查询
相同；点 2 构成 3-4-5 三角形，所以负平方分数分别为 `-0.0` 和 `-25.0`。维度
校验在无效批次进入 WAL 前报告 collection 合同。本 direct 实验不使用 socket，
已在当前仓库实跑。

## 练习

### 理解题

1. 为什么 payload 冻结必须发生在 WAL 追加前？
2. Euclid 打分下，平方距离 4、10、16 中哪些通过 `-10` 阈值？

??? note "参考答案"

    1. WAL 和 stored point 必须描述稳定值。若调用者字典仍可变，状态就能在没有
       版本或持久操作时变化，从而破坏恢复和可见性。
    2. 距离 4 和 10 得分 `-4`、`-10`，都至少为 `-10`；距离 16 得 `-16`，
       被拒绝。

### 动手题

3. 在临时脚本中替换点 1 的 payload，再浅合并一个嵌套 object 并打印。验收：
   证明嵌套 object 被替换而不是递归合并；不要修改 `src/`。
4. 比较同时包含 `(1, 0)` 与 `(2, 0)` 的 cosine、dot collection。验收：断言
   cosine 分数相等而 dot 分数不同，脚本退出码为 0。

??? note "参考解法"

    第 3 题先用 `{"meta": {"a": 1, "b": 2}}`，再调用
    `merge_payload([1], {"meta": {"a": 9}})`。结果应是
    `{"meta": {"a": 9}}`，浅合并不会保留键 `b`。

    第 4 题必须创建两个 collection，因为 distance 对 collection 固定。都用
    `(1, 0)` 搜索。Cosine 把两个存储向量归一化成相同方向；dot 保留模长，分数
    分别为 1 和 2。

## 小结

逻辑 point 是经过校验的 ID、向量和不可变 JSON payload；存储形式增加 WAL 派生
版本和 tombstone 状态。Cosine 归一化，dot 保留模长，Euclid 暴露负平方距离，
使一个确定性 Top-K 能为所有度量排序。Payload 编辑会成为完整的新 point 版本。
第 3 章将跟随这些版本进入带校验和的 WAL 帧、不可变 manifest 与重启 replay。
