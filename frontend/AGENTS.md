# Frontend agent guide

You are the frontend agent for Pyra. Work only in `frontend/`. The backend agent owns `backend/`; do not edit it. Read the root `AGENTS.md` first for scope, milestones, data integrity, and acceptance criteria. If the two files disagree, the root wins on product rules, and this file wins on frontend mechanics.

**Hard boundary:** your writes stay inside `frontend/`. Reading other trees is allowed when you need context. Do not edit root-level Docker, CI, or deployment files without the task saying so.

Route substantive work through the `godfile-navigator` skill first when your environment provides it; otherwise follow this guide and the root guide.

## What the frontend must do

The browser app is the product. It shows an interactive 3D globe, source-attributed hotspot markers, a details panel, a place-name search and an opt-in current-location button that move the globe to the result, an area explorer where the user locks an area by drawing it or entering latitude and longitude, a timeline and a draggable calendar that run real queries for the locked area, a synchronized activity chart, burning activity calendar, count, comparison against the historical median, CSV download of the current selection, provenance and freshness, and distinct loading, empty, unavailable, error, and stale states. It also needs an accessible list or table alternative and a responsive layout.

One query drives the screen: products plus time range plus the locked geographic area. The globe, timeline, chart, calendar, comparison, count, and details panel render the same response snapshot. Scrubbing the calendar changes the time range through the same query path as the timeline. A calendar drag is a real request, not a cosmetic filter.

## Stack

Follow the MVP stack: React, TypeScript, Vite, CesiumJS for the globe, Tailwind CSS, and Recharts for the basic chart. MapLibre GL JS with globe projection is the fallback. Test with Vitest, React Testing Library, and Playwright. Build Cesium first. Keep the MapLibre fallback behind the same `GlobeView` interface; implement it if Cesium misses the phone target or time allows. The choice stays a build-time flag, not a rewrite.

When you scaffold, check the current official docs for the packages you add. Cesium with Vite needs static asset and worker configuration. MapLibre needs its CSS and worker setup checked against the installed version. Tailwind's setup depends on the major version. Recharts should be lazy-loaded with the chart. Record the versions you choose in `package.json` and the frontend README. Do not copy a blog snippet without checking it against the installed version.

Configuration comes from Vite environment variables, for example `VITE_API_BASE_URL` with a local default. Provider keys never belong in the frontend. All provider access goes through the backend.

## Phone-first constraints

The demo must load on a phone. Treat that as a product requirement, not a later optimization.

- Default to CesiumJS for the 3D feel. Keep the globe behind `src/features/globe` with one `GlobeView` interface. MapLibre GL JS globe projection is the fallback if Cesium misses the phone load or interaction target.
- Choose one engine at build time with `VITE_GLOBE_ENGINE=cesium|maplibre`, and lazy-load only the chosen engine. Do not ship both to the phone.
- Start Cesium without terrain and without the default Ion imagery. Use a solid globe or a small local texture until the phone test passes. Add terrain or imagery only after it passes.
- Lazy-load the globe and chart with dynamic imports. Keep the initial route small.
- Cluster or cap markers for the MVP dataset. Use Cesium point primitives or MapLibre circle and glow layers. Do not render an unbounded global point layer.
- Use touch targets that work with a thumb, a responsive layout, and a timeline that does not cover the globe.
- Do not add a UI kit or a global state library for the MVP. React state, a small query hook, and Tailwind are enough.
- Test the built app on a real mid-range phone over the demo connection. If Cesium fails the first-load or interaction budget, switch the flag to MapLibre and re-test.

## Repo hygiene before the first install

The root `.gitignore` is Python-oriented. It ignores `dist/`, but it does not ignore `node_modules/`. Before the first install, ask the orchestrator or DevOps to add the frontend entries: `node_modules/`, `.vite/`, Playwright output, and frontend env files not already covered. If you are asked to make that change, keep it scoped to frontend patterns. The file also ignores any directory named `lib/`, so do not put source in `src/lib`; use `src/api`, `src/query`, `src/format`, or another name. Keep the existing Python ignores intact.

## Suggested layout

Use feature folders, not type folders:

- `src/features/globe`: `GlobeView` interface, Cesium implementation, MapLibre fallback, markers, legend, selection bridge.
- `src/features/search`: place-name search, current-location button, globe fly-to.
- `src/features/timeline`: date and range state, scrubber, reset to latest.
- `src/features/details`: observation fields, source, limitations.
- `src/features/chart`: lazy-loaded Recharts count chart for the same query.
- `src/features/calendar`: months-by-years heatmap of hotspot counts for the same query, with accessible color ramps. Draggable like a timeline: scrubbing it changes the selected period and drives the same query as the timeline.
- `src/features/compare`: selected period against the historical median, with defined anomalies.
- `src/features/export`: CSV download of the hotspots for the search.
- `src/features/status`: loading, empty, unavailable, error, stale.
- `src/api`: typed client and contract types.
- `src/query`: request identity, cancellation, snapshot state, locked area.
- `src/test`: fixtures and test helpers.

Do not create a shared abstraction until a second caller needs it.

## API and state rules

- Use `/api/v1` from the contract: health, observations, observation by id, summary, comparison against the historical baseline, CSV export, metadata.
- In production, use same-origin `/api/v1` served by FastAPI. In development, proxy `/api` through Vite so the phone only needs the Vite URL.
- The locked area is the active bbox. It stays fixed while the user scrubs time with the timeline or the calendar; changing the area starts a new lock.
- Searching a place centers the globe on the result and locks the default area around it, like a lat/lon entry. The globe stays fully usable by hand afterward.
- Current location is opt-in only: one button, one fix, no watch. On grant, center and lock the default area; on deny or failure, say so and keep the manual globe. Never send the raw fix anywhere except as the bbox of the existing observation query.
- Place search uses Photon (OSM-based, no key; verify the endpoint and terms when scaffolding). Debounce keystrokes and show attribution.
- Calendar scrubbing dispatches through the same query path as the timeline: debounce the drag, cancel obsolete requests, and ignore out-of-order responses. The globe, calendar highlight, counts, chart, and details update from the same response snapshot.
- The area comes from a drawn bbox or a latitude and longitude entry. Convert a lat/lon entry to a bbox with a documented default radius on the client; the backend filters by bbox. Do not promise polygon areas until the contract supports them.
- Send both time and area for observation queries. Include `limit` and `cursor`.
- The CSV request reuses the active snapshot's filters and freshness. Name the file with area and period so the download traces back to the selection.
- Use the summary `interval` for the calendar buckets (month, year). Chart, calendar, comparison, and count all derive from the same response snapshot.
- Use accessible color ramps for the calendar and any count encoding. Pair color with numbers and a legend; do not rely on color alone.
- Treat each response as a snapshot with the observation list, count, filters, coverage, and freshness. Render the globe, chart, and count from that snapshot, not from independent requests.
- On success, replace the active set atomically. If the selected observation is not in the new set, clear the selection and say so. Do not keep a ghost selection.
- Use `AbortController` plus a monotonically increasing request id. Ignore any response that does not belong to the latest request. Test fast scrubbing.
- Keep last-known-good data only for the stale state. Label its retrieval time and do not mix it with new results.
- Do not derive fields the backend did not send. Render null as "not provided", not zero.
- Reset returns to the latest available observations for MODIS and VIIRS. Do not imply a live feed without verified freshness.

## The four result states

Keep these separate in state, rendering, and copy.

- **Empty:** the request succeeded and returned zero records. Use the PRD copy: "No satellite hotspot detections were returned for this area and period. This does not prove that no fire occurred."
- **Unavailable:** the product does not cover the period. Say coverage is unavailable. Do not render zero.
- **Error:** the request failed or returned an invalid response. Offer retry. Do not show it as empty.
- **Stale:** earlier successful data is on screen. Show its age and do not present it as current.

Loading is its own state. Do not let a loading state erase the last good result without labelling what is happening.

## Data integrity in the UI

- Show `observed_at` separately from `ingested_at`.
- Show source and product. Show satellite, platform, or instrument when present. Show confidence with its source-defined meaning, FRP with units, the source link, and limitations.
- Label harmonized counts as harmonized and name the method. Show the sensor of origin for each observation in details and CSV.
- An anomaly is observed activity against the historical baseline for that area and window. Do not frame it as a forecast or a fire-risk score.
- The CSV must match the on-screen selection: same filters, same freshness. Show the locked area and period next to the download.
- Do not call detection counts "number of fires", burned area, or a fire perimeter.
- Do not say or imply that missing detections prove no fire.
- Mark synthetic fixtures in the UI and in tests.
- Base freshness on the backend's latest successful ingestion, not the browser clock.
- Do not fabricate a field to fill a gap in the design.
- Request the browser location only when the user taps the location button, once per tap. Never watch, track, or store it.
- Do not use emergency-service framing or advise people to approach fires.

## Accessibility and interaction

Globe-first does not mean globe-only.

- Every control is keyboard operable with visible focus.
- Provide an accessible list or table of the same records, with selection and paging.
- Announce loading and result changes without stealing focus.
- Support reduced motion and give users a way to stop camera animation. Fly-to and spin animations honor reduced motion by jumping instead.
- Make calendar scrubbing keyboard-operable (step through months), not drag-only.
- Keep the timeline usable without covering the globe.
- Do not rely on color alone. Check contrast for markers, states, and text.
- Cover empty, unavailable, and error states in the accessibility pass, not just the happy path.

## Testing

- Unit and component tests: Vitest and React Testing Library. Mock at the API client boundary.
- End-to-end: Playwright. Cover latest data, place search centering the globe and locking the area, denied geolocation staying usable, lock an area, hotspot selection, historical period change, calendar scrub for the locked area, marker replacement, calendar output, comparison output, CSV matching the selection, empty, unavailable, error, rapid scrubbing, and reset.
- Add a unit test for denied or failed geolocation resolving gracefully.
- Add a mobile viewport run for the core journey, then confirm it on a real phone.
- If both globe engines exist, smoke-test each behind the build flag. Do not load both in one test run.
- Add a race test with delayed and out-of-order responses.
- No test depends on the live provider. Fixtures are labelled synthetic.
- Run lint, typecheck, unit tests, end-to-end tests where practical, and build before handoff.

## Boundaries and handoff

- Do not edit `backend/`, database migrations, ingestion, or backend deployment files.
- Keep Cesium and MapLibre imports inside `src/features/globe`. The rest of the app should not know which engine is active.
- Do not implement a runtime engine switch that downloads both. Use the build flag. If the chosen engine fails, show the accessible list or table and a clear error.
- Do not call the satellite provider directly. If a key would be exposed in the browser, stop.
- If the contract is missing a field or an error code, propose the change to the orchestrator. Do not invent a parallel shape.
- If the backend is not ready, use the agreed fixtures and keep the API seam real.
- Do not build P1 features before the core journey passes.
- Report files changed, commands run, test evidence, and anything you deliberately left alone.

## Milestone checklist

- **M2:** Cesium globe, camera, markers, legend, selection, details, source and freshness, place search with fly-to, opt-in current location. Keep the MapLibre fallback behind the same interface.
- **M3:** locked-area state, timeline and calendar scrub on the same query path, request on time or area change, marker replacement, synchronized chart, calendar, count, and details, four states, race guard, reset.
- **M4:** comparison against the historical median with defined anomalies, CSV download matching the query, metrics and ramps documented, no percentage from a zero baseline.
