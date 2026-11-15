import type { SnapshotView } from "../../query/useSnapshotQuery";

type Props = { snapshot: SnapshotView; onRetry: () => void };

const EMPTY_COPY = "No satellite hotspot detections were returned for this area and period. This does not prove that no fire occurred.";

export function QueryStatus({ snapshot, onRetry }: Props) {
  if (snapshot.state === "idle" || snapshot.state === "success") return null;
  const copy = snapshot.state === "loading" ? "Loading observations for this selection…"
    : snapshot.state === "empty" ? snapshot.message ?? EMPTY_COPY
      : snapshot.state === "unavailable" ? snapshot.message ?? "This area or period is outside the available sensor archive coverage."
        : snapshot.state === "stale" ? snapshot.message ?? "Showing the previous successful result. It may not match the current selection."
          : snapshot.message ?? "The observation request failed.";
  const retrieved = snapshot.retrievedAt ? new Date(snapshot.retrievedAt) : null;
  const retrievalLabel = retrieved && !Number.isNaN(retrieved.valueOf())
    ? `${retrieved.toISOString().slice(0, 16).replace("T", " ")} UTC`
    : "not provided";
  return (
    <div className={`query-banner query-banner-${snapshot.state}`} role={snapshot.state === "loading" ? "status" : "alert"} aria-live={snapshot.state === "loading" ? "polite" : "assertive"}>
      <div><span>{copy}</span>{snapshot.state === "stale" && <p className="stale-retrieval">Previous successful data retrieved at {retrievalLabel}.</p>}</div>
      {(snapshot.state === "error" || snapshot.state === "stale") && <button type="button" onClick={onRetry}>Retry</button>}
    </div>
  );
}
