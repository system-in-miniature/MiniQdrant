from __future__ import annotations

from threading import RLock

from miniqdrant.errors import ClosedResourceError


class Lifecycle:
    def __init__(self) -> None:
        self._lifecycle_lock = RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lifecycle_lock:
            return self._closed

    def _ensure_open(self) -> None:
        if self.closed:
            raise ClosedResourceError(f"{type(self).__name__} is closed")

    def _mark_closed(self) -> bool:
        with self._lifecycle_lock:
            if self._closed:
                return False
            self._closed = True
            return True

