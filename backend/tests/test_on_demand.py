"""On-demand bounded fetch: DB miss warms Postgres, revisit hits cache."""

from datetime import UTC, datetime, timedelta

import app.db as db_module
import app.firms as firms_lib
from tests.conftest import get_client
from tests.test_db_read_path import DB_ROW, FRESHNESS

BBOX = "-1.9,6.5,-1.4,6.9"
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)


def test_on_demand_window_recent_small():
    firms_lib.reset_rate_limit()
    start = NOW - timedelta(days=3)
    window = firms_lib.on_demand_window(start, NOW, [-1.9, 6.5, -1.4, 6.9])
    assert window is not None
    fetch_start, fetch_end, bbox_str = window
    assert fetch_end == "2026-11-14"
    assert bbox_str == "-1.9,6.5,-1.4,6.9"


def test_on_demand_window_rejects_history_and_wide_area():
    old = NOW - timedelta(days=60)
    assert firms_lib.on_demand_window(old - timedelta(days=5), old, [-1.9, 6.5, -1.4, 6.9]) is None
    recent = NOW - timedelta(days=2)
    assert firms_lib.on_demand_window(recent, NOW, [-180.0, -90.0, 180.0, 90.0]) is None


def test_rate_limit_blocks_rapid_repeat():
    firms_lib.reset_rate_limit()
    assert firms_lib.rate_limit_ok() is True
    assert firms_lib.rate_limit_ok() is False  # within MIN_PROVIDER_INTERVAL_S


def test_db_miss_triggers_fetch_then_cache(monkeypatch):
    firms_lib.reset_rate_limit()
    calls = {"fetch": 0, "page": 0}

    def fake_page(start, end, bbox, products, limit, offset):
        calls["page"] += 1
        if calls["page"] == 1:
            return [], False
        return [DB_ROW], False

    def fake_fetch_and_store(products, sources, bbox, fetch_end, url):
        calls["fetch"] += 1
        assert set(sources) <= {"modis", "viirs"}
        return 2, []

    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", fake_page)
    monkeypatch.setattr(db_module, "fetch_freshness", lambda: FRESHNESS)
    monkeypatch.setattr(db_module, "fetch_count", lambda *a: 2)
    monkeypatch.setattr(firms_lib, "map_key", lambda: "K")
    monkeypatch.setattr(firms_lib, "fetch_and_store", fake_fetch_and_store)
    monkeypatch.setattr(firms_lib, "_utcnow", lambda: NOW)

    c = get_client()
    params = {
        "start": (NOW - timedelta(days=3)).isoformat(),
        "end": NOW.isoformat(),
        "bbox": BBOX,
    }
    r1 = c.get("/api/v1/observations", params=params)
    assert r1.status_code == 200
    body = r1.json()
    assert body["coverage_status"] == "ok"
    assert body["data"][0]["id"] == "modis-abc123"
    assert body["synthetic"] is False
    assert calls["fetch"] == 1

    r2 = c.get("/api/v1/observations", params=params)
    assert r2.status_code == 200
    assert calls["fetch"] == 1  # revisit served from cache
    assert calls["page"] == 2  # no further DB reads


def test_db_miss_without_key_serves_empty(monkeypatch):
    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", lambda *a: ([], False))
    monkeypatch.setattr(db_module, "fetch_freshness", lambda: FRESHNESS)
    monkeypatch.setattr(db_module, "fetch_count", lambda *a: 0)
    monkeypatch.setattr(firms_lib, "map_key", lambda: "")

    c = get_client()
    r = c.get(
        "/api/v1/observations",
        params={"start": "2024-08-01T00:00:00Z", "end": "2024-08-31T00:00:00Z", "bbox": BBOX},
    )
    assert r.status_code == 200
    assert r.json()["coverage_status"] == "empty"
