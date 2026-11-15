"""Long-running ingest worker: rolling recent windows for WATCH_BBOXES.

Each tick ingests the recent window for every configured watch area
(FIRMS tail; EE only if an area's window falls outside FIRMS bounds) and
upserts into whichever database tier is reachable (primary, fallback,
local). The API serves worker-written rows through its normal read path;
its short-TTL cache picks them up without a restart.

Runs two ways: standalone (`uv run python scripts/ingest_worker.py`) or
inside the API process (FastAPI lifespan starts `serve()` in a thread when
WORKER_ENABLED=1, so one uvicorn owns both and they stop together).

Usage (from backend/):
  uv run python scripts/ingest_worker.py --once
  WATCH_BBOXES="Tamale:-2.2,8.05,0.52,10.75;Ghana:-3.3,4.5,1.2,11.2" \\
    uv run python scripts/ingest_worker.py --interval 3600

Env (also read from the repo-root .env via app.settings):
  WORKER_ENABLED   1 to run inside the API process (default 0; standalone
                   script runs regardless)
  WATCH_BBOXES     "Label:min_lon,min_lat,max_lon,max_lat;..." (required)
  WORKER_INTERVAL_S  seconds between ticks (default 3600, --interval wins)
  WORKER_RECENT_DAYS recent window length in days (default 7, --recent-days wins)
  WORKER_MAX_JOBS  gap-fill jobs claimed per tick (default 3)

Exit codes: 0 all areas ok, 1 any area failed (tick exit for --once/cron).
"""

import argparse
import logging
import signal
import sys
import threading
import time
from datetime import UTC, datetime, timedelta

from app.settings import get_settings
from scripts import ingest_window

log = logging.getLogger("pyra.ingest_worker")

_stop = False


def request_stop() -> None:
    """Ask the loop to finish the current area/job and exit. Idempotent."""
    global _stop
    _stop = True


def _handle_stop(signum, frame):  # noqa: ARG001
    request_stop()
    log.info("shutdown requested (signal %s); finishing the current area", signum)


def parse_watch_bboxes(value: str) -> list[tuple[str, list[float]]]:
    """Parse 'Label:bbox;...' entries. Invalid entries are skipped with a warning."""
    areas = []
    for entry in (value or "").split(";"):
        entry = entry.strip()
        if not entry:
            continue
        label, sep, bbox_raw = entry.partition(":")
        label = label.strip()
        if not sep or not label:
            log.warning("skipping watch entry with no label: %r", entry)
            continue
        try:
            parts = [float(p) for p in bbox_raw.split(",")]
        except ValueError:
            log.warning("skipping watch entry with non-numeric bbox: %r", entry)
            continue
        if len(parts) != 4 or not (parts[0] < parts[2] and parts[1] < parts[3]):
            log.warning("skipping watch entry with invalid bbox: %r", entry)
            continue
        areas.append((label, parts))
    return areas


def run_once(
    areas: list[tuple[str, list[float]]], recent_days: int, timeout_s: int
) -> dict[str, int]:
    """Ingest the recent window for each watch area. Returns {label: exit_code}."""
    end = datetime.now(UTC)
    start = end - timedelta(days=max(1, recent_days) - 1)
    results = {}
    for label, bbox in areas:
        if _stop:
            log.info("stopping before %s", label)
            break
        log.info("area %s bbox=%s window=%s..%s", label, bbox, start.date(), end.date())
        code = ingest_window.main(
            [
                f"--bbox={','.join(str(v) for v in bbox)}",
                f"--start={start.date().isoformat()}",
                f"--end={end.date().isoformat()}",
                f"--timeout={timeout_s}",
            ]
        )
        results[label] = code
        if code != 0:
            log.warning("area %s finished with exit %d", label, code)
    return results


_jobs_table_hinted = False


def run_claimed_jobs(max_jobs: int = 3, timeout_s: int = 30) -> list[dict]:
    """Claim user gap-fill jobs oldest-first and run each through ingest_window."""
    global _jobs_table_hinted
    from app import ingest_jobs as jobs_lib

    results = []
    for _ in range(max(1, max_jobs)):
        try:
            job = jobs_lib.claim_job()
        except Exception as exc:
            if getattr(exc, "pgcode", "") == "42P01":
                if not _jobs_table_hinted:
                    log.warning("ingest_jobs table missing; apply schema.sql to enable gap-fill")
                    _jobs_table_hinted = True
                return results
            log.warning("job claim failed: %s", exc)
            return results
        if job is None:
            return results
        bbox = [job["min_lon"], job["min_lat"], job["max_lon"], job["max_lat"]]
        log.info(
            "claimed job %s bbox=%s window=%s..%s (attempt %s)",
            job["id"],
            bbox,
            job["start_date"],
            job["end_date"],
            job["attempts"],
        )
        code = ingest_window.main(
            [
                f"--bbox={','.join(str(v) for v in bbox)}",
                f"--start={job['start_date'].isoformat()}",
                f"--end={job['end_date'].isoformat()}",
                f"--timeout={timeout_s}",
            ]
        )
        ok = code == 0
        try:
            jobs_lib.complete_job(job["id"], ok, None if ok else f"ingest_window exit {code}")
        except Exception as exc:
            log.warning("job %s completion not recorded: %s", job["id"], exc)
        results.append({"id": job["id"], "exit": code})
        if _stop:
            break
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rolling ingest worker for watch areas")
    parser.add_argument("--once", action="store_true", help="single tick, then exit")
    parser.add_argument("--interval", type=int, default=None, help="seconds between ticks")
    parser.add_argument("--recent-days", type=int, default=None, help="recent window length")
    parser.add_argument("--timeout", type=int, default=30, help="FIRMS fetch timeout seconds")
    parser.add_argument(
        "--watch",
        default=None,
        help="override WATCH_BBOXES ('Label:bbox;...')",
    )
    return parser


def tick(
    areas: list[tuple[str, list[float]]],
    recent_days: int,
    timeout_s: int,
    max_jobs: int = 3,
) -> int:
    """One tick: watch areas, then claimed gap-fill jobs. 0 when all ok."""
    results = run_once(areas, recent_days, timeout_s)
    failed = {label: code for label, code in results.items() if code != 0}
    claimed = run_claimed_jobs(max_jobs=max_jobs, timeout_s=timeout_s)
    claimed_failed = [job for job in claimed if job["exit"] != 0]
    log.info(
        "tick done: %d ok, %d failed, %d gap-fill jobs (%d failed)",
        len(results) - len(failed),
        len(failed),
        len(claimed),
        len(claimed_failed),
    )
    return 1 if failed or claimed_failed else 0


def serve(
    interval_s: int,
    areas: list[tuple[str, list[float]]],
    recent_days: int,
    timeout_s: int = 30,
    max_jobs: int = 3,
) -> int:
    """Loop ticks until request_stop(). Shared by standalone and API-lifespan runs."""
    log.info(
        "worker watching %d area(s), every %ds, recent window %dd",
        len(areas),
        interval_s,
        recent_days,
    )
    worst = 0
    while not _stop:
        worst = max(worst, tick(areas, recent_days, timeout_s, max_jobs))
        deadline = time.monotonic() + interval_s
        while not _stop and time.monotonic() < deadline:
            time.sleep(min(5, deadline - time.monotonic()))
    log.info("worker stopped")
    return worst


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    settings = get_settings()
    watch_raw = args.watch if args.watch is not None else settings.watch_bboxes
    areas = parse_watch_bboxes(watch_raw)
    if not areas and args.once:
        # A bare --once with nowhere to watch is a usage error; the daemon
        # and lifespan paths may legitimately run area-less (gap-fill only).
        print("no valid watch areas (WATCH_BBOXES or --watch)", file=sys.stderr)
        return 2
    interval = args.interval or settings.worker_interval_s
    recent_days = args.recent_days or settings.worker_recent_days
    if interval < 60:
        print("--interval/ WORKER_INTERVAL_S must be >= 60s (provider quota)", file=sys.stderr)
        return 2
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT, _handle_stop)

    if args.once:
        return tick(areas, recent_days, args.timeout)
    return serve(interval, areas, recent_days, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
