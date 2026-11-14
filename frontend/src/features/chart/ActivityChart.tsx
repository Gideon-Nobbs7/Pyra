import type { SummaryBucket } from "../../api/types";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function BarGroup({ title, buckets, labels, compact, onSelect }: {
  title: string;
  buckets: SummaryBucket[];
  labels: string[];
  compact: boolean;
  onSelect?: (bucket: SummaryBucket) => void;
}) {
  const values = new Map(buckets.map((bucket, index) => [labels[index], bucket]));
  const max = Math.max(1, ...buckets.map(({ count }) => count));
  return (
    <section className={`activity-chart ${compact ? "activity-chart-compact" : ""}`} aria-label={title}>
      <div className="section-title-row"><h3>{title}</h3>{compact && <span className="muted">from this query</span>}</div>
      <div className="chart-bars" role="list" aria-label={`${title} detections`}>
        {labels.map((label) => {
          const bucket = values.get(label);
          const height = bucket ? Math.max(4, (bucket.count / max) * 100) : 0;
          return (
            <div className="chart-bar-column" role="listitem" key={label}>
              {bucket && onSelect ? (
                <button className="chart-bar-button" type="button" onClick={() => onSelect(bucket)} aria-label={`${label}: ${bucket.count} detections. Select this period.`}>
                  <span className="chart-bar-value">{bucket.count}</span><span className="chart-bar" style={{ height: `${height}%` }} />
                </button>
              ) : <><span className="chart-bar-value">{bucket?.count ?? "—"}</span><span className="chart-bar" style={{ height: `${height}%` }} /> </>}
              <span className="chart-bar-label">{label}</span>
            </div>
          );
        })}
      </div>
      {!buckets.length && <p className="muted">No summary buckets were returned for this selection.</p>}
    </section>
  );
}

export function ActivityChart({ monthly, daily, selectedMonth, compact = false, onSelectPeriod }: {
  monthly: SummaryBucket[];
  daily: SummaryBucket[];
  selectedMonth: string;
  compact?: boolean;
  onSelectPeriod?: (bucket: SummaryBucket) => void;
}) {
  const monthOfYear = MONTH_LABELS.map((month, index) => {
    const count = monthly.filter((bucket) => Number(bucket.start.slice(5, 7)) === index + 1).reduce((total, bucket) => total + bucket.count, 0);
    const entries = monthly.filter((bucket) => Number(bucket.start.slice(5, 7)) === index + 1);
    return { start: `${selectedMonth.slice(0, 4)}-${String(index + 1).padStart(2, "0")}-01`, end: entries.at(-1)?.end ?? "", count };
  });
  const seasonalBuckets = monthly.length ? monthOfYear.filter((_, index) => monthly.some((bucket) => Number(bucket.start.slice(5, 7)) === index + 1)) : [];
  const dailyLabels = daily.map((bucket) => bucket.start.slice(5, 10));
  const seasonLabels = seasonalBuckets.map((bucket) => MONTH_LABELS[Number(bucket.start.slice(5, 7)) - 1]);
  const toMonthRange = (bucket: SummaryBucket) => {
    const month = bucket.start.slice(0, 7);
    const date = new Date(`${month}-01T00:00:00Z`);
    const next = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0, 23, 59, 59, 999));
    onSelectPeriod?.({ start: `${month}-01`, end: next.toISOString(), count: bucket.count });
  };
  return (
    <div className="activity-chart-stack">
      <BarGroup title={compact ? "Activity summary" : "Seasonal activity by month"} buckets={seasonalBuckets} labels={seasonLabels} compact={compact} onSelect={onSelectPeriod ? toMonthRange : undefined} />
      {!compact && <BarGroup title="Daily detections in selected period" buckets={daily} labels={dailyLabels} compact={false} onSelect={onSelectPeriod} />}
    </div>
  );
}
