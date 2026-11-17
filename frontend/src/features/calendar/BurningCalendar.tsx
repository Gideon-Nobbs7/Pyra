import type { SummaryBucket } from "../../api/types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function intensity(count: number | undefined): string {
  if (count === undefined) return "calendar-cell-unreported";
  if (count === 0) return "calendar-cell-zero";
  if (count < 5) return "calendar-cell-low";
  if (count < 20) return "calendar-cell-medium";
  return "calendar-cell-high";
}

export function BurningCalendar({ buckets, selectedMonth, onSelectMonth }: {
  buckets: SummaryBucket[];
  selectedMonth: string;
  onSelectMonth: (month: string) => void;
}) {
  const year = selectedMonth.slice(0, 4);
  const counts = new Map<string, number>();
  for (const bucket of buckets) {
    const month = bucket.start.slice(0, 7);
    if (month.startsWith(`${year}-`)) counts.set(month, (counts.get(month) ?? 0) + bucket.count);
  }
  // Months without rows render as zero, not missing.
  for (let index = 0; index < 12; index += 1) {
    const key = `${year}-${String(index + 1).padStart(2, "0")}`;
    if (!counts.has(key)) counts.set(key, 0);
  }
  return (
    <section className="burning-calendar" aria-labelledby="burning-calendar-title">
      <div className="section-title-row"><h3 id="burning-calendar-title">Burning activity calendar</h3><span className="muted">{year} · selected area</span></div>
      <div className="calendar-grid" role="group" aria-label={`Monthly hotspot detections for ${year}`}>
        {MONTHS.map((label, index) => {
          const key = `${year}-${String(index + 1).padStart(2, "0")}`;
          const count = counts.get(key) ?? 0;
          return <button key={key} type="button" className={`calendar-cell ${intensity(count)} ${selectedMonth === key ? "calendar-cell-selected" : ""}`} onClick={() => onSelectMonth(key)} aria-pressed={selectedMonth === key} aria-label={`${label} ${year}: ${count === undefined ? "count not provided" : `${count} detections`}. Select month.`}>
            <span>{label}</span><strong>{count === undefined ? "—" : count.toLocaleString()}</strong>
          </button>;
        })}
      </div>
      <div className="calendar-legend" aria-label="Calendar intensity legend">
        <span>Count in query</span><i className="calendar-cell-zero" /> 0<i className="calendar-cell-low" /> 1–4<i className="calendar-cell-medium" /> 5–19<i className="calendar-cell-high" /> 20+<i className="calendar-cell-unreported" /> not returned
      </div>
    </section>
  );
}
