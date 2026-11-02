"""
One TTL cache for every source.

Replaces six unrelated caches that had grown up independently: `_GDELT_CACHE`
and `_NEWS_CACHE` in the extinction-risk service, the Movebank router's `_cache`
(which never evicted anything), two `lru_cache`s, and the agent's species list.
Each had its own key format and expiry rules, and none could be inspected or
cleared from one place.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("ecopath.data.cache")

# Entries are small (JSON payloads), but an unbounded dict on a long-running
# server is a leak. Evict the oldest entries once the cap is passed.
MAX_ENTRIES = 2000


def make_key(source: str, operation: str, params: dict) -> str:
    """Stable key for a source operation and its arguments."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"{source}:{operation}:{digest}"


class TTLCache:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._max = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if time.time() >= expires_at:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        with self._lock:
            if len(self._store) >= self._max:
                self._evict_locked()
            self._store[key] = (time.time() + ttl_seconds, value)

    def _evict_locked(self) -> None:
        """Drop expired entries; if that frees nothing, drop the oldest tenth."""
        now = time.time()
        expired = [k for k, (exp, _) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]
        if not expired:
            oldest = sorted(self._store.items(), key=lambda kv: kv[1][0])
            for k, _ in oldest[: max(1, self._max // 10)]:
                del self._store[k]

    def invalidate(self, prefix: str = "") -> int:
        """Drop entries whose key starts with `prefix` (e.g. a source id)."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


cache = TTLCache()
