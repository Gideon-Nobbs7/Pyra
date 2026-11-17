"""Gap-fill queue: unserved (bbox, window) misses and worker claims oldest-first."""

import logging

from app import db as db_module
from app import firms as firms_lib

log = logging.getLogger("pyra.ingest_jobs")

MAX_JOB_DEG2 = 500.0
MAX_JOB_DAYS = 366
MAX_ATTEMPTS = 5
ROUND_DP = 2

ENQUEUE_SQL = """
INSERT INTO ingest_jobs
  (min_lon, min_lat, max_lon, max_lat, start_date, end_date, status, updated_at)
VALUES
  (%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s,
   %(start_date)s, %(end_date)s, 'pending', now())
ON CONFLICT (min_lon, min_lat, max_lon, max_lat, start_date, end_date)
DO UPDATE SET status = 'pending', updated_at = now(), last_error = NULL
WHERE ingest_jobs.status = 'failed'
RETURNING id, status;
"""

CLAIM_SQL = """
UPDATE ingest_jobs
SET status = 'claimed', attempts = attempts + 1, updated_at = now()
WHERE id = (
  SELECT id FROM ingest_jobs
  WHERE status = 'pending' AND attempts < %(max_attempts)s
  ORDER BY created_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING id, min_lon, min_lat, max_lon, max_lat, start_date, end_date, attempts;
"""

COMPLETE_SQL = """
UPDATE ingest_jobs
SET status = %(status)s, last_error = %(error)s, updated_at = now()
WHERE id = %(id)s;
"""


def _connect(url):
    # Pooler-safe (no prepared statements).
    return db_module._try_connect(url)


def _rounded(bbox: list[float]) -> list[float]:
    return [round(float(v), ROUND_DP) for v in bbox]


def enqueue_job(bbox: list[float], start, end) -> str:
    """Enqueue of bbox + window"""
    rounded = _rounded(bbox)
    if firms_lib.bbox_deg2(rounded) > MAX_JOB_DEG2:
        return "skipped:area-too-wide"
    span_days = (end.date() - start.date()).days
    if span_days < 0 or span_days > MAX_JOB_DAYS:
        return "skipped:window-out-of-range"
    url, _ = db_module.resolve_database_url()
    params = {
        "min_lon": rounded[0],
        "min_lat": rounded[1],
        "max_lon": rounded[2],
        "max_lat": rounded[3],
        "start_date": start.date(),
        "end_date": end.date(),
    }
    with _connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(ENQUEUE_SQL, params)
            row = cur.fetchone()
        conn.commit()
    return "enqueued" if row else "exists"


def claim_job() -> dict | None:
    """Claim oldest pending job or None."""
    url, _ = db_module.resolve_database_url()
    with _connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(CLAIM_SQL, {"max_attempts": MAX_ATTEMPTS})
            row = cur.fetchone()
        conn.commit()
    return row


def complete_job(job_id: int, ok: bool, error: str | None = None) -> None:
    """Mark claimed job done/failed."""
    url, _ = db_module.resolve_database_url()
    with _connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                COMPLETE_SQL,
                {"status": "done" if ok else "failed", "error": error, "id": job_id},
            )
        conn.commit()
