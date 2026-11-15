import { useMemo, useState } from "react";
import type { Observation } from "../../api/types";
import type { QuerySelection } from "../../query/useSnapshotQuery";
import { ExportTools } from "../export/ExportTools";
import { buildCorroborationMap, getObservationPass, resolveCorroboration } from "../details/ObservationDetails";
import { ObservationDetails } from "../details/ObservationDetails";

type Sensor = "all" | "modis" | "viirs";
type Pass = "all" | "Day" | "Night" | "not-provided";
type CorroborationFilter = "all" | "yes" | "no" | "not-provided";
type Sort = "time" | "frp" | "sensor";

function textValue(value: unknown): string {
  return value === null || value === undefined || value === "" ? "not provided" : String(value);
}

function corroborationLabel(value: boolean | null): string {
  return value === null ? "not provided" : value ? "Yes" : "No";
}

export function RecordsWorkbench({ observations, selectedId, onSelect, query, retrievedAt, synthetic }: {
  observations: Observation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  query: QuerySelection;
  retrievedAt: string | null;
  synthetic: boolean;
}) {
  const [sensor, setSensor] = useState<Sensor>("all");
  const [pass, setPass] = useState<Pass>("all");
  const [confidence, setConfidence] = useState("all");
  const [corroboration, setCorroboration] = useState<CorroborationFilter>("all");
  const [sort, setSort] = useState<Sort>("time");
  const [search, setSearch] = useState("");

  const confidenceOptions = useMemo(() => [...new Set(observations.map((item) => item.confidence === null ? "not provided" : String(item.confidence)))].sort(), [observations]);
  const corroborationMap = useMemo(() => buildCorroborationMap(observations), [observations]);
  const filtered = useMemo(() => observations.filter((item) => {
    const itemPass = getObservationPass(item);
    const itemCorroboration = resolveCorroboration(item, corroborationMap);
    const confidenceText = item.confidence === null ? "not provided" : String(item.confidence);
    const matchesSearch = !search || `${item.id} ${item.platform ?? ""} ${item.instrument ?? ""}`.toLowerCase().includes(search.toLowerCase());
    return (sensor === "all" || item.source === sensor) &&
      (pass === "all" || (pass === "not-provided" ? itemPass === null : itemPass === pass)) &&
      (confidence === "all" || confidenceText === confidence) &&
      (corroboration === "all" || (corroboration === "yes" && itemCorroboration === true) || (corroboration === "no" && itemCorroboration === false) || (corroboration === "not-provided" && itemCorroboration === null)) &&
      matchesSearch;
  }).sort((a, b) => {
    if (sort === "time") return b.observed_at.localeCompare(a.observed_at);
    if (sort === "sensor") return a.source.localeCompare(b.source) || b.observed_at.localeCompare(a.observed_at);
    if (a.frp === null) return b.frp === null ? 0 : 1;
    if (b.frp === null) return -1;
    return b.frp - a.frp;
  }), [observations, sensor, pass, confidence, corroboration, corroborationMap, sort, search]);

  const selected = observations.find(({ id }) => id === selectedId) ?? null;
  return (
    <section className="records-workbench" aria-labelledby="records-heading">
      <div className="workbench-heading">
        <div><p className="eyebrow">02 / RECORDS</p><h1 id="records-heading">Records &amp; analytics</h1><p className="muted">Filter the observations returned for the locked area and period.</p></div>
        <span className="record-count">{filtered.length} / {observations.length} loaded</span>
      </div>
      <div className="records-filters" aria-label="Observation filters">
        <label>Sensor<select value={sensor} onChange={(event) => setSensor(event.currentTarget.value as Sensor)}><option value="all">All sensors</option><option value="modis">MODIS</option><option value="viirs">VIIRS</option></select></label>
        <label>Pass<select value={pass} onChange={(event) => setPass(event.currentTarget.value as Pass)}><option value="all">All passes</option><option value="Day">Day</option><option value="Night">Night</option><option value="not-provided">Not provided</option></select></label>
        <label>Confidence<select value={confidence} onChange={(event) => setConfidence(event.currentTarget.value)}><option value="all">All confidence values</option>{confidenceOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label title="Corroborated means both MODIS and VIIRS saw the same cell on the same day">Cross-sensor corroboration<select value={corroboration} onChange={(event) => setCorroboration(event.currentTarget.value as CorroborationFilter)}><option value="all">All</option><option value="yes">Corroborated</option><option value="no">Not corroborated</option><option value="not-provided">Not provided</option></select></label>
        <label>Sort by<select value={sort} onChange={(event) => setSort(event.currentTarget.value as Sort)}><option value="time">Observation time</option><option value="frp">Peak FRP</option><option value="sensor">Sensor</option></select></label>
        <label>Find record<input type="search" value={search} onChange={(event) => setSearch(event.currentTarget.value)} placeholder="ID, platform, instrument" /></label>
      </div>
      <p className="muted">Corroborated means both MODIS and VIIRS saw the same cell on the same day — stronger evidence of a real hotspot.</p>
      <div className="records-table-wrap">
        <table className="records-table">
          <caption>Satellite hotspot observations matching the active filters</caption>
          <thead><tr><th scope="col">Record</th><th scope="col">Sensor</th><th scope="col">Pass</th><th scope="col">Observed at (UTC)</th><th scope="col">Ingested at (UTC)</th><th scope="col">Confidence</th><th scope="col">FRP</th><th scope="col">Corroboration</th></tr></thead>
          <tbody>
            {filtered.map((item) => <tr key={item.id} aria-selected={selectedId === item.id}>
              <td><button className="record-select" type="button" onClick={() => onSelect(item.id)} aria-pressed={selectedId === item.id}>{item.id}</button></td>
              <td>{item.source.toUpperCase()}</td>
              <td>{getObservationPass(item) ?? "not provided"}</td>
              <td>{textValue(item.observed_at)}</td>
              <td>{textValue(item.ingested_at)}</td>
              <td>{textValue(item.confidence)}</td>
              <td>{item.frp === null ? "not provided" : `${item.frp} ${textValue(item.frp_unit)}`}</td>
              <td>{corroborationLabel(resolveCorroboration(item, corroborationMap))}</td>
            </tr>)}
            {!filtered.length && <tr><td className="records-empty" colSpan={8}>No loaded observations match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      <section className="record-inspector" aria-labelledby="record-inspector-heading">
        <h2 id="record-inspector-heading">Observation details</h2>
        <ObservationDetails observation={selected} corroborated={selected ? resolveCorroboration(selected, corroborationMap) : null} />
      </section>
      <ExportTools observations={filtered} query={query} retrievedAt={retrievedAt} synthetic={synthetic} activeFilters={{ sensor, pass, confidence, corroboration, sort, search: search || "none" }} />
    </section>
  );
}
