import { useState } from "react";
import type { Observation } from "../../api/types";
import type { QuerySelection } from "../../query/useSnapshotQuery";
import { getCorroboration, getObservationPass } from "../details/ObservationDetails";

type ActiveFilters = Record<string, string>;

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  return `"${String(value).replaceAll('"', '""')}"`;
}

function csvFor(observations: Observation[], query: QuerySelection, retrievedAt: string | null, synthetic: boolean, activeFilters: ActiveFilters): string {
  const metadata = [
    "# metadata: Pyra observation export",
    "# source: NASA FIRMS MODIS and VIIRS active fire detections",
    `# area: ${query.areaLabel}`,
    `# center_latitude: ${query.center.lat}`,
    `# center_longitude: ${query.center.lon}`,
    `# radius_km: ${query.radiusKm}`,
    `# bbox_west_south_east_north: ${query.bbox.join(",")}`,
    `# observed_start_utc: ${query.start}`,
    `# observed_end_utc: ${query.end}`,
    `# products: ${query.products.join(",")}`,
    `# sensor_scope: ${query.sensorScope}`,
    ...Object.entries(activeFilters).map(([name, value]) => `# table_filter_${name}: ${value}`),
    `# retrieved_at_utc: ${retrievedAt ?? "not provided"}`,
    `# records_in_current_snapshot: ${observations.length}`,
    `# synthetic_fixture: ${synthetic ? "yes" : "no"}`,
    "# limitations: A hotspot is a detection, not a confirmed fire or burned area. Zero detections do not prove no fire occurred."
  ];
  const columns: Array<keyof Observation> = ["id", "source", "source_record_id", "observed_at", "ingested_at", "latitude", "longitude", "instrument", "platform", "confidence", "frp", "frp_unit", "quality_flags", "product_version"];
  const header = [...columns, "pass", "cross_sensor_corroborated"];
  const rows = observations.map((observation) => [
    ...columns.map((column) => csvCell(observation[column])),
    csvCell(getObservationPass(observation)),
    csvCell(getCorroboration(observation))
  ]);
  return [...metadata, header.map(csvCell).join(","), ...rows.map((row) => row.join(","))].join("\r\n");
}

export function ExportTools({ observations, query, retrievedAt, synthetic, activeFilters = {} }: {
  observations: Observation[];
  query: QuerySelection;
  retrievedAt: string | null;
  synthetic: boolean;
  activeFilters?: ActiveFilters;
}) {
  const [message, setMessage] = useState("");
  const citation = `Pyra · NASA FIRMS MODIS/VIIRS active-fire observations (https://firms.modaps.eosdis.nasa.gov/). Area: ${query.areaLabel} (${query.center.lat}, ${query.center.lon}; ${query.radiusKm} km). Period: ${query.start} to ${query.end} UTC. Products: ${query.products.join(", ")}. Retrieval: ${retrievedAt ?? "not provided"}.${synthetic ? " Synthetic fixture data." : ""}`;

  const download = () => {
    const blob = new Blob([csvFor(observations, query, retrievedAt, synthetic, activeFilters)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `pyra-${query.start.slice(0, 10)}-to-${query.end.slice(0, 10)}.csv`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage(`Downloaded ${observations.length} records from the current filtered snapshot.`);
  };

  const copyCitation = async () => {
    try {
      await navigator.clipboard.writeText(citation);
      setMessage("Provenance citation copied.");
    } catch {
      setMessage("Clipboard access is unavailable. Select and copy the citation below.");
    }
  };

  return <section className="export-tools" aria-labelledby="export-heading">
    <div className="section-title-row"><h3 id="export-heading">Export &amp; cite</h3><span className="muted">{observations.length} filtered records loaded</span></div>
    <div className="export-actions"><button type="button" className="small-action" onClick={download} disabled={!observations.length}>Download CSV</button><button type="button" className="small-action secondary-action" onClick={copyCitation}>Copy provenance citation</button></div>
    <p className="citation-text">{citation}</p>
    <p className="muted">The CSV includes the loaded records matching the active table filters and a comment metadata block. Null source fields remain blank in CSV cells.</p>
    <p className="sr-only" aria-live="polite">{message}</p>
    {message && <p className="area-feedback">{message}</p>}
  </section>;
}
