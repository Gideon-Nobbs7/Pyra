"""Gap-fill queue: enqueue dedupe/caps, claim/complete, endpoint + worker wiring.

No live provider. No real Postgres: _connect is stubbed; one DB-gated test
below is skipped without DATABASE_URL.
"""

import os
from datetime import UTC, date, datetime, timedelta

import pytest

import app.db as db_module
import app.firms as firms_lib
import app.ingest_jobs as jobs_lib
from scripts import ingest_worker
from tests.conftest import get_client
from tests.test_db_read_path import FRESHNESS

NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
GHANA = [-1.9, 6.5, -1.4, 6.9]


class StubConn:
    """Minimal psycopg stand-in: records statements, replays queued rows."""

    def __init__(self, log, rows):
        self.log = log
        self._rows = list(rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.log.append(("execute", sql, params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def commit(self):
        self.log.append(("commit",))


def _stubbed(monkeypatch, rows, urls=None):
    log = []
    if urls is None:
        urls = []

    def fake_connect(url):
        urls.append(url)
        return StubConn(log, rows)

    monkeypatch.setattr(jobs_lib, "_connect", fake_connect)
    monkeypatch.setattr(db_module, "resolve_database_url", lambda: ("postgresql://x", "primary"))
    return log, urls


def test_enqueue_rounds_bbox_and_inserts(monkeypatch):
    log, urls = _stubbed(monkeypatch, [{"id": 3, "status": "pending"}])
    outcome = jobs_lib.enqueue_job([-1.901, 6.499, -1.399, 6.901], NOW, NOW)
    assert outcome == "enqueued"
    assert urls == ["postgresql://x"]
    _, sql, params = log[0]
    assert "ON CONFLICT" in sql
    assert (params["min_lon"], params["min_lat"], params["max_lon"], params["max_lat"]) == (
        -1.9,
        6.5,
        -1.4,
        6.9,
    )
    assert ("commit",) in log


def test_enqueue_exists_when_no_row_returned(monkeypatch):
    _stubbed(monkeypatch, [])
    assert jobs_lib.enqueue_job(GHANA, NOW, NOW) == "exists"


def test_enqueue_skips_wide_and_long_windows(monkeypatch):
    log, urls = _stubbed(monkeypatch, [{"id": 1}])
    assert jobs_lib.enqueue_job([-180.0, -90.0, 180.0, 90.0], NOW, NOW).startswith("skipped:")
    far = datetime(2020, 1, 1, tzinfo=UTC)
    assert jobs_lib.enqueue_job(GHANA, far, NOW).startswith("skipped:")
    assert urls == []  # no store touched for skipped jobs


def test_claim_and_complete(monkeypatch):
    job = {
        "id": 7,
        "min_lon": 0.0,
        "min_lat": 0.0,
        "max_lon": 1.0,
        "max_lat": 1.0,
        "start_date": NOW.date(),
        "end_date": NOW.date(),
        "attempts": 1,
    }
    log, _ = _stubbed(monkeypatch, [job])
    claimed = jobs_lib.claim_job()
    assert claimed["id"] == 7
    assert "FOR UPDATE SKIP LOCKED" in log[0][1]
    log.clear()
    jobs_lib.complete_job(7, True)
    _, _, params = log[0]
    assert params["status"] == "done" and params["id"] == 7
    jobs_lib.complete_job(7, False, "boom")
    _, _, params = log[2]
    assert params["status"] == "failed" and params["error"] == "boom"


def test_claim_empty_queue_returns_none(monkeypatch):
    _stubbed(monkeypatch, [])
    assert jobs_lib.claim_job() is None


def test_observations_miss_enqueues_user_bbox(monkeypatch):
    calls = []
    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", lambda *a: ([], False))
    monkeypatch.setattr(db_module, "fetch_count", lambda *a: 0)
    monkeypatch.setattr(db_module, "fetch_freshness", lambda: FRESHNESS)
    monkeypatch.setattr(firms_lib, "map_key", lambda: "")  # sync path declines fast

    def fake_enqueue(bbox, start, end):
        calls.append(bbox)
        return "enqueued"

    monkeypatch.setattr(jobs_lib, "enqueue_job", fake_enqueue)

    old = datetime(2024, 8, 17, 12, 0, 0, tzinfo=UTC)
    r = get_client().get(
        "/api/v1/observations",
        params={
            "start": (old - timedelta(days=7)).isoformat(),
            "end": old.isoformat(),
            "bbox": ",".join(str(v) for v in GHANA),
        },
    )
    assert r.status_code == 200
    assert r.json()["coverage_status"] == "empty"
    assert calls == [GHANA]


def test_observations_recent_small_miss_does_not_enqueue(monkeypatch):
    calls = []
    monkeypatch.setattr(db_module, "db_configured", lambda: True)
    monkeypatch.setattr(db_module, "fetch_page", lambda *a: ([], False))
    monkeypatch.setattr(db_module, "fetch_count", lambda *a: 0)
    monkeypatch.setattr(db_module, "fetch_freshness", lambda: FRESHNESS)
    monkeypatch.setattr(firms_lib, "map_key", lambda: "")  # sync path declines: no key
    monkeypatch.setattr(firms_lib, "_utcnow", lambda: NOW)
    monkeypatch.setattr(jobs_lib, "enqueue_job", lambda *a: calls.append(a) or "enqueued")

    r = get_client().get(
        "/api/v1/observations",
        params={
            "start": (NOW - timedelta(days=3)).isoformat(),
            "end": NOW.isoformat(),
            "bbox": ",".join(str(v) for v in GHANA),
        },
    )
    assert r.status_code == 200
    assert calls == []  # sync path owns recent+small windows


def test_worker_runs_claimed_jobs(monkeypatch):
    queue = [
        {
            "id": 1,
            "min_lon": 0.0,
            "min_lat": 0.0,
            "max_lon": 1.0,
            "max_lat": 1.0,
            "start_date": date(2024, 8, 10),
            "end_date": date(2024, 8, 16),
            "attempts": 1,
        },
        {
            "id": 2,
            "min_lon": 2.0,
            "min_lat": 2.0,
            "max_lon": 3.0,
            "max_lat": 3.0,
            "start_date": date(2024, 8, 10),
            "end_date": date(2024, 8, 16),
            "attempts": 2,
        },
    ]
    runs = []
    done = []

    import app.ingest_jobs as jobs_module

    monkeypatch.setattr(jobs_module, "claim_job", lambda: queue.pop(0) if queue else None)
    monkeypatch.setattr(
        jobs_module, "complete_job", lambda i, ok, error=None: done.append((i, ok, error))
    )
    monkeypatch.setattr(ingest_worker.ingest_window, "main", lambda argv: runs.append(argv) or 0)

    results = ingest_worker.run_claimed_jobs(max_jobs=5, timeout_s=30)
    assert [r["id"] for r in results] == [1, 2]
    assert done == [(1, True, None), (2, True, None)]
    assert runs[0][0] == "--bbox=0.0,0.0,1.0,1.0"
    assert "--start=2024-08-10" in runs[0] and "--end=2024-08-16" in runs[0]


def test_worker_records_failed_jobs(monkeypatch):
    import app.ingest_jobs as jobs_module

    job = {
        "id": 9,
        "min_lon": 0.0,
        "min_lat": 0.0,
        "max_lon": 1.0,
        "max_lat": 1.0,
        "start_date": date(2024, 8, 10),
        "end_date": date(2024, 8, 11),
        "attempts": 1,
    }
    done = []
    monkeypatch.setattr(jobs_module, "claim_job", lambda: job if done == [] else None)
    monkeypatch.setattr(
        jobs_module, "complete_job", lambda i, ok, error=None: done.append((i, ok, error))
    )
    monkeypatch.setattr(ingest_worker.ingest_window, "main", lambda argv: 1)

    results = ingest_worker.run_claimed_jobs(max_jobs=3, timeout_s=30)
    assert [r["exit"] for r in results] == [1]
    assert done == [(9, False, "ingest_window exit 1")]


def test_worker_skips_job_phase_without_store(monkeypatch):
    import app.ingest_jobs as jobs_module

    def no_store():
        raise ConnectionError("no database configured")

    monkeypatch.setattr(jobs_module, "claim_job", no_store)
    assert ingest_worker.run_claimed_jobs() == []


LIVE_DB = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs PostGIS DATABASE_URL")


@LIVE_DB
def test_enqueue_roundtrip_against_postgres():
    import psycopg

    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    outcome = jobs_lib.enqueue_job(GHANA, NOW, NOW)
    assert outcome in ("enqueued", "exists")
