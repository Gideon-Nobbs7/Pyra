import type { Observation } from "../../api/types";

function display(value: unknown): string {
  return value === null || value === undefined || value === "" ? "not provided" : String(value);
}

function detailValue(observation: Observation, keys: string[]): unknown {
  const properties = observation.raw_properties;
  if (!properties) return null;
  for (const key of keys) if (properties[key] !== undefined && properties[key] !== null) return properties[key];
  return null;
}

export function ObservationDetails({ observation }: { observation: Observation | null }) {
  if (!observation) return <p className="muted">Select a row or globe marker to inspect an observation.</p>;
  const pass = detailValue(observation, ["day_night", "pass"]);
  const corroboration = detailValue(observation, ["cross_sensor_corroborated", "corroborated"]);
  return (
    <dl className="observation-details">
      <div><dt>Source / sensor</dt><dd>{display(observation.source.toUpperCase())}</dd></div>
      <div><dt>Product version</dt><dd>{display(observation.product_version)}</dd></div>
      <div><dt>Platform</dt><dd>{display(observation.platform)}</dd></div>
      <div><dt>Instrument</dt><dd>{display(observation.instrument)}</dd></div>
      <div><dt>Observed at (UTC)</dt><dd>{display(observation.observed_at)}</dd></div>
      <div><dt>Ingested at (UTC)</dt><dd>{display(observation.ingested_at)}</dd></div>
      <div><dt>Latitude</dt><dd>{display(observation.latitude)}</dd></div>
      <div><dt>Longitude</dt><dd>{display(observation.longitude)}</dd></div>
      <div><dt>Pass</dt><dd>{display(pass)}</dd></div>
      <div><dt>Confidence</dt><dd>{display(observation.confidence)}</dd></div>
      <div><dt>FRP</dt><dd>{display(observation.frp)} {observation.frp === null ? "" : display(observation.frp_unit)}</dd></div>
      <div><dt>Cross-sensor corroboration</dt><dd>{display(corroboration)}</dd></div>
      <div><dt>Quality flags</dt><dd>{display(observation.quality_flags)}</dd></div>
      <div><dt>Source record ID</dt><dd>{display(observation.source_record_id)}</dd></div>
    </dl>
  );
}

export function getObservationPass(observation: Observation): "Day" | "Night" | null {
  const raw = detailValue(observation, ["day_night", "pass"]);
  if (typeof raw !== "string") return null;
  const normalized = raw.toLowerCase();
  if (normalized === "d" || normalized.includes("day")) return "Day";
  if (normalized === "n" || normalized.includes("night")) return "Night";
  return null;
}

export function getCorroboration(observation: Observation): boolean | null {
  const raw = detailValue(observation, ["cross_sensor_corroborated", "corroborated"]);
  return typeof raw === "boolean" ? raw : null;
}
