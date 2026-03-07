"""
In-memory idempotency store with TTL.
If X-Idempotency-Key is sent and was already seen within TTL, treat as duplicate (return 202, do not enqueue).
"""

from __future__ import annotations

import time


class IdempotencyStore:
    """In-memory store: key -> expiry_ts. add(key) returns True if new, False if duplicate."""

    def __init__(self, ttl_sec: int = 86400) -> None:
        self._ttl_sec = ttl_sec
        self._store: dict[str, float] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [k for k, exp in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]

    def add(self, key: str) -> bool:
        """Return True if key was not seen (first time); False if already seen within TTL (duplicate)."""
        if not key or not key.strip():
            return True
        self._prune()
        now = time.monotonic()
        if key in self._store and self._store[key] > now:
            return False
        self._store[key] = now + self._ttl_sec
        return True
