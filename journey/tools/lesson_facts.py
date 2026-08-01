"""Reviewed bilingual mechanism facts for MiniQdrant's fifteen Stages."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LessonFacts:
    title_en: str
    title_zh: str
    problem_en: str
    problem_zh: str
    failure_en: str
    failure_zh: str
    concepts_en: str
    concepts_zh: str
    runtime_en: str
    runtime_zh: str
    statement_en: str
    statement_zh: str


@dataclass(frozen=True, slots=True)
class Seed:
    title_en: str
    title_zh: str
    need_en: str
    need_zh: str
    invariant_en: str
    invariant_zh: str


SEEDS = (
    Seed("Domain contracts", "领域契约", "points, vectors, payload values, ids, distance modes, and collection configuration need closed validation before storage or search can reason about them", "Point、Vector、Payload Value、ID、Distance Mode 与 Collection Configuration 必须先形成封闭校验，存储和搜索才能可靠推理", "accepted values are owned and canonical, dimensions remain fixed, and unsupported types fail at the public boundary", "被接受的值由系统拥有且具有规范表示，维度保持固定，不支持的类型在公共边界失败"),
    Seed("Distance scoring and top-k", "距离评分与 Top-k", "exact search needs one deterministic meaning for cosine, dot, Euclidean distance, ties, limits, and non-finite components", "精确搜索需要统一定义 Cosine、Dot、Euclidean Distance、Tie、Limit 与非有限分量", "all metrics expose a common higher-is-better score and top-k ordering is stable under equal scores", "所有 Metric 暴露统一的分数越高越好语义，相同分数下 Top-k 顺序保持稳定"),
    Seed("Structured payload filters", "结构化 Payload 过滤", "payload conditions need an explicit recursive AST instead of accidental Python truthiness and dictionary comparison", "Payload 条件需要显式递归 AST，不能依赖偶然的 Python Truthiness 与字典比较", "every condition has declared missing-field and type behavior, and boolean composition remains deterministic", "每个 Condition 都明确缺失字段和类型行为，Boolean 组合保持确定"),
    Seed("Exact mutable segments", "精确可变 Segment", "new points need an owned in-memory segment that coordinates replacement, deletion, filtering, and exact vector retrieval", "新 Point 需要受控的内存 Segment，统一协调替换、删除、过滤与精确向量检索", "a point id has at most one live record and every search result is rederived from the segment's current owned state", "一个 Point ID 至多对应一条活记录，每个搜索结果都从 Segment 当前受控状态重新推导"),
    Seed("Collection operations", "Collection 操作闭环", "segments and indexes do not yet form a public database until one collection owns lifecycle, validation, upsert, delete, retrieve, and search", "Segment 与 Index 只有由一个 Collection 统一拥有生命周期、校验、Upsert、Delete、Retrieve 与 Search 后才构成公共数据库", "public mutations validate completely before publication and reads never expose caller-owned mutable payload state", "公共修改在发布前完成全部校验，读取绝不暴露调用方可变 Payload 状态"),
    Seed("Filter-aware query planning", "过滤感知查询规划", "exact scans, payload indexes, and filters need a planner that can choose candidates without changing result semantics", "精确扫描、Payload Index 与 Filter 需要 Planner 选择 Candidate，同时不得改变结果语义", "plans may narrow candidates but execution always preserves filter and exact-score parity with the reference scan", "Plan 可以缩小 Candidate，但执行始终保持与参考扫描相同的 Filter 和精确分数语义"),
    Seed("Deterministic HNSW search", "确定性 HNSW 搜索", "approximate nearest-neighbor retrieval needs explicit graph layers, neighbor bounds, entry points, traversal budgets, and tie rules", "近似最近邻检索需要显式 Graph Layer、Neighbor Bound、Entry Point、Traversal Budget 与 Tie Rule", "graph construction and search are reproducible and never return deleted, duplicate, or out-of-scope candidates", "Graph 构建与搜索可复现，绝不返回已删除、重复或越界 Candidate"),
    Seed("Versioned immutable segments", "版本化不可变 Segment", "flushed data needs immutable segment files and versioned references while new writes continue in a mutable owner", "Flush 后的数据需要不可变 Segment File 与版本化 Reference，同时新写入继续进入 Mutable Owner", "readers observe a stable published segment set and merge results by current point identity rather than stale copies", "Reader 观察稳定发布的 Segment Set，并按当前 Point Identity 合并结果而不是保留陈旧副本"),
    Seed("Framed write-ahead logging", "分帧预写日志", "acknowledged operations need ordered, checksummed frames whose valid prefix is recoverable after truncation or tail corruption", "已确认操作需要有序、带校验和的 Frame，使截断或尾部损坏后仍能恢复有效前缀", "a mutation is publishable only after its complete frame is durable, and recovery never skips corruption to invent later history", "Mutation 只有完整 Frame 持久后才能发布，恢复绝不跳过损坏去虚构后续历史"),
    Seed("Manifest publication and recovery", "Manifest 发布与恢复", "segment files, collection metadata, manifest generations, and WAL replay need one restart protocol with an atomic publication point", "Segment File、Collection Metadata、Manifest Generation 与 WAL Replay 需要统一的重启协议和原子发布点", "restart opens one complete manifest generation then replays only the ordered WAL suffix not already represented by it", "重启只打开一个完整 Manifest Generation，再回放其中尚未表示的有序 WAL 后缀"),
    Seed("Online segment optimization", "在线 Segment 优化", "merge, vacuum, and replacement must reclaim obsolete segment state without blocking readers or publishing partial output", "Merge、Vacuum 与 Replacement 必须在不阻塞 Reader、不发布部分输出的前提下回收过时 Segment 状态", "optimization builds privately, validates its inputs are still current, then atomically swaps references while old readers finish", "Optimization 私下构建，确认输入仍是当前版本，再原子替换 Reference，同时允许旧 Reader 完成"),
    Seed("Quantized candidate rescoring", "量化候选精排", "compressed vectors can accelerate candidate generation only if bounded approximation and exact final scoring are kept distinct", "压缩 Vector 只有在区分有界近似 Candidate Generation 与最终精确评分时才能安全加速", "quantization may change candidate cost but returned scores and ordering come from exact vectors after rescoring", "Quantization 可以改变候选成本，但返回分数与顺序来自精确 Vector 的再次评分"),
    Seed("Atomic snapshot and restore", "原子 Snapshot 与 Restore", "portable backups need a self-consistent cut of metadata, manifests, segments, and WAL that restores without aliasing the live collection", "可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份", "a snapshot contains one declared generation and restore either publishes the whole verified copy or leaves the destination unchanged", "Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变"),
    Seed("Concurrency and acceptance closure", "并发与验收闭环", "flush and optimize can race, while cross-segment merge can surface the same point id more than once unless lifecycle ownership is tightened", "Flush 与 Optimize 可能竞争，跨 Segment Merge 也可能重复暴露同一 Point ID，必须收紧生命周期所有权", "lifecycle mutations serialize at publication and merged search emits only the newest live identity for each point", "生命周期修改在发布点串行化，合并搜索对每个 Point 只输出最新活身份"),
    Seed("Executable vector-search labs", "可执行向量搜索实验", "isolated contracts do not show whether learners can reproduce filtering, recall, recovery, segments, and plan choice through public APIs", "孤立契约无法说明学习者能否仅通过公共 API 复现 Filtering、Recall、Recovery、Segment 与 Plan Choice", "each fresh-process lab exposes one mechanism through stable observable output without private fixtures or pre-existing state", "每个新进程 Lab 都通过稳定可观察输出展示一个机制，不依赖私有 Fixture 或既有状态"),
)


def _facts(seed: Seed) -> LessonFacts:
    return LessonFacts(
        seed.title_en,
        seed.title_zh,
        seed.need_en.capitalize() + ".",
        seed.need_zh + "。",
        f"The focused tests force {seed.title_en.lower()} through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.",
        f"聚焦测试让{seed.title_zh}经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。",
        f"The central mechanism is {seed.title_en.lower()}. {seed.need_en.capitalize()}.",
        f"核心机制是{seed.title_zh}。{seed.need_zh}。",
        seed.invariant_en + ".",
        seed.invariant_zh + "。",
        f"The durable boundary is this: {seed.invariant_en[0].lower() + seed.invariant_en[1:]}.",
        f"真正要守住的边界是：{seed.invariant_zh}。",
    )


FACTS = tuple(_facts(seed) for seed in SEEDS)
