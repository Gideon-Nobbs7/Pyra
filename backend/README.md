# Pyra backend (M1 scaffold)

FastAPI + Pydantic + PostgreSQL/PostGIS + bounded in-process cache.
M1 serves labelled synthetic fixtures so frontend integration is real
before FIRMS ingest. No live provider calls.

## Quick start

Bash:
```bash
python -m venv .venv && source .venv/bin/activate
uv sync --extra dev || pip install -e ".[dev]"
uv run uvicorn app.main:app --reload
```

PowerShell:
```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

Health: `GET /api/v1/health`
Observations: `GET /api/v1/observations?start=2024-08-01T00:00:00Z&end=2024-08-31T23:59:59Z&bbox=22.9,37.7,24.3,38.5&limit=100`
Metadata: `GET /api/v1/metadata`

## Env

See `../.env.example` (root). `DATABASE_URL` unset means `database: not_configured` and fixtures serve reads. Once PostGIS is up, copy root `.env.example` to `.env` and set values. The API and worker auto-load root `.env` via `app/settings.py` (real env vars still win); the older `ingest_firms.py` / `refresh_nrt.sh` scripts still need it exported (`set -a; source ../.env; set +a`).

Tiered stores: `DATABASE_URL` is primary (Cloud SQL), `DATABASE_URL_FALLBACK`
Supabase second, `DATABASE_URL_LOCAL` local Compose last. Reads fail over down
the chain; `freshness.store` names whichever store answered (`primary`,
`fallback`, or `local`) and its timestamp tells the truth about staleness.
Fallbacks are separate datasets that may lag — no replication, by design.
Ingest targets the primary unless `--database-url` overrides it.

Schema: `psql $DATABASE_URL -f schema.sql` then `SELECT PostGIS_Version();`

## FIRMS ingest (Ghana baseline 2018–present + NRT tail)

One-time setup: Earthdata Login → request `FIRMS_MAP_KEY` on the FIRMS
web-services page → put it in root `.env` (server-side only, never frontend).

Archive base (history to ~7 days ago; files arrive by email from Archive Download):

```bash
set -a; source ../.env; set +a
uv run python scripts/ingest_firms.py archive --csv ghana_modis_2024.csv --source modis --bbox=-3.3,4.5,1.2,11.2
uv run python scripts/ingest_firms.py archive --csv ghana_viirs_2024.csv --source viirs --bbox=-3.3,4.5,1.2,11.2
```

NRT tail (manual now; same command fits cron/systemd later):

```bash
uv run python scripts/ingest_firms.py api --bbox=-3.3,4.5,1.2,11.2 --day-range 5 --date 2026-11-14
```

Product-string drift guard (FIRMS renames products over time; the strings live
in `FIRMS_API_PRODUCTS`, not just code — see root `.env.example`):

```bash
uv run python scripts/ingest_firms.py api --bbox=-3.3,4.5,1.2,11.2 --date 2026-11-14 --check
```

`--check` probes each product with a 1-day pull, writes nothing, and exits 1
on rename/header drift. A failed product fails the run (exit 1) while healthy
products still commit — partial success, loud signal. Run it in CI/cron.

Background refresh (same command cron/systemd can own; `--check` gates the ingest):

```bash
./scripts/refresh_nrt.sh >> /var/log/pyra-refresh.log 2>&1
# cron daily 06:00 UTC: 0 6 * * * /path/to/Pyra/backend/scripts/refresh_nrt.sh >> /var/log/pyra-refresh.log 2>&1
```

`NRT_BBOX` env overrides the default Ghana bbox. Restart the API process after
a successful refresh so the in-process cache drops.

## Background worker (rolling ingest + user gap-fill)

Set `WORKER_ENABLED=1` in root `.env`: the API lifespan starts the worker
in a thread, so one `uvicorn` owns both — stopping/restarting the server
stops/restarts the worker. Standalone runs still work for cron/manual use:

```bash
# one tick over every watch area, then exit (cron-friendly)
uv run python scripts/ingest_worker.py --once
# long-running daemon: ticks every WORKER_INTERVAL_S (default 3600, min 60)
WATCH_BBOXES="Tamale:-2.2,8.05,0.52,10.75;Ghana:-3.3,4.5,1.2,11.2" uv run python scripts/ingest_worker.py
# single window, routed automatically (recent+small → FIRMS tail, else EE raster)
uv run python scripts/ingest_window.py --bbox=-3.3,4.5,1.2,11.2 --start 2024-08-10 --end 2024-08-17
```

`WATCH_BBOXES` (or `--watch`, same format) also lives in root `.env`.
Each tick ingests the recent window per area and then claims user gap-fill
jobs oldest-first (up to `WORKER_MAX_JOBS`, default 3). A gap-fill job is
enqueued automatically when a query's locked bbox + window has no stored
data and the synchronous path cannot cover it (history or areas over
50 deg², capped at 500 deg² / 366 days). Jobs are deduped per rounded bbox
+ window, retried to 5 attempts, and run through `ingest_window` into
whichever tier answers (primary → fallback → local). Nothing new appears
in the UI; freshness timestamps prove the fill.

First run on an existing database: `psql $DATABASE_URL -f schema.sql`
adds the rerunnable `ingest_jobs` table. Worker-written rows are picked up
through the normal cache TTL (60 s recent) — no API restart needed.

## Read path (cache → DB → bounded live fetch)

1. In-process cache hit → return (no DB, no provider).
2. Postgres hit → return + warm cache.
3. Postgres miss on a recent (≤10 days), small (≤50 deg²) query with `FIRMS_MAP_KEY`
   set and the 60 s provider rate limit clear → one bounded FIRMS pull (≤5-day
   window), upsert, re-read from DB, warm cache. Next identical visit stops at step 1.
4. Otherwise serve the stored result: `empty` with honest copy, `unavailable`
   outside fixture coverage (fixture mode), or 503 if the store is down.

History is never fetched live; it arrives via archive ingest. Concurrent
identical queries coalesce on the per-key single-flight lock.

Cache backend: `functools.lru_cache` inside `app/cache.py` (`LruCacheBackend`,
selected by `CACHE_BACKEND`, default `lru`). To swap it (Redis, second process,
no-op for tests), implement the `CacheBackend` protocol and add a branch to
`build_cache()` — callers only use `get`/`put`/`invalidate`/`stats`, so nothing
else changes. Watch it working via `cache.stats()["lru"]` (hits/misses/currsize).

After a direct ingest (scripts, `refresh_nrt.sh`), restart the API process so
the in-process cache drops. Worker-written rows need no restart (short TTL).
Method, field mapping, and the synthesized record-ID rule live in
`docs/harmonization.md`.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

CI uses `postgis/postgis:16-3.4-alpine` and `DATABASE_URL=postgresql://pyra:pyra@localhost:5432/pyra_test`.

Synthetic fixtures in `fixtures/synthetic_attica_aug2024.json` are labelled and must never be presented as FIRMS data.
