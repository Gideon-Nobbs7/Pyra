"""ingest_worker: watch-area parsing and tick behavior. No live provider, no real DB."""

from scripts import ingest_worker


def test_parse_watch_bboxes():
    areas = ingest_worker.parse_watch_bboxes("Tamale:-2.2,8.05,0.52,10.75;Ghana:-3.3,4.5,1.2,11.2")
    assert areas == [
        ("Tamale", [-2.2, 8.05, 0.52, 10.75]),
        ("Ghana", [-3.3, 4.5, 1.2, 11.2]),
    ]


def test_parse_watch_bboxes_skips_invalid():
    areas = ingest_worker.parse_watch_bboxes("NoLabel;Bad:1,2,3;Inverted:1,1,0,0;Ok:0,0,1,1")
    assert areas == [("Ok", [0.0, 0.0, 1.0, 1.0])]
    assert ingest_worker.parse_watch_bboxes("") == []


def test_run_once_calls_window_per_area(monkeypatch):
    calls = []

    def fake_main(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(ingest_worker.ingest_window, "main", fake_main)
    areas = [("A", [0.0, 0.0, 1.0, 1.0]), ("B", [2.0, 2.0, 3.0, 3.0])]
    results = ingest_worker.run_once(areas, 7, 30)
    assert results == {"A": 0, "B": 0}
    assert len(calls) == 2
    assert calls[0][0] == "--bbox=0.0,0.0,1.0,1.0"
    assert any(part.startswith("--start=") for part in calls[0])
    assert any(part.startswith("--end=") for part in calls[0])


def test_run_once_reports_failures(monkeypatch):
    monkeypatch.setattr(ingest_worker.ingest_window, "main", lambda argv: 1)
    results = ingest_worker.run_once([("A", [0.0, 0.0, 1.0, 1.0])], 7, 30)
    assert results == {"A": 1}


def test_main_once_ok(monkeypatch):
    monkeypatch.setattr(ingest_worker.ingest_window, "main", lambda argv: 0)
    code = ingest_worker.main(["--once", "--watch=Ok:0,0,1,1"])
    assert code == 0


def test_main_once_reports_area_failure(monkeypatch):
    monkeypatch.setattr(ingest_worker.ingest_window, "main", lambda argv: 1)
    code = ingest_worker.main(["--once", "--watch=Ok:0,0,1,1"])
    assert code == 1


def test_main_rejects_missing_areas_and_fast_interval():
    assert ingest_worker.main(["--once"]) == 2
    assert ingest_worker.main(["--once", "--watch=Ok:0,0,1,1", "--interval=5"]) == 2


def test_worker_disabled_by_default(monkeypatch):
    monkeypatch.delenv("WORKER_ENABLED", raising=False)
    from app.settings import get_settings

    assert get_settings().worker_enabled is False


def test_tick_aggregates_watch_and_jobs(monkeypatch):
    monkeypatch.setattr(ingest_worker, "run_once", lambda areas, days, timeout: {"A": 0, "B": 1})
    monkeypatch.setattr(
        ingest_worker,
        "run_claimed_jobs",
        lambda max_jobs=3, timeout_s=30: [{"id": 1, "exit": 0}, {"id": 2, "exit": 1}],
    )
    assert ingest_worker.tick([("A", [0.0, 0.0, 1.0, 1.0])], 7, 30) == 1
    monkeypatch.setattr(ingest_worker, "run_once", lambda *a: {"A": 0})
    monkeypatch.setattr(ingest_worker, "run_claimed_jobs", lambda max_jobs=3, timeout_s=30: [])
    assert ingest_worker.tick([], 7, 30) == 0


def test_serve_exits_when_stopped():
    ingest_worker.request_stop()
    try:
        assert ingest_worker.serve(3600, [], 7) == 0
    finally:
        ingest_worker._stop = False


def test_lifespan_starts_and_stops_worker(monkeypatch):
    from tests.conftest import get_client

    monkeypatch.setenv("WORKER_ENABLED", "1")
    for key in ("WORKER_INTERVAL_S", "WORKER_RECENT_DAYS", "WORKER_MAX_JOBS", "WATCH_BBOXES"):
        monkeypatch.delenv(key, raising=False)
    calls = []
    monkeypatch.setattr(ingest_worker, "serve", lambda *a: calls.append(a) or 0)
    with get_client():
        pass
    assert len(calls) == 1
    interval, areas, days, timeout_s, max_jobs = calls[0]
    from app.settings import get_settings

    defaults = get_settings()
    assert (interval, days, timeout_s, max_jobs) == (
        defaults.worker_interval_s,
        defaults.worker_recent_days,
        30,
        defaults.worker_max_jobs,
    )
    assert areas == []
    ingest_worker._stop = False


def test_main_reads_watch_list_from_env(monkeypatch):
    monkeypatch.setattr(ingest_worker.ingest_window, "main", lambda argv: 0)
    monkeypatch.setenv("WATCH_BBOXES", "EnvArea:0,0,1,1")
    assert ingest_worker.main(["--once"]) == 0
