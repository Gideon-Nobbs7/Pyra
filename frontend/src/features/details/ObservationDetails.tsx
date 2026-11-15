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

export function ObservationDetails({ observation, corroborated }: { observation: Observation | null; corroborated?: boolean | null }) {
  if (!observation) return <p className="muted">Select a row or globe marker to inspect an observation.</p>;
  const pass = detailValue(observation, ["day_night", "pass"]);
  const crossSensor = corroborated ?? resolveCorroboration(observation, null);
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
      <div><dt title="Seen by both MODIS and VIIRS in the same cell on the same day">Cross-sensor corroboration</dt><dd>{crossSensor === null ? "not provided" : crossSensor ? "Yes — both sensors saw it" : "No — one sensor only"}</dd></div>
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

/** Cell a detection falls in for cross-sensor matching: ~1 km grid cell + UTC day. */
export function observationCellKey(observation: Pick<Observation, "latitude" | "longitude" | "observed_at">): string {
  return `${observation.latitude.toFixed(2)},${observation.longitude.toFixed(2)},${observation.observed_at.slice(0, 10)}`;
}

/**
 * Cross-sensor corroboration computed from the loaded set: true when both
 * MODIS and VIIRS saw the same cell on the same day. A same-day, same-cell
 * detection by both sensors raises confidence it is a real hotspot rather
 * than a sensor artifact (sun glint, scan-edge noise).
 */
export function buildCorroborationMap(observations: Observation[]): Map<string, boolean> {
  const sensors = new Map<string, Set<string>>();
  for (const item of observations) {
    const key = observationCellKey(item);
    let set = sensors.get(key);
    if (!set) {
      set = new Set();
      sensors.set(key, set);
    }
    set.add(item.source);
  }
  const result = new Map<string, boolean>();
  for (const [key, set] of sensors) result.set(key, set.size > 1);
  return result;
}

export function resolveCorroboration(observation: Observation, map: Map<string, boolean> | null): boolean | null {
  const raw = getCorroboration(observation);
  if (raw !== null) return raw;
  if (!map) return null;
  return map.get(observationCellKey(observation)) ?? null;
}
