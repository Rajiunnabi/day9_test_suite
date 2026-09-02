"""Brute-force guard for login.

Written as a Protocol + one implementation, which is the honest version of
"when to abstract". The interface exists for a concrete reason: this in-memory
dict dies with the process and each uvicorn worker keeps its own copy, so a
real deployment swaps in Redis. Having the Protocol means that swap is a new
class plus one line in deps.py - no service code changes.

Contrast with the repositories: there is no RepositoryProtocol, because there
is no second implementation coming. Abstract where you can name the second
implementation; don't where you can't.
"""

from __future__ import annotations

import time
from typing import Protocol


class LoginThrottle(Protocol):
    def seconds_remaining(self, key: str) -> int: ...
    def record_failure(self, key: str) -> None: ...
    def reset(self, key: str) -> None: ...


class InMemoryLoginThrottle:
    """Fine for one dev server. Not shared across workers or restarts."""

    def __init__(self, max_attempts: int, lockout_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, tuple[int, float]] = {}

    def seconds_remaining(self, key: str) -> int:
        record = self._failures.get(key)
        if record is None:
            return 0
        count, last_failure = record
        if count < self.max_attempts:
            return 0
        elapsed = time.monotonic() - last_failure
        if elapsed >= self.lockout_seconds:
            self._failures.pop(key, None)
            return 0
        return int(self.lockout_seconds - elapsed)

    def record_failure(self, key: str) -> None:
        count, _ = self._failures.get(key, (0, 0.0))
        self._failures[key] = (count + 1, time.monotonic())

    def reset(self, key: str) -> None:
        """Called on success, so one typo doesn't haunt the user."""
        self._failures.pop(key, None)
