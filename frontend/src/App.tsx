import { lazy, Suspense, useCallback, useMemo, useRef, useState } from "react";
import type { GlobeObservation } from "./features/globe/GlobeView";

const GlobeView = lazy(() =>
  import("./features/globe/ThreeGlobeView").then(({ ThreeGlobeView }) => ({
    default: ThreeGlobeView
  }))
);

const syntheticObservations: GlobeObservation[] = [
  { id: "synthetic-viirs-001", source: "viirs", observedAt: "14 Nov 2026 · 03:42 UTC", ingestedAt: "14 Nov 2026 · 03:48 UTC", latitude: 40.031, longitude: -2.141, confidence: "nominal", frp: 18.4, frpUnit: "MW" },
  { id: "synthetic-modis-002", source: "modis", observedAt: "12 Nov 2026 · 12:05 UTC", ingestedAt: "12 Nov 2026 · 12:12 UTC", latitude: 39.842, longitude: -2.684, confidence: "nominal", frp: 11.2, frpUnit: "MW" },
  { id: "synthetic-viirs-003", source: "viirs", observedAt: "09 Nov 2026 · 09:18 UTC", ingestedAt: "09 Nov 2026 · 09:24 UTC", latitude: 40.411, longitude: -1.884, confidence: "nominal", frp: 7.8, frpUnit: "MW" },
  { id: "synthetic-modis-004", source: "modis", observedAt: "07 Nov 2026 · 17:20 UTC", ingestedAt: "07 Nov 2026 · 17:28 UTC", latitude: 40.218, longitude: -2.944, confidence: "nominal", frp: 5.6, frpUnit: "MW" }
];

function App() {
  const globeContainerRef = useRef<HTMLDivElement>(null);
  const [selectedObservationId, setSelectedObservationId] = useState(syntheticObservations[0].id);
  const [statusMessage, setStatusMessage] = useState("Synthetic fixture data is displayed while the API is being built.");
  const [zoomRequest, setZoomRequest] = useState<{ direction: "in" | "out"; requestId: number }>();
  const [resetRequestId, setResetRequestId] = useState(0);

  const selectedObservation = useMemo(
    () => syntheticObservations.find(({ id }) => id === selectedObservationId) ?? null,
    [selectedObservationId]
  );

  const handleSelectObservation = useCallback((observationId: string | null) => {
    setSelectedObservationId(observationId ?? "");
    setStatusMessage(observationId ? "Observation selected. Details are shown in the inspector." : "No observation selected.");
  }, []);

  const handleZoom = useCallback((direction: "in" | "out") => {
    setZoomRequest((current) => ({ direction, requestId: (current?.requestId ?? 0) + 1 }));
    setStatusMessage(direction === "in" ? "Globe zoomed in." : "Globe zoomed out.");
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">P</div>
          <div>
            <div className="brand-name">PYRA</div>
            <div className="brand-subtitle">SATELLITE HOTSPOT EXPLORER</div>
          </div>
        </div>
        <div className="topbar-meta">
          <span className="status-dot" aria-hidden="true" />
          <span>Source-backed globe shell</span>
          <button className="icon-button" type="button" aria-label="Open help">?</button>
        </div>
      </header>

      <section className="workspace" aria-label="Pyra globe explorer">
        <section className="globe-card">
          <div className="globe-heading">
            <div className="eyebrow">01 / EXPLORE</div>
            <h1>See what burned here.</h1>
            <p>Drag to rotate, scroll to zoom, and select a hotspot to inspect the observation.</p>
          </div>
          <div ref={globeContainerRef} className="globe-canvas" role="application" aria-label="Interactive Earth. Drag to rotate and use the controls to zoom." />
          <div className="globe-controls" aria-label="Globe controls">
            <button type="button" onClick={() => handleZoom("in")} aria-label="Zoom in">+</button>
            <button type="button" onClick={() => handleZoom("out")} aria-label="Zoom out">-</button>
          </div>
          <div className="rotation-hint" aria-hidden="true"><span>↻</span> Drag to rotate 360° <span className="hint-divider">·</span> Pinch or scroll to zoom</div>
          <Suspense fallback={<div className="globe-loading">Loading globe...</div>}>
            <GlobeView containerRef={globeContainerRef} observations={syntheticObservations} selectedObservationId={selectedObservationId} onSelectObservation={handleSelectObservation} zoomRequest={zoomRequest} resetRequestId={resetRequestId} />
          </Suspense>
        </section>

        <aside className="inspector">
          <section className="panel">
            <div className="panel-heading"><h2>Locked area</h2><span className="state-pill">READY</span></div>
            <strong>Serrania de Cuenca</strong>
            <span className="muted">40.02 N, 2.13 W · 25 km radius</span>
            <div className="panel-divider" />
            <button className="search-button" type="button"><span aria-hidden="true">⌕</span> Search a place or enter coordinates</button>
          </section>
          <section className="panel">
            <div className="panel-heading"><h2>Selected observation</h2><span className="source-label">{selectedObservation?.source.toUpperCase() ?? "-"}</span></div>
            {selectedObservation ? <><strong>{selectedObservation.observedAt}</strong><span className="muted">{selectedObservation.latitude.toFixed(3)} N, {Math.abs(selectedObservation.longitude).toFixed(3)} W</span><div className="metric-row"><span>Confidence <b>{selectedObservation.confidence ?? "not provided"}</b></span><span>FRP <b>{selectedObservation.frp ?? "not provided"} {selectedObservation.frpUnit ?? ""}</b></span></div><div className="muted">Ingested {selectedObservation.ingestedAt}</div></> : <p className="muted">Select a marker to inspect its source fields.</p>}
          </section>
          <section className="panel interaction-panel">
            <h2>Globe interaction</h2>
            <p><span>↻</span> Drag anywhere on Earth to rotate.</p>
            <p><span>⌕</span> Search keeps the area locked.</p>
            <p><span>↺</span> Use the timeline to query history.</p>
          </section>
        </aside>
      </section>

      <section className="timeline-panel" aria-label="Historical timeline">
        <div className="timeline-heading"><div><h2>Historical timeline</h2><span>The globe and evidence update from one query snapshot.</span></div><button type="button" className="reset-button" onClick={() => { setResetRequestId((current) => current + 1); setStatusMessage("Globe view reset."); }}>Reset to latest</button></div>
        <div className="timeline-track" aria-hidden="true"><span>2002</span><div className="track"><div className="track-active" /><div className="track-thumb" /></div><span>2026</span><span className="timeline-date">14 Nov 2026</span></div>
      </section>

      <p className="sr-only" aria-live="polite">{statusMessage}</p>
      <footer className="disclaimer">Synthetic fixture data · A satellite detection is an observation, not proof of a fire or burned area.</footer>
    </main>
  );
}

export default App;
