"""DB read path: revisit served from Postgres + cache, no provider call."""

import app.db as db_module
from tests.conftest import get_client

BBOX = "-1.9,6.5,-1.4,6.9"
START = "2024-08-01T00:00:00Z"
END = "2024-08-31T00:00:00Z"

DB_ROW = {
    "id": "modis-abc123",
    "source": "modis",
    "source_record_id": "abc123",
    "observed_at": "2024-08-15T13:30:00+00:00",
    "ingested_at": "2024-09-01T12:00:00+00:00",
    "latitude": 6.71,
    "longitude": -1.62,
    "instrument": "MODIS",
    "platform": "Terra",
    "confidence": "n",
    "frp": 12.3,
    "frp_unit": "MW",
    "quality_flags": None,
    "product_version": "6.1NRT",
    "raw_properties": {"brightness": "320.5"},
}

FRESHNESS = {
    "latest_ingested_at": "2024-09-01T12:00:00+00:00",
    "row_count": 1,
    "synthetic": False,
    "note": "latest successful FIRMS ingestion into Postgres",
}


def _params(**extra):
    base = {"start": START, "end": END, "bbox": BBOX}
    base.update(extra)
    return base


def test_db_mode_serves_rows_then_cache(monkeypatch):
    calls = []

    def fake_page(start, end, bbox, products, limit, offset):
        calls.append((start, end, bbox, products, limit, offset))
        return [DB_ROW], False

    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", fake_page)
    monkeypatch.setattr(db_module, "fetch_freshness", lambda: FRESHNESS)
    monkeypatch.setattr(db_module, "fetch_count", lambda *a: 5)

    c = get_client()
    r1 = c.get("/api/v1/observations", params=_params())
    assert r1.status_code == 200
    body = r1.json()
    assert body["synthetic"] is False
    assert body["coverage_status"] == "ok"
    assert body["data"][0]["id"] == "modis-abc123"
    assert body["freshness"]["synthetic"] is False

    r2 = c.get("/api/v1/observations", params=_params())
    assert r2.status_code == 200
    assert len(calls) == 1  # second visit served from cache, no DB hit


def test_db_empty_is_empty_not_unavailable(monkeypatch):
    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", lambda *a: ([], False))
    monkeypatch.setattr(db_module, "fetch_freshness", lambda: FRESHNESS)
    monkeypatch.setattr(db_module, "fetch_count", lambda *a: 0)

    c = get_client()
    r = c.get("/api/v1/observations", params=_params())
    assert r.status_code == 200
    assert r.json()["coverage_status"] == "empty"


def test_db_empty_inside_fixture_window_serves_fixtures(monkeypatch):
    """No source-backed rows yet for Attica 2024: labelled fixtures fill the gap."""
    from app import firms as firms_lib

    firms_lib.reset_rate_limit()
    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", lambda *a: ([], False))
    monkeypatch.setattr(
        db_module,
        "fetch_freshness",
        lambda: {"synthetic": False, "row_count": 0, "latest_ingested_at": None},
    )
    monkeypatch.setattr(firms_lib, "map_key", lambda: "")  # no live fetch

    c = get_client()
    r = c.get(
        "/api/v1/observations",
        params={
            "start": "2024-08-01T00:00:00Z",
            "end": "2024-08-31T23:59:59Z",
            "bbox": "22.9,37.7,24.3,38.5",
            "limit": 5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "ok"
    assert body["synthetic"] is True
    assert len(body["data"]) == 5


def test_db_down_returns_503_not_empty(monkeypatch):
    def boom(*args):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", boom)

    c = get_client()
    r = c.get("/api/v1/observations", params=_params())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"
