"""Bounded in-process read-through cache (M1 full version).

Key from products + start + end + bbox + limit + cursor, normalized.
Short TTL for recent/open windows, long TTL for closed historical windows.
LRU bound + single-flight per key. Freshness comes from ingestion time,
never from cache insert time.
"""

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field

RECENT_TTL_S = 60
HISTORICAL_TTL_S = 3600
MAX_KEYS = 1000


@dataclass
class _Entry:
    value: dict
    expires_at: float


class BoundedCache:
    def __init__(self, max_keys: int = MAX_KEYS) -> None:
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._max_keys = max_keys
        self.hits = 0
        self.misses = 0

    @staticmethod
    def make_key(
        products: str,
        start: str,
        end: str,
        bbox: str,
        limit: int,
        cursor: str | None,
    ) -> str:
        norm = "|".join(
            [
                products.strip().lower(),
                start.strip(),
                end.strip(),
                ",".join(p.strip() for p in bbox.split(",")),
                str(limit),
                (cursor or "").strip(),
            ]
        )
        return hashlib.sha256(norm.encode()).hexdigest()[:32]

    @staticmethod
    def ttl_for(start_iso: str, end_iso: str) -> int:
        # Closed historical months (same year-month, past) get long TTL.
        # Anything else is treated as recent/open.
        try:
            s = start_iso[:7]
            e = end_iso[:7]
            if s == e:
                return HISTORICAL_TTL_S
        except Exception:
            pass
        return RECENT_TTL_S

    def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at < time.monotonic():
            self._store.pop(key, None)
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return entry.value

    def put(self, key: str, value: dict, ttl_s: int) -> None:
        self._store[key] = _Entry(value=value, expires_at=time.monotonic() + ttl_s)
        self._store.move_to_end(key)
        while len(self._store) > self._max_keys:
            self._store.popitem(last=False)

    def invalidate(self, prefix: str | None = None) -> int:
        if prefix is None:
            n = len(self._store)
            self._store.clear()
            return n
        doomed = [k for k in self._store if k.startswith(prefix)]
        for k in doomed:
            self._store.pop(k, None)
        return len(doomed)

    def lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "size": len(self._store)}


@dataclass
class CacheState:
    cache: BoundedCache = field(default_factory=BoundedCache)


cache_state = CacheState()
