import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SummaryBucket } from "./api/types";
import { ActivityChart } from "./features/chart/ActivityChart";
import { BurningCalendar } from "./features/calendar/BurningCalendar";
import { HistoricalComparison } from "./features/compare/HistoricalComparison";
import { ObservationDetails } from "./features/details/ObservationDetails";
import { ExportTools } from "./features/export/ExportTools";
import { PlaceSearch, type LockedPlace } from "./features/search/PlaceSearch";
import { ProvenanceView } from "./features/provenance/ProvenanceView";
import { RecordsWorkbench } from "./features/records/RecordsWorkbench";
import { QueryStatus } from "./features/status/QueryStatus";
import { radiusToBbox, toGlobeObservations, useSnapshotQuery } from "./query/useSnapshotQuery";

const GlobeView = lazy(() =>
  import("./features/globe/ThreeGlobeView").then(({ ThreeGlobeView }) => ({ default: ThreeGlobeView }))
);

function dateValue(iso: string): string {
  return iso.slice(0, 10);
}

function formatTimestamp(value: string | null): string {
  if (!value) return "not provided";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function monthRange(month: string): { start: string; end: string } {
  const [year, monthNumber] = month.split("-").map(Number);
  const start = new Date(Date.UTC(year, monthNumber - 1, 1));
  const end = new Date(Date.UTC(year, monthNumber, 0, 23, 59, 59, 999));
  return { start: start.toISOString(), end: end.toISOString() };
}

function monthIndex(month: string): number {
  const [year, monthNumber] = month.split("-").map(Number);
  return year * 12 + monthNumber - 1;
}

function monthFromIndex(index: number): string {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

type WorkspaceView = "explorer" | "records" | "provenance";

function readWorkspaceView(): WorkspaceView {
  const value = new URLSearchParams(window.location.search).get("view");
  return value === "records" || value === "provenance" ? value : "explorer";
}

function App() {
  const globeContainerRef = useRef<HTMLDivElement>(null);
  const { query, snapshot, updateQuery, retry } = useSnapshotQuery();
  const [activeView, setActiveView] = useState<WorkspaceView>(readWorkspaceView);
  const [selectedObservationId, setSelectedObservationId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("Choose a place or use the current area to query satellite observations.");
  const [zoomRequest, setZoomRequest] = useState<{ direction: "in" | "out"; requestId: number }>();
  const [resetRequestId, setResetRequestId] = useState(0);

  const observations = useMemo(() => toGlobeObservations(snapshot.data?.data ?? []), [snapshot.data]);
  const selectedObservation = useMemo(
    () => observations.find(({ id }) => id === selectedObservationId) ?? null,
    [observations, selectedObservationId]
  );
  const selectedRecord = snapshot.data?.data.find(({ id }) => id === selectedObservationId) ?? null;
  const monthlyBuckets = snapshot.summary?.data?.data ?? [];
  const dailyBuckets = snapshot.dailySummary?.data?.data ?? [];

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    params.set("view", activeView);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}${window.location.hash}`);
  }, [activeView]);

  useEffect(() => {
    const handlePopState = () => setActiveView(readWorkspaceView());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (selectedObservationId && !observations.some(({ id }) => id === selectedObservationId)) setSelectedObservationId(null);
  }, [observations, selectedObservationId]);

  useEffect(() => {
    const messages: Record<string, string> = {
      idle: "Waiting for a query.",
      loading: "Loading satellite observations for the selected area and period.",
      success: `${snapshot.data?.count ?? 0} observations loaded${snapshot.synthetic ? ". Synthetic fixture data." : "."}`,
      empty: "No satellite hotspot detections were returned for this area and period. This does not prove that no fire occurred.",
      unavailable: "Coverage is unavailable for this period.",
      error: snapshot.message ?? "The observation query failed. Retry to try again.",
      stale: snapshot.message ?? "Showing a previous successful result."
    };
    setStatusMessage(snapshot.message ?? messages[snapshot.state]);
  }, [snapshot]);

  const handleSelectObservation = useCallback((observationId: string | null) => {
    setSelectedObservationId(observationId);
    setStatusMessage(observationId ? "Observation selected. Details are shown in the inspector." : "No observation selected.");
  }, []);

  const handleZoom = useCallback((direction: "in" | "out") => {
    setZoomRequest((current) => ({ direction, requestId: (current?.requestId ?? 0) + 1 }));
    setStatusMessage(direction === "in" ? "Globe zoomed in." : "Globe zoomed out.");
  }, []);

  const lockPlace = useCallback((place: LockedPlace) => {
    updateQuery({
      areaLabel: place.label,
      center: { lat: place.lat, lon: place.lon },
      radiusKm: place.radiusKm,
      bbox: radiusToBbox(place.lat, place.lon, place.radiusKm),
      areaSource: place.source
    });
    setSelectedObservationId(null);
    setStatusMessage(`${place.label} locked. Loading observations for this area.`);
  }, [updateQuery]);

  const setStartDate = (value: string) => {
    if (!value) return;
    const start = new Date(`${value}T00:00:00.000Z`).toISOString();
    updateQuery({ start, end: start > query.end ? new Date(`${value}T23:59:59.999Z`).toISOString() : query.end, selectedMonth: value.slice(0, 7) });
  };

  const setEndDate = (value: string) => {
    if (!value) return;
    const end = new Date(`${value}T23:59:59.999Z`).toISOString();
    updateQuery({ start: end < query.start ? new Date(`${value}T00:00:00.000Z`).toISOString() : query.start, end, selectedMonth: value.slice(0, 7) });
  };

  const setMonth = (month: string) => {
    if (!month) return;
    updateQuery({ selectedMonth: month, ...monthRange(month) });
  };

  const selectBucket = (bucket: SummaryBucket) => {
    const start = new Date(`${bucket.start.slice(0, 10)}T00:00:00.000Z`);
    const endValue = bucket.end ? new Date(bucket.end.length <= 10 ? `${bucket.end}T23:59:59.999Z` : bucket.end) : new Date(`${bucket.start.slice(0, 10)}T23:59:59.999Z`);
    const end = Number.isNaN(endValue.valueOf()) ? new Date(`${bucket.start.slice(0, 10)}T23:59:59.999Z`) : endValue;
    updateQuery({ start: start.toISOString(), end: end.toISOString(), selectedMonth: bucket.start.slice(0, 7) });
  };

  const resetToLatest = () => {
    const end = new Date();
    end.setUTCHours(23, 59, 59, 999);
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - 7);
    updateQuery({ start: start.toISOString(), end: end.toISOString(), selectedMonth: end.toISOString().slice(0, 7) });
    setSelectedObservationId(null);
    setResetRequestId((current) => current + 1);
    setStatusMessage("Showing the latest seven-day selection.");
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <img className="brand-logo" src={`${import.meta.env.BASE_URL}pyra-logo.png`} alt="Pyra" />
          <div className="brand-subtitle">SATELLITE HOTSPOT EXPLORER</div>
        </div>
        <div className="topbar-meta">
          <span className={`status-dot ${snapshot.state === "error" || snapshot.state === "unavailable" ? "status-dot-alert" : ""}`} aria-hidden="true" />
          <span>{snapshot.synthetic ? "Synthetic demo data" : `Query ${snapshot.state}`}</span>
          <button className="icon-button" type="button" aria-label="Open help">?</button>
        </div>
        <nav className="view-switcher" aria-label="Workspace views">
          <button type="button" className={activeView === "explorer" ? "view-tab view-tab-active" : "view-tab"} aria-current={activeView === "explorer" ? "page" : undefined} onClick={() => setActiveView("explorer")}>Explorer</button>
          <button type="button" className={activeView === "records" ? "view-tab view-tab-active" : "view-tab"} aria-current={activeView === "records" ? "page" : undefined} onClick={() => setActiveView("records")}>Records &amp; analytics</button>
          <button type="button" className={activeView === "provenance" ? "view-tab view-tab-active" : "view-tab"} aria-current={activeView === "provenance" ? "page" : undefined} onClick={() => setActiveView("provenance")}>Harmonization &amp; provenance</button>
        </nav>
      </header>

      <QueryStatus snapshot={snapshot} onRetry={retry} />
      {activeView === "explorer" && <section className="workspace" aria-label="Pyra globe explorer">
        <section className="globe-card">
          <div className="globe-heading">
            <div className="eyebrow">01 / EXPLORE</div>
            <h1>See what satellites observed.</h1>
            <p>Choose an area and time period. Drag to rotate and select a hotspot for its source fields.</p>
          </div>
          <div ref={globeContainerRef} className="globe-canvas" role="application" aria-label="Interactive Earth. Drag to rotate and use the controls to zoom." />
          <div className="globe-controls" aria-label="Globe controls">
            <button type="button" onClick={() => handleZoom("in")} aria-label="Zoom in">+</button>
            <button type="button" onClick={() => handleZoom("out")} aria-label="Zoom out">-</button>
          </div>
          <div className="rotation-hint" aria-hidden="true"><span>↻</span> Drag to rotate 360° <span className="hint-divider">·</span> Pinch or scroll to zoom</div>
          <Suspense fallback={<div className="globe-loading">Loading globe...</div>}>
            <GlobeView containerRef={globeContainerRef} observations={observations} selectedObservationId={selectedObservationId} onSelectObservation={handleSelectObservation} zoomRequest={zoomRequest} resetRequestId={resetRequestId} />
          </Suspense>
        </section>

        <section className="timeline-panel" aria-label="Historical timeline">
          <div className="timeline-heading">
            <div><h2>Historical timeline</h2><span>Changing the period runs the same area query and replaces its observations.</span></div>
            <button type="button" className="reset-button" onClick={resetToLatest}>Reset to latest</button>
          </div>
          <div className="query-controls">
            <label>From<input type="date" value={dateValue(query.start)} onChange={(event) => setStartDate(event.currentTarget.value)} /></label>
            <label>Through<input type="date" value={dateValue(query.end)} onChange={(event) => setEndDate(event.currentTarget.value)} /></label>
            <label>Scrub month<input type="month" value={query.selectedMonth} onChange={(event) => setMonth(event.currentTarget.value)} /></label>
            <label>Sensor scope<select value={query.sensorScope} onChange={(event) => updateQuery({ sensorScope: event.currentTarget.value as typeof query.sensorScope })}><option value="all">MODIS + VIIRS</option><option value="modis">MODIS only</option><option value="viirs">VIIRS only</option></select></label>
          </div>
          <div className="timeline-track"><span>2000</span><input className="history-scrubber" aria-label="Historical month scrubber" type="range" min={monthIndex("2000-01")} max={monthIndex(new Date().toISOString().slice(0, 7))} step="1" value={monthIndex(query.selectedMonth)} onChange={(event) => setMonth(monthFromIndex(Number(event.currentTarget.value)))} /><output className="timeline-date">{query.selectedMonth}</output><span>{new Date().getUTCFullYear()}</span><span className="timeline-date">{snapshot.data?.count ?? 0} detections</span></div>
        </section>

        <aside className="inspector">
          <section className="panel">
            <div className="panel-heading"><h2>Locked area</h2><span className="state-pill">{snapshot.state === "loading" ? "UPDATING" : "READY"}</span></div>
            <strong>{query.areaLabel}</strong>
            <span className="muted">{query.center.lat.toFixed(3)}° {query.center.lat < 0 ? "S" : "N"}, {Math.abs(query.center.lon).toFixed(3)}° {query.center.lon < 0 ? "W" : "E"} · {query.radiusKm} km radius</span>
            <div className="panel-divider" />
            <PlaceSearch areaLabel={query.areaLabel} center={query.center} radiusKm={query.radiusKm} onLock={lockPlace} />
          </section>
          <section className="panel observation-panel">
            <div className="panel-heading"><h2>Selected observation</h2><span className="source-label">{selectedObservation?.source.toUpperCase() ?? "—"}</span></div>
            <ObservationDetails observation={selectedRecord} />
          </section>
          <section className="panel query-panel">
            <div className="panel-heading"><h2>Your query</h2><span className="source-label">{snapshot.data?.count ?? 0} DETECTIONS</span></div>
            <span className="muted">{query.products.map((product) => product.toUpperCase()).join(" + ")} · {query.sensorScope === "all" ? "all sensors" : query.sensorScope.toUpperCase()}</span>
            <span className="muted">Retrieval: {snapshot.retrievedAt ? formatTimestamp(snapshot.retrievedAt) : "not provided"}</span>
            {snapshot.synthetic && <span className="synthetic-label">Synthetic fixture data · not FIRMS observations</span>}
            <HistoricalComparison comparison={snapshot.comparison?.data ?? null} query={query} synthetic={snapshot.comparison?.synthetic ?? false} />
            <ActivityChart monthly={monthlyBuckets} daily={dailyBuckets} selectedMonth={query.selectedMonth} compact />
            <BurningCalendar buckets={monthlyBuckets} selectedMonth={query.selectedMonth} onSelectMonth={setMonth} />
            <ExportTools observations={snapshot.data?.data ?? []} query={query} retrievedAt={snapshot.retrievedAt} synthetic={snapshot.synthetic} />
          </section>
        </aside>
      </section>}

      {activeView === "records" && <section className="records-view-shell" aria-label="Records and analytics workspace">
        <div className="analytics-overview">
          <ActivityChart monthly={monthlyBuckets} daily={dailyBuckets} selectedMonth={query.selectedMonth} onSelectPeriod={selectBucket} />
          <HistoricalComparison comparison={snapshot.comparison?.data ?? null} query={query} synthetic={snapshot.comparison?.synthetic ?? false} />
        </div>
        <RecordsWorkbench observations={snapshot.data?.data ?? []} selectedId={selectedObservationId} onSelect={setSelectedObservationId} query={query} retrievedAt={snapshot.retrievedAt} synthetic={snapshot.synthetic} />
      </section>}

      {activeView === "provenance" && <ProvenanceView />}

      <p className="sr-only" aria-live="polite">{statusMessage}</p>
      <footer className="disclaimer">A satellite hotspot is a detection, not a confirmed fire or measure of burned area. Zero detections do not prove no fire occurred.</footer>
    </main>
  );
}

export default App;
