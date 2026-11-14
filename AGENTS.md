# Pyra agent guide

Pyra is the project and repository. The PRD in this repo (v1.2, 20 October 2026) names the product FireWatch. Use Pyra for code, packages, and repo docs. Use FireWatch when the PRD's product name matters, such as user-facing copy or provenance text.

Pyra is a web app for exploring satellite-observed fire hotspots on an interactive 3D globe. The product answers one question at a time: what did MODIS and VIIRS observe, in this area, during this period? The user locks an area on the map, then drags the timeline or the calendar to scrub through burning activity from the early 2000s to the present and watch the hotspots change. The globe, timeline, activity chart, calendar, count, and details panel all read the same query result. Changing the timeline or scrubbing the calendar must run a real historical query and replace the displayed observations. Neither control is decoration.

This build targets the NASA Space Apps Challenge 2026 "MODIS and VIIRS Hot Spots" challenge: a web application that harmonizes MODIS and VIIRS hotspot records into a burning activity calendar. The PRD `.docx` in this repo is unchanged (v1.2); the Challenge alignment section below tailors scope and milestones to the challenge, and wins where the two differ.

This is a hackathon MVP. The repo currently holds the PRD (`Pyra_PRD_Scope_Milestones.docx`), a stub README, a Python-oriented `.gitignore`, and the `frontend/` and `backend/` trees with agent guides only. There is no application code yet. Milestone 1 is the next step.

## Read before working

1. This file.
2. `frontend/AGENTS.md` before touching `frontend/`.
3. `backend/AGENTS.md` before touching `backend/`.
4. The PRD for anything this file does not settle. The PRD is the source of truth for scope and acceptance, as tailored by the Challenge alignment section below. This file is the agent-facing contract. If your tool cannot read `.docx`, ask the orchestrator for a text export instead of guessing.

## Skills first

Before starting any substantive task, route it through the `godfile-navigator` skill if your environment provides it. Substantive means creating or changing an artifact, making or explaining a decision, investigating a problem, evaluating work, or giving guidance someone may act on. Follow the skills it selects. If your environment has no godfile skills, proceed with this guide and the subdirectory guides.

## Non-negotiables

- A satellite hotspot is a detection. It is not a confirmed wildfire, a fire perimeter, or a measure of burned area.
- Zero returned detections are not proof that no fire occurred.
- Never fabricate observations, missing fields, freshness, coverage, or measurements.
- The timeline must query the selected period and geographic area. Globe, timeline, chart, calendar, count, and details stay synchronized.
- A successful query replaces the active observation set. Never leave old-period markers mixed with new ones.
- Scrubbing the timeline or the calendar runs the same real query for the locked area. The CSV download always matches the current selection.
- Empty, unavailable, error, and stale are four different states with different copy and behavior.
- An older response must not overwrite a newer selection.
- Observation time and ingestion or retrieval time are different fields. Both stay visible.
- Source, product, coverage, freshness, and limitations stay visible. Harmonized views may hide the sensor of origin only after the harmonization method is documented; per-observation provenance always stays.
- An anomaly is observed activity against a multi-year baseline. It is not a forecast.
- Do not present the app as an emergency service or advise people to approach fires.
- The globe stays fully usable by hand. Current location is used only on explicit user action, as a single fix; never track, watch, or store it.

## Challenge alignment

This build targets the NASA Space Apps Challenge 2026 "MODIS and VIIRS Hot Spots" challenge: harmonize MODIS and VIIRS active-fire hotspot records into a burning activity calendar, so patterns, trends, and anomalies become the focus. Target users add early warning and emergency responders, scientists, land managers, and firefighters.

Objectives the build must meet:

- Combine the MODIS historical series (early 2000s to present) with VIIRS continuity and detail into one consistent hotspot time series, with a documented harmonization method.
- Let a user pick an area and a date range, then show analytics and visualizations of fire activity.
- Show a calendar of hotspot counts from the early 2000s to the present: which months and years burned more, and how current activity compares with the historical median.
- Use accessible color ramps for similarities and differences across months.
- Offer a downloadable CSV of hotspots for the search.
- Accept an area drawn on the map or entered as latitude and longitude.

## Scope

**P0, the MVP.** Globe-first landing with CesiumJS or an equivalent globe; MODIS plus VIIRS harmonized into one documented hotspot time series; documented ingestion and harmonization method; storage and query layer; place-name search and opt-in current location that move the globe and seed the locked area; source-attributed markers; hotspot selection and details; geographic filtering by drawn area or latitude and longitude, locked while the user scrubs time; historical timeline and draggable calendar that change the query; marker replacement after success; loading, empty, unavailable, error, and stale states; basic observation-count chart; burning activity calendar with accessible color ramps; comparison of the selected period against the historical median with anomalies; downloadable CSV for the search; provenance and freshness; core automated tests; Docker Compose; README; demo flow.

**P1, stretch only after P0 works.** Arbitrary two-period comparison, polygon areas, timeline playback, richer chart and calendar interactions, chart-image download, last-known-good display, shareable links, extra accessibility polish.

**Out of scope.** Fire prediction, custom AI or ML, burned-area analysis, accounts, saved investigations, social features, emergency dispatch, large-scale production infrastructure, calendar-only experience with no globe.

When time is short, cut P1 before weakening the core journey: harmonized observations, find a place by name, current location, or the globe itself, lock an area, scrub the calendar through history, watch the globe update, explain results accurately, offer the CSV.

## Milestones and exit gates

Do not start a milestone while an earlier exit criterion is unmet.

1. **Repository, data source, and contracts.** Verify MODIS and VIIRS via FIRMS: access, terms, update cadence, historical coverage, fields, and limitations. Write the harmonization method (`docs/harmonization.md`). Define the observation schema and UTC conventions. Agree the API query, response, and error contract. Label fixtures as synthetic. Document fields, units, and limitations. Exit: source evidence, a documented harmonization method, shared contract, local run, and no blocker for a historical query.
2. **Globe and source-backed observations.** Render the globe and camera controls, load harmonized records, draw markers and a legend, select a hotspot, show details, show source and freshness, and support place search with fly-to plus opt-in current location. Exit: harmonized records on the globe, correct metadata, no fabricated fields, and basic frontend/backend integration.
3. **Historical time travel and the calendar, the core MVP.** Timeline and date-range state, geographic filter by drawn area or latitude and longitude, timeline-to-API wiring, calendar scrubbing on the same query path, marker replacement, synchronized details, chart, calendar, and count, all four states, race protection, and reset to latest. Exit: a historical period or calendar scrub visibly changes the globe for the locked area, no stale markers remain, empty copy is correct, and automated tests cover it.
4. **Comparison, export, and provenance.** Comparison of the selected period against the historical median with anomalies, downloadable CSV for the search, chart and calendar from the same filters, stronger metadata and limitation copy, comparability warnings, and no percentage change from a zero baseline. Exit: globe, calendar, and chart share one query, metrics and anomalies are defined, CSV matches the query, and claims match the data.
5. **QA, deployment, and demo.** Backend, frontend, integration, and end-to-end tests. Empty, unavailable, upstream-failure, and rapid-scrub cases. Clean-clone setup, CI, deployment, demo script, and submission checklist. Exit: documented start, CI green, core journey works end to end, limitations documented, and the demo uses harmonized source-backed observations or clearly labelled fixtures.

## MVP acceptance criteria

- The app opens on an interactive globe.
- Harmonized MODIS and VIIRS observations appear with source attribution and coverage from the early 2000s to the present.
- A user can select a hotspot and inspect its details.
- A user can choose a supported historical period and a geographic area by drawing it or entering latitude and longitude.
- A user can search a place name or use their current location; the globe moves there.
- The timeline triggers a query filtered by both time and geography.
- Scrubbing the calendar updates the globe, counts, chart, and details for the locked area.
- A successful response replaces the previous-period markers.
- Globe, timeline, calendar, count, chart, and details stay synchronized.
- The calendar shows hotspot counts by month and year with accessible color ramps.
- The selected period is compared against the historical median with defined anomalies.
- A user can download a CSV of hotspots for the search, matching the current selection.
- Empty, unavailable, error, and stale are distinguishable.
- Older responses cannot overwrite the newest selection.
- Users can return to the latest available observations.
- The data source and historical coverage are documented.
- Backend, frontend, and end-to-end tests cover the core journey.
- Setup and deployment are reproducible.
- The core journey is usable on a mid-range phone over the demo connection.

## Architecture

- **Frontend:** React, TypeScript, Vite, CesiumJS with a MapLibre GL JS fallback behind one globe interface, Tailwind CSS, and Recharts for the basic chart. Tests: Vitest with React Testing Library and Playwright.
- **Backend:** Python, FastAPI, Pydantic, PostgreSQL with PostGIS, and a bounded in-process cache. Tests: pytest and HTTPX.
- **API:** `/api/v1` with health, observations (`start`, `end`, `bbox`, `limit`, `cursor`), observation by id, summary (`start`, `end`, `bbox`, `interval`), comparison of the selected period against the historical baseline, CSV export of the observations for the search, and metadata.
- **Shape:** use the smallest architecture that supports correct historical filtering. One FastAPI process serves the built frontend and the API, so users get one URL and no CORS. Run one API worker for the MVP so the in-process cache is coherent. A scheduled ingestion command may be enough. Add Celery only when background work requires it. Add Redis only when multiple workers or instances make the in-process cache inconsistent. Do not pull a large historical dataset from the provider on every timeline move.
- **Operations:** a small Docker Compose with the API and a PostGIS-enabled Postgres; every image uses its smallest variant (`postgis/postgis:16-3.4-alpine`, `python:3.12-alpine`, `node:24-alpine` at the time of writing; no full Debian images for the demo); `.env.example` with no secrets; one GitHub Actions workflow (`.github/workflows/ci.yml`) with a Postgres service for tests, type checks, and builds; a health endpoint; structured logs. Add CORS only if the frontend is split onto another origin.

The API contract will live in `docs/api-contract.md` (created in Milestone 1). Until it exists, the PRD's "Suggested API" section is provisional, not implemented truth.

## MVP stack and phone fallback

These are the defaults for the hackathon MVP. Cesium is the primary globe because the 3D feel is part of the product. The rest of the stack stays small. MapLibre is the fallback if Cesium misses the phone budget.

- **CesiumJS primary, MapLibre GL JS fallback.** Cesium gives a true 3D ellipsoid, atmosphere, lighting, terrain, and 3D Tiles. That is the kind of 3D depth the demo needs. Cesium's package is about 5 MB minified (1.35 MB gzip) before its worker and asset files. MapLibre's globe projection is about 1.1 MB minified (298 KB gzip); use it if Cesium misses the first-load or interaction target on a mid-range phone. Start Cesium without terrain or Ion imagery; use a solid globe until the phone test passes. Keep both behind one globe interface and choose one with `VITE_GLOBE_ENGINE=cesium|maplibre`. Lazy-load only the chosen engine. Do not ship both to a phone.
- **Recharts instead of ECharts for the basic chart.** Recharts is about 150 KB gzip against ECharts' 368 KB. Lazy-load it. Use ECharts only if the chart needs its feature set.
- **PostgreSQL with PostGIS, plus a bounded in-process cache.** Postgres is the source of truth and handles the time and area filters. The cache is a read-through layer keyed by products, time range, bbox, and pagination. It keeps repeat visits to the same area off the database. Use a TTL and an LRU bound. Invalidate or version entries after ingestion. Keep the cache in the API process; no Redis until multiple workers or instances.
- **One process and one origin.** Build the frontend and serve `frontend/dist` plus `/api/v1` from FastAPI. Run one API worker for the MVP so the in-process cache is coherent. No separate frontend host and no CORS in the deployed demo. Add Redis before scaling to multiple workers.
- **Prebuilt data.** Ingest a bounded MODIS and VIIRS dataset into Postgres and ship a seed or dump with the app. The API never calls the provider at request time.
- **Local dev.** Run Vite and `uvicorn` directly. The human already runs a local Postgres (alpine); use it and do not install another. Docker Compose is for the reproducible demo path, not a daily requirement.

These are package-level size numbers, not a full app measurement. Verify the built bundle on a mid-range phone. The first phone test decides whether Cesium stays or the MapLibre fallback takes over. Revisit the decision if the dataset, globe fidelity, or chart needs outgrow these defaults.

Trade-offs: Cesium gives the stronger 3D feel at a higher first-load cost; MapLibre is the lighter fallback if the phone test fails. PostgreSQL with PostGIS costs more setup, but it is the persistent store; the in-process cache keeps repeat queries fast. Both decisions are isolated behind the globe and query boundaries, so the swap is contained.

## Data shape and integrity

Minimum observation fields: `id`, `source` (`modis` or `viirs`), `source_record_id` (nullable), `observed_at` (UTC), `ingested_at` (UTC), `latitude`, `longitude`, `instrument` (nullable), `platform` (nullable), `confidence` (nullable, source-defined), `frp` and `frp_unit` (nullable), `quality_flags` (nullable), `product_version` (nullable), and `raw_properties` (optional JSON). Optional fields stay null. Observation time and ingestion time stay distinct.

Use MODIS and VIIRS for the MVP. Record each product's name and version, satellite and instrument, spatial coverage and resolution, historical range, latency, confidence semantics, FRP units, and known limitations. Verify the exact FIRMS collections in the FIRMS docs before implementing (MODIS Collection 6.1 and the VIIRS 375m active-fire products are the expected starting point). The harmonization method lives in `docs/harmonization.md` (written in Milestone 1): it states how resolutions, sensitivities, and observation schedules are reconciled, what a harmonized count means, and when sensor-of-origin comparisons are not valid. Do not combine products without that documented method.

NASA FIRMS is the source. Verify its access method, authentication, terms, update cadence, coverage, field definitions, and limitations before implementing. Provider credentials never reach the frontend.

## Read path and cache

1. Ingestion fetches a bounded dataset from the provider, validates and normalizes it, and upserts it into Postgres.
2. A request normalizes its filters and builds a cache key from products, time range, bbox, and pagination.
3. Check the in-process cache first. On a hit, return the cached result.
4. On a miss, query Postgres. On a hit, populate the cache and return.
5. On a database miss, return empty or unavailable per the contract. Do not call the provider synchronously from the request path. If on-demand fetch is added, make it a bounded ingestion job with rate limits and a bounded area and time range. It writes to Postgres, warms the cache, and surfaces loading, empty, unavailable, and error states.
6. Invalidate or version cache entries after ingestion. Warm the latest window if useful. A cache entry carries the data's freshness, not the time it was cached.

The cache is an optimization, not a second source of truth. Keep it bounded with a TTL and an LRU limit. Use a single-flight lock per key so concurrent misses do not stampede the database. No Redis for a single process; add Redis only when multiple workers or instances make an in-process cache inconsistent.

## Agent roles and boundaries

- **Orchestrator and integrator:** owns the PRD, `docs/`, contracts, root-level shared files such as `.gitignore`, task breakdown, integration, and final acceptance. Inspects before assigning or changing.
- **Frontend agent:** writes only in `frontend/`. Reads `frontend/AGENTS.md`.
- **Backend agent:** writes only in `backend/`. Reads `backend/AGENTS.md`.
- **Data and ingestion agent:** works in `backend/` and follows `backend/AGENTS.md`. Coordinate schema and contract changes with the backend agent.
- **UX/UI agent:** design work belongs in `docs/design/`. Do not edit application code unless the task assigns that tree.
- **Scientific and geospatial reviewer:** read-only review of source semantics, units, timestamps, coverage, normalization, and claims. Write findings through the orchestrator.
- **QA agent:** tests live in the tree that owns them. Coordinate with the owning agent before changing production behavior.
- **DevOps and release agent:** owns root-level Docker, CI, environment examples, and deployment files. Do not edit application code without coordination.

Coordination rules:

1. Inspect before changing.
2. Agree on contracts before parallel implementation.
3. Use clearly labelled synthetic fixtures for parallel UI work.
4. Integrate the first end-to-end slice early.
5. Require evidence of tests and files changed before accepting a task.
6. Prioritize P0 over stretch work.
7. Do not claim completion when a feature is only visually implemented.

## Working agreements

- Prefer the smallest change that satisfies the milestone. No speculative abstractions.
- Reuse working code. Do not replace it without a stated reason.
- Keep commits atomic and explain the why. Do not commit, push, or open a pull request unless the task asks.
- Commits and pull requests belong to the human who ships them. Do not add agent co-author lines or generated-by footers.
- Never commit secrets, `.env` files, provider keys, or local credentials.
- Do not collect precise user location automatically. The app stays usable without registration.
- Do not expose stack traces or credentials in API responses.
- Report what you changed, what you did not touch, the commands you ran, and any open risk.

## Quality gates

Every change runs the checks for its side. Frontend: lint, typecheck, unit tests, build, and a bundle-size check. Backend: lint and format, typecheck if configured, and pytest. Backend tests cover cache hit, miss, TTL, invalidation, and database misses. End-to-end tests cover latest data, place search, lock area, hotspot selection, historical switch, calendar scrub, marker replacement, empty versus unavailable versus error, rapid timeline changes, calendar and comparison output, CSV download, and reset to latest.

Initial performance targets: the interface is usable in about five seconds on the demo connection; backend filtering stays under one second at p95 in the demo environment, excluding upstream retrieval; the globe stays responsive at the agreed MVP dataset size; timeline changes cannot produce incorrect results from races. These are targets to measure, not guarantees.

A task is done when its acceptance criteria are met, tests are added or updated and pass, no secret is committed, affected docs are updated, and the handoff includes evidence.

## Phone testing

The demo must load on a phone. Test that path before calling a milestone complete.

- Build the frontend and serve it with the API from one origin. That is the closest test to the deployed demo.
- For the demo, deploy the same app to a small host and share the URL. Testers should only need a browser.
- For local testing, run Vite with `--host` and proxy `/api` to the local backend. Open the LAN URL on the phone. The phone and computer must be on the same network.
- Test Cesium first. If it misses the first-load or interaction target, switch `VITE_GLOBE_ENGINE` to MapLibre and re-test. Do not ship both engines to the phone.
- For the first Cesium build, disable terrain and the default Ion imagery. Use a solid globe or a small local texture, then add detail only if the phone test passes.
- Use a mid-range phone over the demo connection, not only a desktop browser.
- Check first load, globe interaction, timeline and calendar scrubbing, hotspot selection, and the four result states.
- Keep the initial transfer small. Lazy-load the globe and chart, cluster or cap markers, and avoid heavy UI kits.

## Cross-tool notes

This file is plain Markdown. Do not add tool-specific frontmatter, directives, or configuration syntax. Plain commands are fine.

- **opencode** reads `AGENTS.md` from the project and its parents. It prefers `AGENTS.md` over `CLAUDE.md`.
- **Antigravity** reads `AGENTS.md` in the workspace folder and its parents. It does not load a subfolder's `AGENTS.md` when the workspace is the repo root.
- **Claude Code** v2.1.277 and later reads `AGENTS.md` when no `CLAUDE.md` is present. Older versions and the Claude harness in VS Code use `CLAUDE.md`. If you need that, create a local `CLAUDE.md` containing `@AGENTS.md`, or upgrade. Do not commit it unless the team agrees.
- **VS Code Copilot** reads `AGENTS.md` as project instructions.
- **Claude apps** do not read the repo automatically. Attach or paste this file into the conversation.

Tools that start at the repo root do not always load a subfolder's guide. Before working in `frontend/` or `backend/`, open that folder's `AGENTS.md` yourself or start the tool with that folder as the workspace.
- **Windows and WSL:** use forward-slash paths in docs. When a command differs between Bash and PowerShell, show both forms.

## Current state and next step

The repo is a shell: PRD, README, `.gitignore`, the two agent guides, and CI (`.github/workflows/ci.yml`, which skips until the frontend/backend scaffold lands). There is no application code yet. Milestone 1 is next. Verify MODIS and VIIRS via FIRMS, write the harmonization method, define the observation schema and API contract, label fixtures, and get both sides running locally. Do not assume a data source, a contract, or a working feature before that work is done.
