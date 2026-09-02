"""app/core/throttle.py - the brute-force guard.

The interesting problem here is time. The lockout lasts 15 minutes in
production; a test cannot wait 15 minutes and must not sleep for even one
second. monkeypatch replaces the clock instead, so "15 minutes later" costs
nothing and the test is deterministic - a sleep-based version would be the
textbook flaky test, passing on a fast machine and failing on a loaded one.
"""

from __future__ import annotations

import pytest

from app.core import throttle as throttle_module
from app.core.throttle import InMemoryLoginThrottle

pytestmark = pytest.mark.unit


class FakeClock:
    """Stands in for time.monotonic(). The test moves time by hand."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    # Patch the name where it is USED, not where it is defined. throttle.py
    # does `import time` then calls `time.monotonic()`, so patching the
    # attribute on that module's `time` reference is what takes effect.
    monkeypatch.setattr(throttle_module.time, "monotonic", fake)
    return fake


def test_a_fresh_key_is_never_locked(clock: FakeClock):
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    assert guard.seconds_remaining("nobody@example.com") == 0


@pytest.mark.parametrize("failures", [1, 2])
def test_below_the_limit_nothing_happens(clock: FakeClock, failures: int):
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    for _ in range(failures):
        guard.record_failure("a@example.com")
    assert guard.seconds_remaining("a@example.com") == 0


def test_hitting_the_limit_locks_the_key(clock: FakeClock):
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    for _ in range(3):
        guard.record_failure("a@example.com")

    assert guard.seconds_remaining("a@example.com") == 60


def test_the_lock_expires_on_its_own(clock: FakeClock):
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    for _ in range(3):
        guard.record_failure("a@example.com")

    clock.advance(59)
    assert guard.seconds_remaining("a@example.com") == 1

    clock.advance(1)
    assert guard.seconds_remaining("a@example.com") == 0


def test_success_clears_the_count(clock: FakeClock):
    """Two typos followed by a correct password must not leave the user one
    mistake away from a lockout tomorrow."""
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    guard.record_failure("a@example.com")
    guard.record_failure("a@example.com")

    guard.reset("a@example.com")

    guard.record_failure("a@example.com")
    assert guard.seconds_remaining("a@example.com") == 0


def test_one_persons_failures_do_not_lock_out_anybody_else(clock: FakeClock):
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    for _ in range(5):
        guard.record_failure("victim@example.com")

    assert guard.seconds_remaining("victim@example.com") > 0
    assert guard.seconds_remaining("someone-else@example.com") == 0


def test_resetting_a_key_that_was_never_seen_is_harmless(clock: FakeClock):
    guard = InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)
    guard.reset("never@example.com")  # must not raise
