"""?live=true: bounded FIRMS pull served directly, never persisted."""

import json
from datetime import UTC, datetime, timedelta

import app.db as db_module
import app.firms as firms_lib
from tests.conftest import get_client

BBOX = "-1.9,6.5,-1.4,6.9"
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)


def _live_row(suffix: str, observed: datetime) -> dict:
    return {
        "id": f"modis-{suffix}",
        "source": "modis",
        "source_record_id": suffix.ljust(16, "0"),
        "observed_at": observed,
        "ingested_at": NOW,
        "latitude": 6.7,
        "longitude": -1.6,
        "instrument": "MODIS",
        "platform": "Terra",
        "confidence": "h",
        "frp": 12.5,
        "frp_unit": "MW",
        "quality_flags": None,
        "product_version": "6.1NRT",
        "raw_properties": json.dumps({"brightness": 301.5, "daynight": "D"}),
    }


def _recent_params(**extra):
    params = {
        "start": (NOW - timedelta(days=3)).isoformat(),
        "end": NOW.isoformat(),
        "bbox": BBOX,
        "live": "1",
    }
    params.update(extra)
    return params


def _live_env(monkeypatch, **overrides):
    """Recent-window live request with a working provider unless overridden."""
    monkeypatch.setattr(firms_lib, "_utcnow", lambda: NOW)
    monkeypatch.setattr(firms_lib, "map_key", lambda: "K")
    monkeypatch.setattr(firms_lib, "rate_limit_ok", lambda: True)
    if "fetch" in overrides:
        monkeypatch.setattr(firms_lib, "fetch_live_records", overrides["fetch"])


def test_live_rejects_bad_value(monkeypatch):
    _live_env(monkeypatch)
    r = get_client().get("/api/v1/observations", params=_recent_params(live="2"))
    assert r.status_code == 422


def test_live_rejects_history_window(monkeypatch):
    _live_env(monkeypatch)
    old = NOW - timedelta(days=400)
    r = get_client().get(
        "/api/v1/observations",
        params={
            "start": (old - timedelta(days=5)).isoformat(),
            "end": old.isoformat(),
            "bbox": BBOX,
            "live": "true",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "unavailable"
    assert "recent window" in body["coverage_reason"]
    assert body["freshness"]["store"] == "live"


def test_live_rejects_wide_area(monkeypatch):
    _live_env(monkeypatch)
    r = get_client().get("/api/v1/observations", params=_recent_params(bbox="-180,-90,180,90"))
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "unavailable"
    assert "deg" in body["coverage_reason"]


def test_live_requires_map_key(monkeypatch):
    _live_env(monkeypatch)
    monkeypatch.setattr(firms_lib, "map_key", lambda: "")
    r = get_client().get("/api/v1/observations", params=_recent_params())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"


def test_live_rate_limited(monkeypatch):
    _live_env(monkeypatch)
    monkeypatch.setattr(firms_lib, "rate_limit_ok", lambda: False)
    r = get_client().get("/api/v1/observations", params=_recent_params())
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


def test_live_serves_rows_without_persisting(monkeypatch):
    calls = {"fetch": 0}
    rows = [
        _live_row("b", NOW - timedelta(days=1)),
        _live_row("a", NOW - timedelta(days=2)),
    ]

    def fake_fetch(api_products, sources, bbox, fetch_end, timeout_s=8):
        calls["fetch"] += 1
        assert set(sources) <= {"modis", "viirs"}
        assert timeout_s == 8
        return list(rows), []

    def no_store(*args, **kwargs):
        raise AssertionError("live mode must not touch the database")

    _live_env(monkeypatch, fetch=fake_fetch)
    monkeypatch.setattr(db_module, "fetch_page", no_store)
    monkeypatch.setattr(db_module, "fetch_count", no_store)
    monkeypatch.setattr(firms_lib, "fetch_and_store", no_store)

    c = get_client()
    r = c.get("/api/v1/observations", params=_recent_params())
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "ok"
    assert body["synthetic"] is False
    assert body["freshness"]["store"] == "live"
    assert body["count"] == 2
    # Sorted oldest-first; envelope conversion applied (dict raw_properties).
    assert [d["id"] for d in body["data"]] == ["modis-a", "modis-b"]
    assert body["data"][0]["raw_properties"] == {"brightness": 301.5, "daynight": "D"}
    assert calls["fetch"] == 1

    r2 = c.get("/api/v1/observations", params=_recent_params())
    assert r2.status_code == 200
    assert calls["fetch"] == 2  # live results are never cached


def test_live_pagination(monkeypatch):
    rows = [
        _live_row("b", NOW - timedelta(days=1)),
        _live_row("a", NOW - timedelta(days=2)),
    ]
    _live_env(monkeypatch, fetch=lambda *a, **k: (list(rows), []))

    c = get_client()
    r1 = c.get("/api/v1/observations", params=_recent_params(limit="1"))
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["count"] == 2
    assert [d["id"] for d in b1["data"]] == ["modis-a"]
    assert b1["pagination"]["has_more"] is True
    cursor = b1["pagination"]["next_cursor"]
    assert cursor

    r2 = c.get("/api/v1/observations", params=_recent_params(limit="1", cursor=cursor))
    assert r2.status_code == 200
    b2 = r2.json()
    assert [d["id"] for d in b2["data"]] == ["modis-b"]
    assert b2["pagination"]["has_more"] is False


def test_live_provider_failure_is_503_not_empty(monkeypatch):
    _live_env(monkeypatch, fetch=lambda *a, **k: ([], [{"stage": "fetch"}]))
    r = get_client().get("/api/v1/observations", params=_recent_params())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"


def test_live_genuine_empty_is_empty(monkeypatch):
    _live_env(monkeypatch, fetch=lambda *a, **k: ([], []))
    r = get_client().get("/api/v1/observations", params=_recent_params())
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "empty"
    assert "does not prove" in body["coverage_reason"]
