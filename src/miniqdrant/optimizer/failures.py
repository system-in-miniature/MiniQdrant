from __future__ import annotations

from threading import Event, Lock


class OptimizationGate:
    """Deterministic synchronization points for optimizer fault tests."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[str, Event] = {}

    def arrive(self, stage: str) -> None:
        self._event(stage).set()

    def wait_until(self, stage: str, timeout: float = 5.0) -> None:
        if not self._event(stage).wait(timeout):
            raise TimeoutError(f"optimizer did not reach stage: {stage}")

    def release(self, stage: str) -> None:
        self._event(stage).set()

    def wait_for_release(self, stage: str, timeout: float = 5.0) -> None:
        if not self._event(stage).wait(timeout):
            raise TimeoutError(f"optimizer was not released at stage: {stage}")

    def _event(self, stage: str) -> Event:
        with self._lock:
            return self._events.setdefault(stage, Event())
