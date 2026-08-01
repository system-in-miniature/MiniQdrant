# Stage 13 · 原子 Snapshot 与 Restore

### 目标

实现原子 Snapshot 与 Restore，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/miniqdrant/collection.py`
    - `src/miniqdrant/database.py`
    - `src/miniqdrant/persistence/snapshot.py`
    - `tests/acceptance/test_snapshot_roundtrip.py`
    - `tests/reliability/test_snapshot.py`
    - `tests/reliability/test_snapshot_restore_failure.py`

### 当前遇到的问题

可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。

### 测试契约

#### 先看会坏在哪里

聚焦测试让原子 Snapshot 与 Restore经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/acceptance/test_snapshot_roundtrip.py"
    ```diff
    diff --git a/tests/acceptance/test_snapshot_roundtrip.py b/tests/acceptance/test_snapshot_roundtrip.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9d04e9fbcca0b11371bc9cdce32afacec6907a20
    --- /dev/null
    +++ b/tests/acceptance/test_snapshot_roundtrip.py
    @@ -0,0 +1,29 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point, SearchRequest
    +
    +
    +def test_snapshot_roundtrip_survives_source_removal(tmp_path) -> None:
    +    source_path = tmp_path / "source"
    +    source_database = Database.open(source_path)
    +    collection = source_database.create_collection(
    +        "vectors",
    +        dimension=3,
    +        distance=Distance.COSINE,
    +    )
    +    collection.upsert(
    +        [
    +            Point(7, (1.0, 0.0, 0.0), {"tenant": "a"}),
    +            Point(8, (0.0, 1.0, 0.0), {"tenant": "b"}),
    +        ]
    +    )
    +    snapshot = collection.create_snapshot(tmp_path / "snapshots" / "portable")
    +    source_database.close()
    +
    +    Database.restore_collection(snapshot, tmp_path / "new-db", "restored")
    +    restored = Database.open(tmp_path / "new-db").collection("restored")
    +
    +    assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
    +        7,
    +        8,
    +    ]
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让原子 Snapshot 与 Restore经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/reliability/test_snapshot.py"
    ```diff
    diff --git a/tests/reliability/test_snapshot.py b/tests/reliability/test_snapshot.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d2a0e8b37c1cc202aee762c46e69cc9491be3157
    --- /dev/null
    +++ b/tests/reliability/test_snapshot.py
    @@ -0,0 +1,27 @@
    +from __future__ import annotations
    +
    +from miniqdrant import Database, Distance, Point, SearchRequest
    +
    +
    +def test_snapshot_restores_searchable_collection(tmp_path) -> None:
    +    live_path = tmp_path / "live"
    +    collection = Database.open(live_path).create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert(
    +        [
    +            Point(1, (1.0, 0.0), {"name": "one"}),
    +            Point(2, (0.0, 1.0), {"name": "two"}),
    +        ]
    +    )
    +    collection.optimize()
    +    expected = collection.search(SearchRequest((1.0, 0.0), 2))
    +
    +    snapshot = collection.create_snapshot(tmp_path / "backups" / "sp-1")
    +    Database.restore_collection(snapshot, tmp_path / "restored", "items")
    +    restored = Database.open(tmp_path / "restored").collection("items")
    +
    +    assert restored.search(SearchRequest((1.0, 0.0), 2)) == expected
    +    assert restored.retrieve([1, 2]) == collection.retrieve([1, 2])
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让原子 Snapshot 与 Restore经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/reliability/test_snapshot_restore_failure.py"
    ```diff
    diff --git a/tests/reliability/test_snapshot_restore_failure.py b/tests/reliability/test_snapshot_restore_failure.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a29d19cf47b8dd0cf2758e3809083fb394306f2b
    --- /dev/null
    +++ b/tests/reliability/test_snapshot_restore_failure.py
    @@ -0,0 +1,99 @@
    +from __future__ import annotations
    +
    +import json
    +
    +import pytest
    +
    +from miniqdrant import Database, Distance, Point, SnapshotError
    +
    +
    +def test_invalid_snapshot_never_replaces_live_collection(tmp_path) -> None:
    +    database_path = tmp_path / "db"
    +    database = Database.open(database_path)
    +    live = database.create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    live.upsert([Point(1, (1.0, 0.0), {"source": "live"})])
    +    live.flush()
    +
    +    source = Database.open(tmp_path / "source").create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    source.upsert([Point(2, (0.0, 1.0), {"source": "snapshot"})])
    +    snapshot = source.create_snapshot(tmp_path / "snapshot")
    +    metadata_path = snapshot / "snapshot.json"
    +    metadata = json.loads(metadata_path.read_text())
    +    first_file = next(iter(metadata["files"]))
    +    (snapshot / "collection" / first_file).write_bytes(b"corrupt")
    +
    +    with pytest.raises(SnapshotError):
    +        Database.restore_collection(
    +            snapshot,
    +            database_path,
    +            "items",
    +            replace=True,
    +        )
    +
    +    assert live.retrieve([1])[0].payload["source"] == "live"
    +    assert (database_path / "collections" / "items").is_dir()
    +
    +
    +def test_snapshot_publish_failure_leaves_no_partial_target(tmp_path) -> None:
    +    collection = Database.open(tmp_path / "db").create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    collection.upsert([Point(1, (1.0, 0.0), {})])
    +    destination = tmp_path / "backups" / "sp-1"
    +
    +    def fail(stage: str) -> None:
    +        if stage == "before_snapshot_publish":
    +            raise RuntimeError(stage)
    +
    +    with pytest.raises(RuntimeError, match="before_snapshot_publish"):
    +        collection.create_snapshot(destination, failure_injector=fail)
    +
    +    assert not destination.exists()
    +
    +
    +def test_restore_publish_failure_rolls_back_previous_collection(tmp_path) -> None:
    +    database_path = tmp_path / "db"
    +    database = Database.open(database_path)
    +    original = database.create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    original.upsert([Point(1, (1.0, 0.0), {"source": "original"})])
    +    original.flush()
    +    database.close()
    +
    +    replacement = Database.open(tmp_path / "replacement").create_collection(
    +        "items",
    +        dimension=2,
    +        distance=Distance.DOT,
    +    )
    +    replacement.upsert([Point(2, (0.0, 1.0), {"source": "replacement"})])
    +    snapshot = replacement.create_snapshot(tmp_path / "valid-snapshot")
    +
    +    def fail(stage: str) -> None:
    +        if stage == "before_restore_publish":
    +            raise RuntimeError(stage)
    +
    +    with pytest.raises(RuntimeError, match="before_restore_publish"):
    +        Database.restore_collection(
    +            snapshot,
    +            database_path,
    +            "items",
    +            replace=True,
    +            failure_injector=fail,
    +        )
    +
    +    reopened = Database.open(database_path).collection("items")
    +    assert reopened.retrieve([1])[0].payload["source"] == "original"
    +    assert reopened.retrieve([2]) == ()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让原子 Snapshot 与 Restore经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert [hit.id for hit in restored.search(SearchRequest((1.0, 0.0, 0.0), 2)).hits] == [
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是原子 Snapshot 与 Restore。可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。

### 为什么需要这个机制

可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

### 机制板块

#### 原子 Snapshot 与 Restore机制

Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

??? note "文件差异：src/miniqdrant/collection.py"
    ```diff
    diff --git a/src/miniqdrant/collection.py b/src/miniqdrant/collection.py
    index 9a8d336c29cec30d9c73e6b9af0169069e6fe14a..fd0756309f34e111e57e6f05b817a7208d209af1 100644
    --- a/src/miniqdrant/collection.py
    +++ b/src/miniqdrant/collection.py
    @@ -31,6 +31,7 @@ from miniqdrant.persistence.metadata import (
         read_collection_metadata,
         write_collection_metadata,
     )
    +from miniqdrant.persistence.snapshot import create_collection_snapshot
     from miniqdrant.persistence.wal import (
         DeleteOperation,
         Durability,
    @@ -373,6 +374,23 @@ class Collection(Lifecycle):
         def vacuum(self) -> None:
             self.optimize()

    +    def create_snapshot(
    +        self,
    +        destination: str | Path,
    +        *,
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> Path:
    +        self._ensure_open()
    +        with self._optimizer_lock, self._update_lock:
    +            self.flush()
    +            self._wal.flush()
    +            return create_collection_snapshot(
    +                self._path,
    +                Path(destination),
    +                self._manifest,
    +                failure_injector=failure_injector,
    +            )
    +
         def close(self) -> None:
             if not self._mark_closed():
                 return
    ```

??? note "文件差异：src/miniqdrant/database.py"
    ```diff
    diff --git a/src/miniqdrant/database.py b/src/miniqdrant/database.py
    index 2b831bce3e83ef2659739c37f3dfec3f71a0dd3b..015eab876ee21f0246fb52d7bacfb3aeb2792022 100644
    --- a/src/miniqdrant/database.py
    +++ b/src/miniqdrant/database.py
    @@ -1,10 +1,13 @@
     from __future__ import annotations

    +import os
     import re
     import shutil
    +import tempfile
     from collections.abc import Callable
     from pathlib import Path
     from threading import RLock
    +from uuid import uuid4

     from miniqdrant.collection import Collection
     from miniqdrant.config import (
    @@ -19,6 +22,13 @@ from miniqdrant.errors import (
         CollectionNotFoundError,
     )
     from miniqdrant.lifecycle import Lifecycle
    +from miniqdrant.persistence.fsync import fsync_directory
    +from miniqdrant.persistence.metadata import (
    +    CollectionMetadata,
    +    read_collection_metadata,
    +    write_collection_metadata,
    +)
    +from miniqdrant.persistence.snapshot import validate_collection_snapshot
     from miniqdrant.persistence.wal import Durability

     _COLLECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    @@ -102,6 +112,57 @@ class Database(Lifecycle):
                 self._collections[name] = collection
                 return collection

    +    @classmethod
    +    def restore_collection(
    +        cls,
    +        snapshot: str | Path,
    +        database_path: str | Path,
    +        name: str,
    +        *,
    +        replace: bool = False,
    +        durability: Durability = Durability.ALWAYS,
    +        failure_injector: Callable[[str], None] | None = None,
    +    ) -> Path:
    +        _validate_collection_name(name)
    +        failure = failure_injector or (lambda _stage: None)
    +        source = validate_collection_snapshot(Path(snapshot))
    +        root = Path(database_path)
    +        collections = root / "collections"
    +        collections.mkdir(parents=True, exist_ok=True)
    +        target = collections / name
    +        if target.exists() and not replace:
    +            raise CollectionExistsError(f"collection already exists: {name}")
    +
    +        stage = Path(tempfile.mkdtemp(prefix=f".{name}-restore-", dir=collections))
    +        backup: Path | None = None
    +        try:
    +            shutil.copytree(source, stage, dirs_exist_ok=True)
    +            metadata = read_collection_metadata(stage / "collection.json")
    +            write_collection_metadata(
    +                stage / "collection.json",
    +                CollectionMetadata(name, metadata.config, metadata.payload_schemas),
    +            )
    +            restored = Collection.open(stage, durability=durability)
    +            restored.close()
    +            fsync_directory(stage)
    +            if target.exists():
    +                backup = collections / f".{name}-backup-{uuid4().hex}"
    +                os.replace(target, backup)
    +            try:
    +                failure("before_restore_publish")
    +                os.replace(stage, target)
    +                fsync_directory(collections)
    +            except BaseException:
    +                if backup is not None and backup.exists() and not target.exists():
    +                    os.replace(backup, target)
    +                raise
    +            if backup is not None:
    +                shutil.rmtree(backup)
    +            return target
    +        except BaseException:
    +            shutil.rmtree(stage, ignore_errors=True)
    +            raise
    +
         def collection(self, name: str) -> Collection:
             self._ensure_open()
             with self._lock:
    @@ -142,4 +203,3 @@ class Database(Lifecycle):
     def _validate_collection_name(name: str) -> None:
         if not _COLLECTION_NAME.fullmatch(name):
             raise ValueError("collection name must contain only letters, digits, '_' or '-'")
    -
    ```

??? note "文件差异：src/miniqdrant/persistence/snapshot.py"
    ```diff
    diff --git a/src/miniqdrant/persistence/snapshot.py b/src/miniqdrant/persistence/snapshot.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..be43c51640ead38bc9eeb2e997852030ecc56e27
    --- /dev/null
    +++ b/src/miniqdrant/persistence/snapshot.py
    @@ -0,0 +1,140 @@
    +from __future__ import annotations
    +
    +import hashlib
    +import json
    +import os
    +import shutil
    +import tempfile
    +from collections.abc import Callable
    +from pathlib import Path
    +
    +from miniqdrant.config import config_fingerprint
    +from miniqdrant.errors import SnapshotError
    +from miniqdrant.persistence.fsync import fsync_directory
    +from miniqdrant.persistence.manifest import Manifest, ManifestStore
    +from miniqdrant.persistence.metadata import read_collection_metadata
    +from miniqdrant.segment.codec import SegmentCodec
    +
    +_FORMAT_VERSION = 1
    +
    +
    +def create_collection_snapshot(
    +    source: Path,
    +    destination: Path,
    +    manifest: Manifest,
    +    *,
    +    failure_injector: Callable[[str], None] | None = None,
    +) -> Path:
    +    failure = failure_injector or (lambda _stage: None)
    +    destination = destination.resolve()
    +    if destination.exists():
    +        raise SnapshotError(f"snapshot destination already exists: {destination}")
    +    destination.parent.mkdir(parents=True, exist_ok=True)
    +    temporary = Path(
    +        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    +    )
    +    try:
    +        collection = temporary / "collection"
    +        collection.mkdir()
    +        _copy_file(source / "collection.json", collection / "collection.json")
    +        _copy_file(source / "CURRENT", collection / "CURRENT")
    +        _copy_file(
    +            source / manifest.filename,
    +            collection / manifest.filename,
    +        )
    +        shutil.copytree(source / "wal", collection / "wal")
    +        (collection / "segments").mkdir()
    +        for segment_id in manifest.segment_ids:
    +            shutil.copytree(
    +                source / "segments" / segment_id,
    +                collection / "segments" / segment_id,
    +            )
    +        files = {
    +            path.relative_to(collection).as_posix(): _sha256(path)
    +            for path in sorted(collection.rglob("*"))
    +            if path.is_file()
    +        }
    +        metadata = {
    +            "format_version": _FORMAT_VERSION,
    +            "files": files,
    +        }
    +        snapshot_metadata = temporary / "snapshot.json"
    +        snapshot_metadata.write_bytes(_canonical_json(metadata))
    +        _fsync_tree(temporary)
    +        failure("before_snapshot_publish")
    +        os.replace(temporary, destination)
    +        fsync_directory(destination.parent)
    +        return destination
    +    except BaseException:
    +        shutil.rmtree(temporary, ignore_errors=True)
    +        raise
    +
    +
    +def validate_collection_snapshot(snapshot: Path) -> Path:
    +    snapshot = snapshot.resolve()
    +    try:
    +        metadata = json.loads((snapshot / "snapshot.json").read_bytes())
    +        if metadata["format_version"] != _FORMAT_VERSION:
    +            raise SnapshotError("unsupported snapshot format")
    +        expected = metadata["files"]
    +        if not isinstance(expected, dict):
    +            raise SnapshotError("snapshot file index must be an object")
    +        collection = snapshot / "collection"
    +        actual_files = {
    +            path.relative_to(collection).as_posix()
    +            for path in collection.rglob("*")
    +            if path.is_file()
    +        }
    +        if actual_files != set(expected):
    +            raise SnapshotError("snapshot file set does not match its index")
    +        for relative, checksum in expected.items():
    +            if _sha256(collection / relative) != checksum:
    +                raise SnapshotError(f"snapshot checksum mismatch: {relative}")
    +
    +        collection_metadata = read_collection_metadata(collection / "collection.json")
    +        manifest = ManifestStore(collection).load_current()
    +        if manifest.schema_fingerprint != config_fingerprint(
    +            collection_metadata.config
    +        ):
    +            raise SnapshotError("snapshot schema fingerprint mismatch")
    +        for segment_id in manifest.segment_ids:
    +            image = SegmentCodec.read(collection / "segments" / segment_id)
    +            if image.config != collection_metadata.config:
    +                raise SnapshotError(f"snapshot segment schema mismatch: {segment_id}")
    +        return collection
    +    except SnapshotError:
    +        raise
    +    except BaseException as error:
    +        raise SnapshotError(f"invalid collection snapshot: {snapshot}") from error
    +
    +
    +def _copy_file(source: Path, target: Path) -> None:
    +    target.parent.mkdir(parents=True, exist_ok=True)
    +    shutil.copy2(source, target)
    +
    +
    +def _sha256(path: Path) -> str:
    +    digest = hashlib.sha256()
    +    with path.open("rb") as stream:
    +        while chunk := stream.read(1024 * 1024):
    +            digest.update(chunk)
    +    return digest.hexdigest()
    +
    +
    +def _fsync_tree(root: Path) -> None:
    +    for path in sorted(root.rglob("*"), reverse=True):
    +        if path.is_file():
    +            with path.open("rb") as stream:
    +                os.fsync(stream.fileno())
    +        elif path.is_dir():
    +            fsync_directory(path)
    +    fsync_directory(root)
    +
    +
    +def _canonical_json(value: object) -> bytes:
    +    return json.dumps(
    +        value,
    +        ensure_ascii=False,
    +        sort_keys=True,
    +        separators=(",", ":"),
    +    ).encode()
    ```

**是什么，为什么现在需要**

核心机制是原子 Snapshot 与 Restore。可移植备份需要 Metadata、Manifest、Segment 与 WAL 的自洽切面，恢复后不能与在线 Collection 共享身份。

**在运行时做什么**

Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

**关键语句理解**

真正要守住的边界是：Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/13-snapshot-restore/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Snapshot 只包含一个声明的 Generation，Restore 要么发布完整校验副本，要么保持目标不变。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-qdrant/blob/main/docs/zh/tutorial/10-snapshots-methodology.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-qdrant/blob/main/journey/stages/13-snapshot-restore/stage.patch)
