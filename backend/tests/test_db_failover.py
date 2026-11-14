"""Tiered resolution: Cloud SQL primary, Supabase fallback, local last resort."""

from datetime import UTC, datetime

import pytest

import app.db as db_module


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args):
        pass

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor({"latest": datetime(2024, 9, 1, 12, 0, 0, tzinfo=UTC), "n": 42})


def _boom(url, timeout=3):
    raise ConnectionError(f"refused: {url[:20]}")


def test_primary_wins_when_reachable(monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgres://primary/db")
    monkeypatch.setattr(db_module, "FALLBACK_URL", "postgres://fallback/db")
    monkeypatch.setattr(db_module, "LOCAL_URL", "postgres://local/db")
    monkeypatch.setattr(db_module, "_try_connect", lambda url, timeout=3: _FakeConn())
    db_module.reset_resolution()
    assert db_module.resolve_database_url() == ("postgres://primary/db", "primary")


def test_fallback_used_when_primary_down(monkeypatch):
    def fake_connect(url, timeout=3):
        if "primary" in url:
            raise ConnectionError("primary down")
        return _FakeConn()

    monkeypatch.setattr(db_module, "DATABASE_URL", "postgres://primary/db")
    monkeypatch.setattr(db_module, "FALLBACK_URL", "postgres://fallback/db")
    monkeypatch.setattr(db_module, "LOCAL_URL", "postgres://local/db")
    monkeypatch.setattr(db_module, "_try_connect", fake_connect)
    db_module.reset_resolution()
    assert db_module.resolve_database_url() == ("postgres://fallback/db", "fallback")


def test_local_used_when_primary_and_fallback_down(monkeypatch):
    def fake_connect(url, timeout=3):
        if "local" in url:
            return _FakeConn()
        raise ConnectionError("cloud down")

    monkeypatch.setattr(db_module, "DATABASE_URL", "postgres://primary/db")
    monkeypatch.setattr(db_module, "FALLBACK_URL", "postgres://fallback/db")
    monkeypatch.setattr(db_module, "LOCAL_URL", "postgres://local/db")
    monkeypatch.setattr(db_module, "_try_connect", fake_connect)
    db_module.reset_resolution()
    assert db_module.resolve_database_url() == ("postgres://local/db", "local")


def test_all_down_raises(monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgres://primary/db")
    monkeypatch.setattr(db_module, "FALLBACK_URL", "postgres://fallback/db")
    monkeypatch.setattr(db_module, "LOCAL_URL", "postgres://local/db")
    monkeypatch.setattr(db_module, "_try_connect", _boom)
    db_module.reset_resolution()
    with pytest.raises(ConnectionError, match="all database stores unreachable"):
        db_module.resolve_database_url()


def test_decision_is_sticky(monkeypatch):
    calls = []

    def fake_connect(url, timeout=3):
        calls.append(url)
        return _FakeConn()

    monkeypatch.setattr(db_module, "DATABASE_URL", "postgres://primary/db")
    monkeypatch.setattr(db_module, "FALLBACK_URL", "")
    monkeypatch.setattr(db_module, "_try_connect", fake_connect)
    db_module.reset_resolution()
    db_module.resolve_database_url()
    db_module.resolve_database_url()
    assert len(calls) == 1  # second call served from sticky decision
    db_module.reset_resolution()


def test_freshness_names_fallback_store(monkeypatch):
    def fake_connect(url, timeout=3):
        if "primary" in url:
            raise ConnectionError("primary down")
        return _FakeConn()

    monkeypatch.setattr(db_module, "DATABASE_URL", "postgres://primary/db")
    monkeypatch.setattr(db_module, "FALLBACK_URL", "postgres://fallback/db")
    monkeypatch.setattr(db_module, "_try_connect", fake_connect)
    db_module.reset_resolution()
    freshness = db_module.fetch_freshness()
    assert freshness["store"] == "fallback"
    assert freshness["row_count"] == 42
    assert freshness["synthetic"] is False
