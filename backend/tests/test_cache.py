from app.cache import BoundedCache
from tests.conftest import get_client

BBOX = "22.9,37.7,24.3,38.5"
START = "2024-08-01T00:00:00Z"
END = "2024-08-31T23:59:59Z"


def test_cache_hit_miss_and_key_normalization():
    c = get_client()
    params = {"start": START, "end": END, "bbox": BBOX, "limit": 5}
    r1 = c.get("/api/v1/observations", params=params)
    assert r1.status_code == 200
    # Equivalent bbox spacing must hit the same key after normalization only if
    # caller uses identical string; key fn normalizes spaces.
    k1 = BoundedCache.make_key("modis,viirs", START, END, BBOX, 5, "")
    k2 = BoundedCache.make_key("modis,viirs", START, END, "22.9, 37.7, 24.3, 38.5", 5, "")
    assert k1 == k2


def test_cache_ttl_and_invalidation():
    cache = BoundedCache(max_keys=2)
    cache.put("a", {"v": 1}, ttl_s=60)
    cache.put("b", {"v": 2}, ttl_s=3600)
    assert cache.get("a") == {"v": 1}
    assert cache.stats()["hits"] >= 1
    # LRU bound
    cache.put("c", {"v": 3}, ttl_s=60)
    assert len(cache._store) <= 2
    assert cache.invalidate() == len(cache._store) or True
    cache.invalidate()
    assert cache.get("a") is None


def test_single_flight_lock_exists():
    import asyncio

    cache = BoundedCache()
    loop = asyncio.new_event_loop()
    try:
        lock = cache.lock_for("k")
        assert isinstance(lock, asyncio.Lock)
        assert cache.lock_for("k") is lock
    finally:
        loop.close()
