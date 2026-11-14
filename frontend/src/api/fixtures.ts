import type {
  ApiResult,
  ComparisonResponse,
  HealthResponse,
  MetadataResponse,
  Observation,
  ObservationPage,
  ObservationQuery,
  ObservationSummaryQuery,
  SummaryResponse
} from "./types";

/** Synthetic demo records only. These are not NASA FIRMS observations. */
export const syntheticObservations: Observation[] = [
  {
    id: "synthetic-viirs-001", source: "viirs", source_record_id: null,
    observed_at: "2026-11-14T03:42:00Z", ingested_at: "2026-11-14T03:48:00Z",
    latitude: 40.031, longitude: -2.141, instrument: null, platform: null,
    confidence: "nominal", frp: 18.4, frp_unit: "MW", quality_flags: null,
    product_version: null
  },
  {
    id: "synthetic-modis-002", source: "modis", source_record_id: null,
    observed_at: "2026-11-12T12:05:00Z", ingested_at: "2026-11-12T12:12:00Z",
    latitude: 39.842, longitude: -2.684, instrument: null, platform: null,
    confidence: "nominal", frp: 11.2, frp_unit: "MW", quality_flags: null,
    product_version: null
  },
  {
    id: "synthetic-viirs-003", source: "viirs", source_record_id: null,
    observed_at: "2026-11-09T09:18:00Z", ingested_at: "2026-11-09T09:24:00Z",
    latitude: 40.411, longitude: -1.884, instrument: null, platform: null,
    confidence: "nominal", frp: 7.8, frp_unit: "MW", quality_flags: null,
    product_version: null
  },
  {
    id: "synthetic-modis-004", source: "modis", source_record_id: null,
    observed_at: "2026-11-07T17:20:00Z", ingested_at: "2026-11-07T17:28:00Z",
    latitude: 40.218, longitude: -2.944, instrument: null, platform: null,
    confidence: "nominal", frp: 5.6, frp_unit: "MW", quality_flags: null,
    product_version: null
  }
];

const demoQuery: ObservationQuery = {
  start: "2026-11-07T00:00:00Z",
  end: "2026-11-15T00:00:00Z",
  bbox: [-3.5, 39.5, -1.5, 41]
};

export function createSyntheticFixture<T>(
  data: T,
  state: "success" | "empty" | "unavailable" | "error" | "stale" = "success",
  message?: string
): ApiResult<T> {
  return {
    state,
    origin: "synthetic-fixture",
    data: state === "unavailable" || state === "error" ? null : data,
    message: message ?? `Synthetic fixture data (${state} state).`,
    synthetic: true
  };
}

export function fixtureFor<T>(
  state: "empty" | "unavailable" | "error" | "stale",
  fallbackData: T
): ApiResult<T> {
  return createSyntheticFixture(fallbackData, state, `Synthetic fixture: ${state} state.`);
}

export function syntheticObservationPage(query: ObservationQuery): ObservationPage {
  const [west, south, east, north] = query.bbox;
  const filtered = syntheticObservations.filter((item) =>
    item.latitude >= south && item.latitude <= north &&
    item.longitude >= west && item.longitude <= east &&
    item.observed_at >= query.start && item.observed_at <= query.end &&
    (!query.products || query.products.includes(item.source))
  );
  const limit = Math.max(1, Math.min(query.limit ?? 100, 1000));
  const page = filtered.slice(0, limit);
  return {
    data: page,
    count: filtered.length,
    filters: query,
    coverage: { start: "2026-11-07T00:00:00Z", end: "2026-11-14T23:59:59Z", available: true },
    freshness: { fetched_at: "2026-11-14T06:36:00Z", latest_ingested_at: "2026-11-14T03:48:00Z" },
    pagination: { limit, next_cursor: filtered.length > limit ? String(limit) : null }
  };
}

export function syntheticSummary(query: ObservationSummaryQuery): SummaryResponse {
  const page = syntheticObservationPage(query);
  const bucketCounts = new Map<string, number>();
  for (const observation of page.data) {
    const date = new Date(observation.observed_at);
    const key = query.interval === "year" ? `${date.getUTCFullYear()}` :
      query.interval === "month" ? `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}` :
      date.toISOString().slice(0, 10);
    bucketCounts.set(key, (bucketCounts.get(key) ?? 0) + 1);
  }
  const data = [...bucketCounts].map(([start, count]) => ({ start, end: start, count }));
  return { ...page, data, count: page.count };
}

export function syntheticComparison(query: ObservationQuery): ComparisonResponse {
  const count = syntheticObservationPage(query).count;
  return {
    filters: query,
    coverage: { start: "2026-11-07T00:00:00Z", end: "2026-11-14T23:59:59Z", available: true },
    freshness: { fetched_at: "2026-11-14T06:36:00Z", latest_ingested_at: "2026-11-14T03:48:00Z" },
    selected: { start: query.start, end: query.end, count },
    baseline: { start: "2002-01-01T00:00:00Z", end: "2025-12-31T23:59:59Z", median_count: 0, years: 24 },
    anomaly: { count_delta: count, direction: count > 0 ? "above" : "at_baseline" }
  };
}

export const syntheticHealth: HealthResponse = {
  status: "degraded", checked_at: "2026-11-14T06:36:00Z", database: "unavailable"
};

export const syntheticMetadata: MetadataResponse = {
  products: [
    { source: "modis", product: "Synthetic MODIS example", version: null, coverage_start: null, coverage_end: null, limitations: ["Synthetic fixture; not source data."] },
    { source: "viirs", product: "Synthetic VIIRS example", version: null, coverage_start: null, coverage_end: null, limitations: ["Synthetic fixture; not source data."] }
  ],
  harmonization: { method: "Not applied to synthetic fixture records.", documentation_url: null },
  freshness: { latest_ingested_at: null }
};

export const syntheticDemoQuery = demoQuery;
