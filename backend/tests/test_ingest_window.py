"""ingest_window: routing, tier resolution, and exit codes. No live provider, no real DB."""

from datetime import UTC, datetime, timedelta

import app.db as db_module
import app.firms as firms_lib
from scripts import ingest_window

NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
SMALL = [-1.9, 6.5, -1.4, 6.9]
WIDE = [-180.0, -90.0, 180.0, 90.0]


def _recent():
    return NOW - timedelta(days=3), NOW


def test_choose_source_recent_small_with_key():
    start, end = _recent()
    source, _ = ingest_window.choose_source(start, end, SMALL, map_key="K", ee_ready=False)
    assert source == "firms"


def test_choose_source_history_needs_ee():
    old = NOW - timedelta(days=400)
    source, reason = ingest_window.choose_source(
        old - timedelta(days=5), old, SMALL, map_key="K", ee_ready=True
    )
    assert source == "ee"
    source, reason = ingest_window.choose_source(
        old - timedelta(days=5), old, SMALL, map_key="K", ee_ready=False
    )
    assert source == "none"
    assert "EE" in reason


def test_choose_source_wide_area_needs_ee():
    start, end = _recent()
    source, _ = ingest_window.choose_source(start, end, WIDE, map_key="K", ee_ready=True)
    assert source == "ee"


def test_choose_source_nothing_configured():
    start, end = _recent()
    source, reason = ingest_window.choose_source(start, end, SMALL, map_key="", ee_ready=False)
    assert source == "none"
    assert "FIRMS_MAP_KEY" in reason


def _patch_firms_path(monkeypatch):
    monkeypatch.setattr(firms_lib, "load_api_products", lambda: {"modis": "M"})
    monkeypatch.setattr(firms_lib, "fetch_api_csv", lambda *a, **k: "fake-csv")
    monkeypatch.setattr(firms_lib, "prepare_records", lambda *a, **k: [{}, {}])
    monkeypatch.setattr(firms_lib, "upsert_records", lambda records, url: len(records))


def test_run_firms_window_upserts_tail(monkeypatch):
    _patch_firms_path(monkeypatch)
    start, end = _recent()
    summary = ingest_window.run_firms_window(SMALL, start, end, "postgresql://x", "K")
    assert summary["source"] == "firms"
    assert summary["rows_upserted"] == 2
    assert summary["failures"] == []
    assert summary["tail_only"] is False


def test_run_firms_window_long_window_uses_tail(monkeypatch):
    _patch_firms_path(monkeypatch)
    start = NOW - timedelta(days=9)
    summary = ingest_window.run_firms_window(SMALL, start, NOW, "postgresql://x", "K")
    assert summary["day_range"] == firms_lib.ON_DEMAND_DAY_RANGE
    assert summary["tail_only"] is True


def test_main_firms_ok_with_tier_override(monkeypatch, capsys):
    _patch_firms_path(monkeypatch)
    monkeypatch.setenv("FIRMS_MAP_KEY", "K")

    def no_resolve():
        raise AssertionError("override must skip tier resolution")

    monkeypatch.setattr(db_module, "resolve_database_url", no_resolve)
    code = ingest_window.main(
        [
            "--bbox=-1.9,6.5,-1.4,6.9",
            "--start=2026-11-11",
            "--end=2026-11-14",
            "--database-url=postgresql://x",
        ]
    )
    assert code == 0


def test_main_firms_resolves_tier(monkeypatch, capsys):
    _patch_firms_path(monkeypatch)
    monkeypatch.setenv("FIRMS_MAP_KEY", "K")
    monkeypatch.setattr(db_module, "resolve_database_url", lambda: ("postgresql://x", "primary"))
    code = ingest_window.main(
        ["--bbox=-1.9,6.5,-1.4,6.9", "--start=2026-11-11", "--end=2026-11-14"]
    )
    assert code == 0
    import json

    body = json.loads(capsys.readouterr().out)
    assert body["tier"] == "primary"


def test_main_no_source_configured_is_usage_error(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.delenv("EE_PROJECT", raising=False)
    monkeypatch.delenv("EE_CREDENTIALS_PATH", raising=False)
    code = ingest_window.main(
        ["--bbox=-1.9,6.5,-1.4,6.9", "--start=2026-11-11", "--end=2026-11-14"]
    )
    assert code == 2


def test_main_rejects_bad_bbox():
    base = ["--start=2026-11-11", "--end=2026-11-14"]
    assert ingest_window.main(["--bbox=nope", *base]) == 2
    assert ingest_window.main(["--bbox=1,1,0,0", *base]) == 2
    flipped = ["--bbox=-1.9,6.5,-1.4,6.9", "--start=2026-11-14", "--end=2026-11-11"]
    assert ingest_window.main(flipped) == 2


def test_run_ee_window_chunks_long_ranges(monkeypatch):
    calls = []
    import scripts.ee_ingest as ee_ingest

    def fake_main(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(ee_ingest, "main", fake_main)
    start = NOW - timedelta(days=40)
    summary = ingest_window.run_ee_window(SMALL, start, NOW, "postgresql://x")
    assert summary["source"] == "ee"
    assert len(calls) == 2  # 41 days over a 31-day cap
    assert summary["failures"] == []
    assert "--database-url=postgresql://x" in calls[0]


def test_run_ee_window_reports_failed_chunks(monkeypatch):
    import scripts.ee_ingest as ee_ingest

    monkeypatch.setattr(ee_ingest, "main", lambda argv: 1)
    start = NOW - timedelta(days=3)
    summary = ingest_window.run_ee_window(SMALL, start, NOW, "postgresql://x")
    assert len(summary["failures"]) == 1
