from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from miniqdrant.config import Distance
from miniqdrant.database import Database
from miniqdrant.filters.index import PayloadSchema
from miniqdrant.json_values import thaw_json
from miniqdrant.models import Point, SearchRequest


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    options = parser.parse_args(arguments)
    result = options.run(options)
    if result is not None:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="miniqdrant",
        description="Direct-first filtered vector search reference runtime.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create a collection")
    create.add_argument("database")
    create.add_argument("collection")
    create.add_argument("--dimension", required=True, type=int)
    create.add_argument(
        "--distance",
        choices=tuple(item.value for item in Distance),
        default=Distance.COSINE.value,
    )
    create.set_defaults(run=_create)

    upsert = commands.add_parser("upsert", help="upsert JSONL points")
    upsert.add_argument("database")
    upsert.add_argument("collection")
    upsert.add_argument("points")
    upsert.set_defaults(run=_upsert)

    search = commands.add_parser("search", help="search a collection")
    search.add_argument("database")
    search.add_argument("collection")
    search.add_argument("vector")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--exact", action="store_true")
    search.add_argument("--with-vector", action="store_true")
    search.set_defaults(run=_search)

    flush = commands.add_parser("flush", help="publish the mutable segment")
    flush.add_argument("database")
    flush.add_argument("collection")
    flush.add_argument("--indexed", action="store_true")
    flush.set_defaults(run=_flush)

    optimize = commands.add_parser("optimize", help="merge, vacuum, and index")
    optimize.add_argument("database")
    optimize.add_argument("collection")
    optimize.set_defaults(run=_optimize)

    payload_index = commands.add_parser(
        "payload-index",
        help="create a payload field index",
    )
    payload_index.add_argument("database")
    payload_index.add_argument("collection")
    payload_index.add_argument("field")
    payload_index.add_argument(
        "schema",
        choices=tuple(item.value for item in PayloadSchema),
    )
    payload_index.set_defaults(run=_payload_index)

    info = commands.add_parser("info", help="describe a collection")
    info.add_argument("database")
    info.add_argument("collection")
    info.set_defaults(run=_info)

    snapshot = commands.add_parser("snapshot", help="create an atomic snapshot")
    snapshot.add_argument("database")
    snapshot.add_argument("collection")
    snapshot.add_argument("destination")
    snapshot.set_defaults(run=_snapshot)

    restore = commands.add_parser("restore", help="restore a collection snapshot")
    restore.add_argument("snapshot")
    restore.add_argument("database")
    restore.add_argument("collection")
    restore.add_argument("--replace", action="store_true")
    restore.set_defaults(run=_restore)
    return parser


def _create(options: argparse.Namespace) -> dict[str, object]:
    with _database(options.database) as database:
        collection = database.create_collection(
            options.collection,
            dimension=options.dimension,
            distance=options.distance,
        )
        return {
            "collection": collection.name,
            "dimension": collection.config.dimension,
            "distance": collection.config.distance.value,
        }


def _upsert(options: argparse.Namespace) -> dict[str, object]:
    points = tuple(
        Point(item["id"], item["vector"], item.get("payload", {}))
        for line in Path(options.points).read_text().splitlines()
        if line.strip()
        for item in (json.loads(line),)
    )
    with _database(options.database) as database:
        sequence = database.collection(options.collection).upsert(points)
        return {"accepted": len(points), "sequence": sequence}


def _search(options: argparse.Namespace) -> dict[str, object]:
    vector = json.loads(options.vector)
    with _database(options.database) as database:
        result = database.collection(options.collection).search(
            SearchRequest(
                vector,
                options.limit,
                exact=options.exact,
                with_vector=options.with_vector,
            )
        )
        return {
            "hits": [
                {
                    "id": _json_id(hit.id),
                    "score": hit.score,
                    "payload": (
                        None if hit.payload is None else thaw_json(hit.payload)
                    ),
                    "vector": hit.vector,
                }
                for hit in result.hits
            ],
            "plan": result.plan,
        }


def _flush(options: argparse.Namespace) -> dict[str, object]:
    with _database(options.database) as database:
        collection = database.collection(options.collection)
        collection.flush(indexed=options.indexed)
        return {"segments": collection.segment_statistics().segment_count}


def _optimize(options: argparse.Namespace) -> dict[str, object]:
    with _database(options.database) as database:
        collection = database.collection(options.collection)
        collection.optimize()
        return {"segments": collection.segment_statistics().segment_count}


def _payload_index(options: argparse.Namespace) -> dict[str, object]:
    with _database(options.database) as database:
        database.collection(options.collection).create_payload_index(
            options.field,
            options.schema,
        )
        return {"field": options.field, "schema": options.schema}


def _info(options: argparse.Namespace) -> dict[str, object]:
    with _database(options.database) as database:
        collection = database.collection(options.collection)
        return {
            "count": collection.count(),
            "dimension": collection.config.dimension,
            "distance": collection.config.distance.value,
            "name": collection.name,
            "payload_indexes": collection.payload_index_schemas,
            "segments": collection.segment_statistics().segment_count,
        }


def _snapshot(options: argparse.Namespace) -> dict[str, object]:
    with _database(options.database) as database:
        path = database.collection(options.collection).create_snapshot(
            options.destination
        )
        return {"snapshot": str(path)}


def _restore(options: argparse.Namespace) -> dict[str, object]:
    path = Database.restore_collection(
        options.snapshot,
        options.database,
        options.collection,
        replace=options.replace,
    )
    return {"collection": options.collection, "path": str(path)}


class _database:
    def __init__(self, path: str) -> None:
        self._database = Database.open(path)

    def __enter__(self) -> Database:
        return self._database

    def __exit__(self, *_error: object) -> None:
        self._database.close()


def _json_id(value: int | UUID) -> int | str:
    return value if isinstance(value, int) else str(value)
