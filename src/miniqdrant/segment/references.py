from __future__ import annotations

import shutil
from pathlib import Path
from threading import Lock

from miniqdrant.segment.immutable import ImmutableSegment


class SegmentHandle:
    """Reference-counted ownership for a published immutable segment."""

    def __init__(
        self,
        segment_id: str,
        path: Path,
        segment: ImmutableSegment,
    ) -> None:
        self.segment_id = segment_id
        self.path = path
        self.segment = segment
        self._lock = Lock()
        self._references = 0
        self._retired = False

    def acquire(self) -> SegmentHandle:
        with self._lock:
            if self._retired and self._references == 0:
                raise RuntimeError("cannot acquire a deleted segment")
            self._references += 1
        return self

    def release(self) -> None:
        delete = False
        with self._lock:
            if self._references == 0:
                raise RuntimeError("segment handle released without an acquisition")
            self._references -= 1
            delete = self._retired and self._references == 0
        if delete:
            shutil.rmtree(self.path, ignore_errors=True)

    def retire(self) -> None:
        delete = False
        with self._lock:
            self._retired = True
            delete = self._references == 0
        if delete:
            shutil.rmtree(self.path, ignore_errors=True)
