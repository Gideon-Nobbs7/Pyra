import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from app.settings import get_settings

RECENT_TTL_S = 60
HISTORICAL_TTL_S = 3600
MAX_KEYS = 1000


@dataclass
class _Entry:
    value: dict
    expires_at: float


class CacheBackend(Protocol):

    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, value: dict, ttl_s: int) -> None: ...

    def invalidate(self, prefix: str | None = None) -> int: ...

    def __len__(self) -> int: ...


class LruCacheBackend:
    def __init__(self, max_keys: int = MAX_KEYS) -> None:
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._max_keys = max_keys
        self._generation = 0
        self.hits = 0
        self.misses = 0
        self._memoized = lru_cache(maxsize=max_keys)(self._lookup)

    def _lookup(self, generation: int, key: str) -> _Entry | None:
        return self._store.get(key)

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
        # Closed historical months get long TTL else recent TTL.
        try:
            s = start_iso[:7]
            e = end_iso[:7]
            if s == e:
                return HISTORICAL_TTL_S
        except Exception:
            pass
        return RECENT_TTL_S

    def get(self, key: str) -> dict | None:
        entry = self._memoized(self._generation, key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at < time.monotonic():
            self._store.pop(key, None)
            self._generation += 1  # orphan the stale memoized hit
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return entry.value

    def put(self, key: str, value: dict, ttl_s: int) -> None:
        self._store[key] = _Entry(value=value, expires_at=time.monotonic() + ttl_s)
        self._store.move_to_end(key)
        self._generation += 1  # orphan memoized reads - writes always win
        while len(self._store) > self._max_keys:
            oldest = next(iter(self._store))
            self._store.pop(oldest)

    def invalidate(self, prefix: str | None = None) -> int:
        if prefix is None:
            n = len(self._store)
            self._store.clear()
            self._generation += 1
            return n
        doomed = [k for k in self._store if k.startswith(prefix)]
        for k in doomed:
            self._store.pop(k, None)
        if doomed:
            self._generation += 1
        return len(doomed)

    def lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def stats(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "size": len(self._store),
            "lru": self._memoized.cache_info()._asdict(),
        }


BoundedCache = LruCacheBackend


def build_cache(kind: str | None = None, max_keys: int = MAX_KEYS) -> LruCacheBackend:
    selected = (kind or get_settings().cache_backend).strip().lower()
    if selected == "lru":
        return LruCacheBackend(max_keys=max_keys)
    raise ValueError(f"unknown CACHE_BACKEND={selected!r}; expected 'lru'")


@dataclass
class CacheState:
    cache: LruCacheBackend = field(default_factory=build_cache)


cache_state = CacheState()
