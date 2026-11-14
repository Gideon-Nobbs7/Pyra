import type { ComparisonResponse } from "../../api/types";
import type { QuerySelection } from "../../query/useSnapshotQuery";

const VIIRS_START = "2012-01-01T00:00:00.000Z";

export function HistoricalComparison({ comparison, query, synthetic }: {
  comparison: ComparisonResponse | null;
  query: QuerySelection;
  synthetic: boolean;
}) {
  const spansViirsStart = query.start < VIIRS_START && query.end >= VIIRS_START && query.sensorScope !== "modis";
  if (!comparison) return <section className="comparison-panel"><h3>Historical baseline</h3><p className="muted">Comparison data is not available for this query.</p></section>;
  const observed = comparison.selected.count;
  const median = comparison.baseline.median_count;
  const isAnomaly = observed > median;
  return (
    <section className="comparison-panel" aria-labelledby="comparison-title">
      <div className="section-title-row"><h3 id="comparison-title">Historical baseline</h3>{synthetic && <span className="synthetic-label">Synthetic</span>}</div>
      <div className="comparison-values">
        <div><span>Observed detections</span><strong>{observed.toLocaleString()}</strong></div>
        <div><span>Historical median</span><strong>{median.toLocaleString()}</strong></div>
      </div>
      <p className={isAnomaly ? "anomaly-flag anomaly-above" : "anomaly-flag"}>
        {isAnomaly ? "Above median · observed anomaly" : "At or below the historical median"}
      </p>
      <p className="muted">Baseline: {comparison.baseline.start.slice(0, 10)} to {comparison.baseline.end.slice(0, 10)} · {comparison.baseline.years} sample years</p>
      {comparison.baseline.sample_years?.length ? <p className="muted">Sample years: {comparison.baseline.sample_years.join(", ")}</p> : <p className="muted">Sample years: not provided</p>}
      <p className="muted">Count difference: {observed - median > 0 ? "+" : ""}{observed - median}</p>
      {spansViirsStart && <p className="comparability-warning" role="note">This period crosses the VIIRS archive start in January 2012. Sensor coverage changes within the selected period, so cross-sensor counts may not be directly comparable.</p>}
      <p className="muted">An anomaly describes observed activity against the selected historical baseline. It is not a forecast.</p>
    </section>
  );
}
