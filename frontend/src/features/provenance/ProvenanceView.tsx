import { useEffect, useState } from "react";
import { apiClient } from "../../api";
import type { ApiResult, MetadataResponse } from "../../api/types";

const COVERAGE_WINDOWS = [
  { sensor: "MODIS", platform: "Terra / Aqua · Collection 6.1", start: "November 2000" },
  { sensor: "VIIRS", platform: "Suomi-NPP", start: "January 2012" },
  { sensor: "VIIRS", platform: "NOAA-20", start: "April 2018" },
  { sensor: "VIIRS", platform: "NOAA-21", start: "January 2024" }
];

function timestamp(value: string | null | undefined): string {
  if (!value) return "not provided";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : `${parsed.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

export function ProvenanceView() {
  const [metadata, setMetadata] = useState<ApiResult<MetadataResponse> | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    void apiClient.getMetadata().then((result) => {
      if (!active) return;
      setMetadata(result);
      setLoading(false);
    });
    return () => { active = false; };
  }, [reloadKey]);

  const response = metadata?.data;
  const synthetic = metadata?.synthetic ?? false;
  return (
    <section className="provenance-view" aria-labelledby="provenance-heading">
      <div className="workbench-heading"><div><p className="eyebrow">03 / DATA</p><h1 id="provenance-heading">Harmonization &amp; provenance</h1><p className="muted">Source coverage, retrieval freshness, and limits of active-fire detections.</p></div></div>
      {synthetic && <p className="synthetic-banner">Synthetic metadata fixture · not a live NASA FIRMS metadata response.</p>}
      <div className="provenance-grid">
        <section className="provenance-panel">
          <h2>Archive coverage windows</h2>
          <p className="muted">Start dates supplied for this build. Coverage windows do not imply uninterrupted observations or local coverage for every period.</p>
          <table className="coverage-table"><caption>Active-fire sensor archive starts</caption><thead><tr><th>Sensor</th><th>Platform / product</th><th>Archive starts</th></tr></thead><tbody>{COVERAGE_WINDOWS.map((window) => <tr key={`${window.sensor}-${window.platform}`}><td>{window.sensor}</td><td>{window.platform}</td><td>{window.start}</td></tr>)}</tbody></table>
        </section>
        <section className="provenance-panel">
          <h2>Metadata</h2>
          {loading ? <p role="status">Loading metadata…</p> : metadata?.state === "error" || metadata?.state === "unavailable" ? <div role="alert"><p>Metadata is unavailable. {metadata.message ?? "No metadata response."}</p><button type="button" className="small-action" onClick={() => { setLoading(true); setReloadKey((key) => key + 1); }}>Retry metadata</button></div> : <>
            <p>Latest successful ingestion: <strong>{timestamp(response?.freshness.latest_ingested_at)}</strong></p>
            <h3>Products reported by the API</h3>
            {response?.products.length ? <ul className="product-metadata">{response.products.map((product) => <li key={`${product.source}-${product.product}`}><strong>{product.source.toUpperCase()} · {product.product}</strong><span>Version: {product.version ?? "not provided"}</span><span>Coverage: {product.coverage_start ?? "not provided"} to {product.coverage_end ?? "not provided"}</span>{product.limitations.map((limitation, index) => <span key={index}>Limit: {limitation}</span>)}</li>)}</ul> : <p className="muted">Product metadata was not provided.</p>}
          </>}
        </section>
        <section className="provenance-panel provenance-wide">
          <h2>Harmonization method</h2>
          {response?.harmonization.method ? <p>{response.harmonization.method}</p> : <p className="comparability-warning">The harmonization method document is not present in this checkout. Do not treat cross-sensor counts as fully comparable until the method and product semantics are documented.</p>}
          <p className="muted">Method citation: {response?.harmonization.documentation_url ?? "not provided"}</p>
        </section>
        <section className="provenance-panel provenance-wide">
          <h2>Detection limits</h2>
          <ul className="limitations-list">
            <li>A hotspot is a satellite detection, not a confirmed wildfire, fire perimeter, or measurement of burned area.</li>
            <li>Zero returned detections do not prove that no fire occurred.</li>
            <li>MODIS and VIIRS have different archive start dates. A period spanning January 2012 crosses the VIIRS Suomi-NPP start boundary.</li>
            <li>Confidence, FRP, pass, and quality fields retain the source meaning. Missing fields are shown as not provided.</li>
          </ul>
        </section>
      </div>
    </section>
  );
}
