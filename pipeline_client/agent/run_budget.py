"""Deadline-aware runtime budget shared across agent operations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


class RunBudgetExceeded(RuntimeError):
    """Raised when an operation cannot finish before the checkpoint deadline."""


@dataclass(frozen=True)
class RunBudget:
    """Bounds calls and retry sleeps to the remaining invocation time."""

    deadline_at: float
    checkpoint_buffer_seconds: float = 15.0
    clock: Callable[[], float] = time.time

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_at - self.clock())

    def usable_seconds(self) -> float:
        return max(0.0, self.remaining_seconds() - self.checkpoint_buffer_seconds)

    def can_start_call(self, minimum_seconds: float = 5.0) -> bool:
        return self.usable_seconds() >= minimum_seconds

    def require_call_time(self, minimum_seconds: float = 5.0, *, operation: str = "operation") -> None:
        if not self.can_start_call(minimum_seconds):
            raise RunBudgetExceeded(
                f"Insufficient run time for {operation}: {self.remaining_seconds():.1f}s remains "
                f"with a {self.checkpoint_buffer_seconds:.1f}s checkpoint buffer"
            )

    def bounded_timeout(
        self,
        requested_seconds: float,
        *,
        minimum_seconds: float = 1.0,
        operation: str = "request",
    ) -> float:
        available = self.usable_seconds()
        if available < minimum_seconds:
            raise RunBudgetExceeded(f"Insufficient run time for {operation}: {self.remaining_seconds():.1f}s remains")
        return max(minimum_seconds, min(float(requested_seconds), available))

    def bounded_sleep(self, requested_seconds: float, *, operation: str = "retry") -> float:
        available = self.usable_seconds()
        sleep_seconds = min(max(0.0, float(requested_seconds)), available)
        if sleep_seconds <= 0:
            raise RunBudgetExceeded(f"Insufficient run time for {operation} sleep")
        return sleep_seconds
