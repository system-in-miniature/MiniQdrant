# MiniQdrant Tutorial

> English quick start · [中文版](zh/index.md)

MiniQdrant is a direct-first Python reference implementation of filtered
vector search, versioned immutable segments, online optimization, and durable
recovery. It exposes the mechanisms behind a single-node vector database
without reproducing Qdrant's network API or distributed deployment surface.

中文简述：MiniQdrant 用 Python 展示过滤向量搜索、版本化不可变分段、在线优化
与持久恢复；它聚焦单节点机制，不复刻 Qdrant 的网络与分布式产品表面。

## Install

```bash
git clone https://github.com/system-in-miniature/MiniQdrant.git
cd MiniQdrant
uv sync
```

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

## First experiment

```bash
uv run python -m miniqdrant.labs.filtering
```

The lab searches a tiny collection with a tenant filter. It prints matching
IDs `[1, 3]`, excluding a vector-similar point from another tenant, and exposes
the selected per-segment plan.

Continue with the [architecture tour](architecture.md), then compare modules
with [Qdrant](qdrant-mapping.md).

For the complete API, CLI, scope, and reliability boundary, read the
[repository README](https://github.com/system-in-miniature/MiniQdrant/blob/main/README.md).
