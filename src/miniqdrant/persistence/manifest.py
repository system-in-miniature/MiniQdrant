from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from miniqdrant.errors import CorruptionError
from miniqdrant.persistence.fsync import fsync_directory

_SEGMENT_ID = re.compile(r"^seg-[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class Manifest:
    generation: int
    schema_fingerprint: str
    segment_ids: tuple[str, ...]
    replay_boundary: int

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise ValueError("manifest generation must be positive")
        if self.replay_boundary < 0:
            raise ValueError("manifest replay boundary must be non-negative")
        object.__setattr__(self, "segment_ids", tuple(self.segment_ids))
        if len(set(self.segment_ids)) != len(self.segment_ids):
            raise ValueError("manifest segment IDs must be unique")
        if any(not _SEGMENT_ID.fullmatch(segment_id) for segment_id in self.segment_ids):
            raise ValueError("manifest contains an unsafe segment ID")

    @property
    def filename(self) -> str:
        return f"manifest-{self.generation:020d}.json"


class ManifestStore:
    def __init__(
        self,
        path: str | Path,
        *,
        failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._failure_injector = failure_injector or (lambda _stage: None)

    def publish(self, manifest: Manifest) -> None:
        current = self._load_current_optional()
        if current is not None and manifest.generation <= current.generation:
            raise ValueError("manifest generation must increase")
        target = self._path / manifest.filename
        payload = _encode_manifest(manifest)
        temporary = target.with_suffix(".json.tmp")
        _write_fsynced(temporary, payload)
        os.replace(temporary, target)
        fsync_directory(self._path)

        current_temporary = self._path / "CURRENT.tmp"
        _write_fsynced(current_temporary, f"{manifest.filename}\n".encode())
        self._failure_injector("before_current_replace")
        os.replace(current_temporary, self._path / "CURRENT")
        fsync_directory(self._path)

    def load_current(self) -> Manifest:
        current = self._load_current_optional()
        if current is None:
            raise CorruptionError("CURRENT manifest pointer is missing")
        return current

    def _load_current_optional(self) -> Manifest | None:
        current_path = self._path / "CURRENT"
        if not current_path.exists():
            return None
        try:
            filename = current_path.read_text().strip()
            if Path(filename).name != filename or not filename.startswith("manifest-"):
                raise CorruptionError("invalid CURRENT manifest pointer")
            path = self._path / filename
            return _decode_manifest(path.read_bytes())
        except CorruptionError:
            raise
        except (OSError, UnicodeDecodeError) as error:
            raise CorruptionError("current manifest cannot be loaded") from error


def _encode_manifest(manifest: Manifest) -> bytes:
    payload = asdict(manifest)
    payload["segment_ids"] = list(manifest.segment_ids)
    canonical = _canonical_json(payload)
    envelope = {
        "format_version": 1,
        "payload": payload,
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }
    return _canonical_json(envelope)


def _decode_manifest(value: bytes) -> Manifest:
    try:
        envelope = json.loads(value)
        if envelope["format_version"] != 1:
            raise CorruptionError("unsupported manifest format")
        payload = envelope["payload"]
        if hashlib.sha256(_canonical_json(payload)).hexdigest() != envelope["sha256"]:
            raise CorruptionError("manifest checksum mismatch")
        return Manifest(
            generation=int(payload["generation"]),
            schema_fingerprint=str(payload["schema_fingerprint"]),
            segment_ids=tuple(payload["segment_ids"]),
            replay_boundary=int(payload["replay_boundary"]),
        )
    except CorruptionError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise CorruptionError("invalid manifest") from error


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _write_fsynced(path: Path, value: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
