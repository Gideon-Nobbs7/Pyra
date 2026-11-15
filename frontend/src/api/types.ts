/**
 * Provisional frontend contract based on the repository guide. The agreed
 * docs/api-contract.md is not present in this checkout; align these wire
 * shapes when that contract becomes available.
 */
export type Observation = {
  id: string;
  source: "modis" | "viirs";
  source_record_id: string | null;
  observed_at: string;
  ingested_at: string;
  latitude: number;
  longitude: number;
  instrument: string | null;
  platform: string | null;
  confidence: string | number | null;
  frp: number | null;
  frp_unit: string | null;
  quality_flags: string | number | null;
  product_version: string | null;
  raw_properties?: Record<string, unknown> | null;
};

export type ObservationQuery = {
  start: string;
  end: string;
  bbox: [west: number, south: number, east: number, north: number];
  products?: Array<"modis" | "viirs">;
  limit?: number;
  cursor?: string;
  live?: boolean;
};

export type ResponseContext = {
  filters: ObservationQuery;
  coverage: { start: string | null; end: string | null; available: boolean };
  coverage_reason?: string | null;
  freshness: { fetched_at: string; latest_ingested_at: string | null };
};

export type ObservationPage = ResponseContext & {
  data: Observation[];
  count: number;
  pagination: { limit: number; next_cursor: string | null };
};

export type ObservationSummaryQuery = ObservationQuery & {
  interval: "day" | "month" | "year";
};

export type SummaryBucket = { start: string; end: string; count: number };
export type SummaryResponse = ResponseContext & { data: SummaryBucket[]; count: number };

export type ComparisonResponse = ResponseContext & {
  selected: { start: string; end: string; count: number };
  baseline: { start: string; end: string; median_count: number; years: number; sample_years?: number[] };
  anomaly: { count_delta: number; direction: "above" | "below" | "at_baseline" };
  comparability_warning?: string | null;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  checked_at: string;
  database: "available" | "unavailable";
};

export type MetadataResponse = {
  products: Array<{
    source: "modis" | "viirs";
    product: string;
    version: string | null;
    coverage_start: string | null;
    coverage_end: string | null;
    limitations: string[];
  }>;
  harmonization: { method: string; documentation_url: string | null };
  freshness: { latest_ingested_at: string | null };
};

export type ResultState = "success" | "empty" | "unavailable" | "error" | "stale";
export type ResultOrigin = "api" | "synthetic-fixture";

export type ApiResult<T> = {
  state: ResultState;
  origin: ResultOrigin;
  data: T | null;
  message?: string;
  synthetic: boolean;
};

export type PlaceSuggestion = {
  name: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
};

export type PlaceResponse = { data: PlaceSuggestion[] };

export type DemoStateOverride = "empty" | "unavailable" | "error" | "stale";

export type ApiClientOptions = {
  /** Fixture fallback is enabled by default only in Vite development mode. */
  demoMode?: boolean;
  /** Deterministically surface a state for local demos and UI verification. */
  stateOverride?: DemoStateOverride;
  fetchImpl?: typeof fetch;
};

export type ApiRequestOptions = { signal?: AbortSignal };
