# Backend agent guide

You are the backend agent for Pyra. Work only in `backend/`. The frontend agent owns `frontend/`; do not edit it. Read the root `AGENTS.md` first for scope, milestones, data integrity, and the observation schema. If the two files disagree, the root wins on product rules, and this file wins on backend mechanics.

**Hard boundary:** your writes stay inside `backend/`. Reading other trees is allowed when you need context. Do not edit root-level Docker, CI, or deployment files without the task saying so.

Route substantive work through the `godfile-navigator` skill first when your environment provides it; otherwise follow this guide and the root guide.

## What the backend must do

Serve harmonized MODIS and VIIRS satellite hotspot observations and summaries by time and geographic area. Own two-product ingestion and harmonization, storage, validation, filtering, pagination, baseline comparison, CSV export, metadata, freshness, the read-through cache, and consistent errors. The frontend must be able to tell four things apart: zero matching detections, unavailable coverage, a request failure, and stale last-known-good data.

## Stack and setup

Follow the MVP stack: Python, FastAPI, Pydantic, PostgreSQL with PostGIS, and a bounded in-process cache. Use `psycopg` or `asyncpg` with parameterized SQL for the first version. Add SQLAlchemy or Alembic only if the schema starts changing often enough to justify them. Use pytest with HTTPX.

When you scaffold, check the current official docs for the packages and versions you choose, then record them in the project manifest and lockfile. Pick one dependency workflow and document it. Use a PostGIS-enabled Postgres image in Compose, such as `postgis/postgis:16-3.4-alpine`, or install the extension during setup. Every image in the demo stack must use its smallest variant. Do not add Celery or Redis until a background job or multiple workers need them.

Configuration comes from environment variables. Document the backend keys in `backend/.env.example` or ask DevOps to add them to a root `.env.example`. No secrets in either file. Provider credentials stay server-side.

Typical commands once scaffolded. Replace them with the real ones in the backend README.

- Create and activate a virtual environment. Bash: `python -m venv .venv && source .venv/bin/activate`. PowerShell: `python -m venv .venv; .venv\Scripts\Activate.ps1`.
- Install dependencies with the chosen tool.
- Run the API: `uvicorn app.main:app --reload`.
- Run tests: `pytest`.
- Run lint and format with the chosen tool.
- Initialize or update the Postgres schema with the project's schema script or migration tool. Enable PostGIS there with `CREATE EXTENSION IF NOT EXISTS postgis;`.

Docker commands belong to the human, not the agent. The human runs `docker compose up --build` and the rest of the `docker` and `docker compose` commands from the repo root. The human already runs a local Postgres (alpine); use it and do not install another. Confirm PostGIS availability on it with `SELECT PostGIS_Version();`; if it is missing, use the plain latitude and longitude bbox path until DevOps provides a PostGIS-enabled database. Do not assume a database is running until the human confirms it.

The README command must be the one that works. Do not claim you ran a command you did not run.

## API contract

Base path `/api/v1`. Endpoints from the PRD:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | liveness and readiness, with no secrets or internals |
| GET | `/api/v1/observations` | time and bbox filtered records, `limit` and `cursor` |
| GET | `/api/v1/observations/{id}` | one record, 404 when absent |
| GET | `/api/v1/summary` | counts by `interval` (`month`, `year`) for the same filters |
| GET | `/api/v1/comparison` | selected period against the historical baseline, with anomalies and a comparability warning |
| GET | `/api/v1/observations/export` | CSV of the observations for the search, same filters, bounded rows |
| GET | `/api/v1/metadata` | products, coverage, freshness, fields, limitations |

Validate every input:

- `start` and `end` are ISO timestamps normalized to UTC. Reject `end < start`.
- `bbox` is `min_lon,min_lat,max_lon,max_lat` with valid ranges and correct ordering.
- `limit` is bounded. `cursor` is opaque and validated.
- Unknown or invalid parameters are rejected. Never silently ignore a filter.

Apply time and area together when both are supplied.

Responses include the filters applied, time boundaries, source and product, metric definition, freshness (latest successful ingestion), pagination, and coverage status. Distinguish:

- **Empty:** a successful response with an empty observation list and a clear reason.
- **Unavailable:** a documented response or error saying coverage is missing for the period.
- **Error:** a documented 4xx or 5xx envelope for invalid input or failed retrieval. Never return an empty list for a failure.

Keep one error envelope across endpoints. Propose its definition and any changes to the orchestrator, who maintains `docs/api-contract.md`. The frontend depends on stable shapes. Change them only by agreement. Example payloads in docs are examples unless they use real source-backed records.

Prefer one origin. Serve `frontend/dist` from the same FastAPI app with `app.frontend()` or `StaticFiles` and a SPA fallback. The demo then needs no CORS. Add CORS only if the frontend is split onto another origin. The frontend build is produced by the frontend agent; serve it, do not edit its source.

## Ingestion and storage

Workflow:

1. Fetch each product through the provider's documented interface.
2. Record source, product, retrieval time, and requested coverage.
3. Validate coordinates, timestamps, and required fields.
4. Normalize timestamps to UTC without changing their meaning.
5. Preserve source identifiers and original properties.
6. Harmonize per `docs/harmonization.md`: map native confidence, FRP, brightness, day/night, and overpass fields onto the harmonized record. Never silently drop a product's records to make the counts match.
7. Deduplicate by `(source, source_record_id)` or a documented composite key.
8. Upsert idempotently.
9. Record success or failure and the latest successful ingestion time.
10. Expose stored observations to API queries.
11. Retain last-known-good data during upstream outages and label its freshness accurately.

Use the root guide's minimum observation fields. `observed_at` and `ingested_at` stay distinct. Nullable fields stay null. Do not turn missing measurements into zero.

Store the records in PostgreSQL. Use `timestamptz` for `observed_at` and `ingested_at`, `double precision` for coordinates and FRP, and `jsonb` for `raw_properties`. Add a unique constraint on `(source, source_record_id)` or a documented composite key, then upsert with `INSERT ... ON CONFLICT ... DO UPDATE`. Use parameterized SQL.

Enable PostGIS with `CREATE EXTENSION IF NOT EXISTS postgis;`. Use a `geography(Point, 4326)` or `geometry(Point, 4326)` column for the area filter. A plain latitude and longitude bbox is acceptable if it is simpler and measures faster. Index `observed_at` and the spatial column, or `(latitude, longitude)`. Add `source` or `product` indexes only if the query uses them. Measure with `EXPLAIN` before claiming performance.

The first schema can be one `schema.sql` file or a small migration. Use a migration tool if the schema starts changing. Keep migrations reversible.

Use MODIS and VIIRS for the MVP. Record each product's name and version, satellite and instrument, spatial coverage and resolution, historical range, latency, confidence semantics, FRP units, and known limitations. Verify the exact FIRMS collections in the FIRMS docs before implementing (MODIS Collection 6.1 and the VIIRS 375m active-fire products are the expected starting point). The harmonization method lives in `docs/harmonization.md`: it states how resolutions, sensitivities, and observation schedules are reconciled, what a harmonized count means, and when sensor-of-origin comparisons are not valid. Do not combine products without that documented method. Do not fabricate missing fields.

Do not have the API call the upstream provider on every timeline move. Historical data belongs in the database. Upstream access belongs in ingestion.

For the demo, ingest a bounded MODIS and VIIRS dataset into Postgres and ship a seed or dump with the app. Run the ingestion script manually before the demo; the API never calls the provider at request time. After ingestion, invalidate or version the cache.

## Read path and cache

The read path is memory first, then Postgres.

1. Normalize the request filters. Build a cache key from products, start, end, bbox, limit, and cursor or offset. Normalize number formatting so equivalent requests hit the same key. If you round bbox to a grid to improve hits, filter the cached records back to the exact requested bbox before returning.
2. Check the in-process cache. On a hit, return the cached result.
3. On a miss, query Postgres. On a hit, put the result in the cache and return.
4. On a database miss, return empty or unavailable per the contract. Do not call the provider synchronously from the request path. If on-demand fetch is added, make it a bounded ingestion job with rate limits and a bounded area and time range. It writes to Postgres, warms the cache, and surfaces loading, empty, unavailable, and error states.
5. After ingestion, invalidate or version the affected cache entries. Warm the latest window if useful. A cache entry must carry the data's freshness, not the time it was cached.

Use a bounded `TTLCache` or LRU with a size limit. Use a short TTL for recent windows and a longer TTL for closed historical windows. Invalidate after ingestion regardless of TTL. Cache successful results; short-TTL negative results are optional. Use a single-flight lock per key so concurrent misses do not stampede the database. Run one API worker for the MVP. Add Redis only when multiple workers or instances make an in-process cache inconsistent. Log cache hits, misses, and database query time.

## Correctness rules

- Empty, unavailable, error, and stale stay separate in the payload, the logs, and the docs.
- A cache hit must return the same state as a database result. Do not let cached data hide a newer ingestion. When in doubt, invalidate.
- Summary counts need an explicit metric definition and interval. Missing coverage must not read as zero.
- Never label detection counts as fires, burned area, or fire perimeters.
- Comparison pits the selected period against the historical baseline for the same area and window. An anomaly is the observed deviation from that baseline, never a forecast. Never divide by a zero baseline. Include a comparability warning. Do not compare products or processing versions without a documented method.
- CSV export carries the same filters and freshness as the search. It is bounded and documented; beyond the limit, reject or truncate with a clear message. Example rows in docs are examples unless they use real source-backed records.
- Keep observation time separate from ingestion time in every response.
- If a selected record disappears from a result set, the API does not preserve a ghost record. Make the absence unambiguous so the frontend can clear the selection.

## Security and operations

- Validate at the boundary. Use parameterized queries. Never build SQL with string concatenation.
- Restrict CORS to the frontend origin or origins from configuration.
- Do not return stack traces, credentials, or upstream URLs containing keys.
- Keep provider keys in environment variables or secret storage. Never log them. Never commit `.env`.
- Keep database credentials in environment variables or secret storage. Do not expose the Postgres port publicly; keep it on the Compose network or a private connection. Do not serve database dumps or connection strings.
- Use a least-privilege database user for the API. Keep migration and ingestion credentials separate when practical. Bound the connection pool.
- Rate-limit public deployments. Keep the app usable without registration. Do not collect precise user location automatically.
- Use structured logs with request id, route, status, duration, and filters. Exclude secrets and personal data.
- The health endpoint must not leak internals.
- Treat upstream data as untrusted input: validate it, bound payload sizes, set timeouts, and fail clearly.
- If you add upstream fetches, allowlist hosts to avoid SSRF.
- Last-known-good data stays available during outages, with its true ingestion time.

## Testing

Use pytest and HTTPX. Cover:

- parameter validation: dates, bbox, limit, cursor, `end < start`, inverted bbox, out-of-range coordinates, unknown parameters;
- time and area filtering together, with neither dropped;
- empty versus unavailable versus upstream failure;
- pagination stability and cursor rules;
- idempotent upsert and dedupe per product by `(source, source_record_id)`;
- harmonization mapping: native confidence, FRP, brightness, and day/night fields land on the harmonized record without invented values;
- summary counts and interval boundaries, including months with no detections versus missing coverage;
- metadata and freshness fields;
- health endpoint;
- baseline comparison and anomaly math, including a zero baseline;
- CSV export matching the search filters and freshness.

Use a PostGIS-enabled Postgres test database. In CI, use an alpine Postgres service container with PostGIS. Do not mock Postgres; mock the provider. Cover cache hit, cache miss, TTL, invalidation after ingestion, and a database miss. Do not hit the live provider in unit tests. Mark synthetic fixtures. Run the full suite, lint, and type checks before handoff.

## Boundaries and handoff

- Do not edit `frontend/`, UI copy, or client state.
- Do not run `docker` or `docker compose` commands. The human operates the local stack.
- Do not change API shapes, field names, status codes, or error semantics without agreement and a contract update.
- Do not add features outside P0 unless the milestone says so.
- Keep migrations reversible. Use expand-and-contract when changing columns.
- Report files changed, commands run, test evidence, migration notes, and anything you deliberately left alone.
- The backend is done when the frontend can render the core journey from real source-backed data with all four states distinguishable, not when an endpoint returns something.

## Milestone checklist

- **M1:** verify MODIS and VIIRS via FIRMS, write the harmonization method, define the Postgres/PostGIS schema and UTC rules, agree the API contract, label fixtures, document fields and limitations.
- **M2:** serve harmonized observations, health, metadata, and basic filtering. Support the first end-to-end slice.
- **M3:** time and bbox filters, memory-first read path, cache invalidation, marker replacement support, calendar-ready summary output, empty, unavailable, error, and stale semantics, pagination, race-safe integration.
- **M4:** comparison against the historical median with anomalies, CSV export, stronger metadata, comparability warnings.
- **M5:** backend tests, Docker Compose with Postgres, CI with a Postgres service, clean-clone setup, deployment notes.
