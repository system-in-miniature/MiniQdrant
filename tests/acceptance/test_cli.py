from __future__ import annotations

import json
import subprocess


def _cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "miniqdrant", *(str(argument) for argument in arguments)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_cli_create_upsert_search(tmp_path) -> None:
    points = tmp_path / "points.jsonl"
    points.write_text(
        "\n".join(
            [
                '{"id":1,"vector":[1,0],"payload":{"name":"one"}}',
                '{"id":2,"vector":[0,1],"payload":{"name":"two"}}',
            ]
        )
        + "\n"
    )

    _cli(
        "create",
        tmp_path / "db",
        "items",
        "--dimension",
        2,
        "--distance",
        "cosine",
    )
    upsert = _cli("upsert", tmp_path / "db", "items", points)
    result = _cli("search", tmp_path / "db", "items", "[1,0]", "--limit", 1)

    assert json.loads(upsert.stdout)["accepted"] == 2
    assert json.loads(result.stdout)["hits"][0]["id"] == 1


def test_cli_snapshot_and_restore(tmp_path) -> None:
    points = tmp_path / "points.jsonl"
    points.write_text('{"id":7,"vector":[1,0],"payload":{}}\n')
    _cli("create", tmp_path / "db", "items", "--dimension", 2)
    _cli("upsert", tmp_path / "db", "items", points)

    _cli("snapshot", tmp_path / "db", "items", tmp_path / "snapshot")
    _cli(
        "restore",
        tmp_path / "snapshot",
        tmp_path / "restored",
        "copy",
    )
    result = _cli("search", tmp_path / "restored", "copy", "[1,0]")

    assert json.loads(result.stdout)["hits"][0]["id"] == 7
