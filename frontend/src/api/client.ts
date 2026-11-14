import {
  createSyntheticFixture,
  fixtureFor,
  syntheticComparison,
  syntheticHealth,
  syntheticMetadata,
  syntheticObservationPage,
  syntheticSummary
} from "./fixtures";
import type {
  ApiClientOptions,
  ApiResult,
  ApiRequestOptions,
  ComparisonResponse,
  DemoStateOverride,
  HealthResponse,
  MetadataResponse,
  Observation,
  ObservationPage,
  ObservationQuery,
  ObservationSummaryQuery,
  SummaryResponse
} from "./types";

const DEFAULT_API_BASE_URL = "/api/v1";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");

export class ApiClientError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ApiClientError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isObservation(value: unknown): value is Observation {
  return isRecord(value) && typeof value.id === "string" &&
    (value.source === "modis" || value.source === "viirs") &&
    nullableString(value.source_record_id) && nullableString(value.instrument) &&
    nullableString(value.platform) && nullableString(value.frp_unit) &&
    nullableString(value.product_version) && nullableString(value.observed_at) &&
    nullableString(value.ingested_at) && nullableNumber(value.frp) &&
    nullableStringOrNumber(value.confidence) && nullableStringOrNumber(value.quality_flags) &&
    typeof value.observed_at === "string" && typeof value.ingested_at === "string" &&
    typeof value.latitude === "number" && typeof value.longitude === "number";
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function nullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function nullableStringOrNumber(value: unknown): value is string | number | null {
  return value === null || typeof value === "string" || typeof value === "number";
}

function isQuery(value: unknown): boolean {
  return isRecord(value) && typeof value.start === "string" && typeof value.end === "string" &&
    Array.isArray(value.bbox) && value.bbox.length === 4 && value.bbox.every((part) => typeof part === "number");
}

function isContext(value: Record<string, unknown>): boolean {
  return isQuery(value.filters) && isRecord(value.coverage) && typeof value.coverage.available === "boolean" &&
    nullableString(value.coverage.start) && nullableString(value.coverage.end) &&
    isRecord(value.freshness) && typeof value.freshness.fetched_at === "string" &&
    nullableString(value.freshness.latest_ingested_at);
}

function isObservationPage(value: unknown): value is ObservationPage {
  return isRecord(value) && Array.isArray(value.data) && value.data.every(isObservation) &&
    typeof value.count === "number" && isRecord(value.pagination) && isContext(value);
}

function isSummaryResponse(value: unknown): value is SummaryResponse {
  return isRecord(value) && Array.isArray(value.data) &&
    value.data.every((bucket) => isRecord(bucket) && typeof bucket.start === "string" && typeof bucket.end === "string" && typeof bucket.count === "number") &&
    typeof value.count === "number" && isContext(value);
}

function isComparisonResponse(value: unknown): value is ComparisonResponse {
  return isRecord(value) && isRecord(value.selected) && typeof value.selected.start === "string" &&
    typeof value.selected.end === "string" && typeof value.selected.count === "number" &&
    isRecord(value.baseline) && typeof value.baseline.start === "string" && typeof value.baseline.end === "string" &&
    typeof value.baseline.median_count === "number" && typeof value.baseline.years === "number" &&
    (value.baseline.sample_years === undefined || (Array.isArray(value.baseline.sample_years) && value.baseline.sample_years.every((year) => typeof year === "number"))) &&
    isRecord(value.anomaly) && typeof value.anomaly.count_delta === "number" &&
    (value.anomaly.direction === "above" || value.anomaly.direction === "below" || value.anomaly.direction === "at_baseline") && isContext(value);
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return isRecord(value) && (value.status === "ok" || value.status === "degraded") &&
    typeof value.checked_at === "string" && (value.database === "available" || value.database === "unavailable");
}

function isMetadataResponse(value: unknown): value is MetadataResponse {
  return isRecord(value) && Array.isArray(value.products) && value.products.every((product) =>
    isRecord(product) && (product.source === "modis" || product.source === "viirs") &&
    typeof product.product === "string" && nullableString(product.version) &&
    nullableString(product.coverage_start) && nullableString(product.coverage_end) &&
    Array.isArray(product.limitations) && product.limitations.every((item) => typeof item === "string")
  ) && isRecord(value.harmonization) && typeof value.harmonization.method === "string" &&
    nullableString(value.harmonization.documentation_url) && isRecord(value.freshness) &&
    nullableString(value.freshness.latest_ingested_at);
}

function isUnavailable(value: unknown): boolean {
  return isRecord(value) && isRecord(value.coverage) && value.coverage.available === false;
}

function isEmpty(value: unknown): boolean {
  return isRecord(value) && typeof value.count === "number" && value.count === 0;
}

function stateFromData<T>(data: T): ApiResult<T> {
  if (isUnavailable(data)) return { state: "unavailable", origin: "api", data, synthetic: false, message: "Coverage is unavailable for this selection." };
  if (isEmpty(data)) return { state: "empty", origin: "api", data, synthetic: false, message: "No satellite hotspot detections were returned for this area and period. This does not prove that no fire occurred." };
  return { state: "success", origin: "api", data, synthetic: false };
}

function queryString(query: ObservationQuery, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({
    start: query.start,
    end: query.end,
    bbox: query.bbox.join(","),
    ...(query.products ? { products: query.products.join(",") } : {}),
    ...(query.limit !== undefined ? { limit: String(query.limit) } : {}),
    ...(query.cursor ? { cursor: query.cursor } : {}),
    ...extra
  });
  return params.toString();
}

function emptyFixture<T>(value: T): T {
  if (!isRecord(value)) return value;
  const emptied: Record<string, unknown> = { ...value };
  if (Array.isArray(emptied.data)) emptied.data = [];
  if (typeof emptied.count === "number") emptied.count = 0;
  if (isRecord(emptied.selected)) emptied.selected = { ...emptied.selected, count: 0 };
  if (isRecord(emptied.anomaly)) emptied.anomaly = { ...emptied.anomaly, count_delta: 0, direction: "at_baseline" };
  return emptied as T;
}

function makeFixture<T>(data: T, override?: DemoStateOverride): ApiResult<T> {
  if (!override) return createSyntheticFixture(data);
  const overridden = override === "empty" ? emptyFixture(data) : data;
  return fixtureFor(override, overridden);
}

function toApiError(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) return error;
  return new ApiClientError(error instanceof Error ? error.message : "The API request failed.");
}

export function createApiClient(options: ApiClientOptions = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const configuredDemoMode = import.meta.env.VITE_DEMO_MODE;
  const demoMode = options.demoMode ?? (configuredDemoMode === undefined ? import.meta.env.DEV : configuredDemoMode === "true");

  async function get<T>(
    path: string,
    validate: (value: unknown) => value is T,
    fixture: () => T,
    accept = "application/json",
    signal?: AbortSignal
  ): Promise<ApiResult<T>> {
    if (options.stateOverride) {
      try {
        return makeFixture(fixture(), options.stateOverride);
      } catch (error) {
        return { state: "error", origin: "synthetic-fixture", data: null, synthetic: true, message: toApiError(error).message };
      }
    }

    try {
      const response = await fetchImpl(`${API_BASE_URL}${path}`, {
        headers: { Accept: accept },
        signal
      });

      if ([502, 503, 504].includes(response.status)) {
        if (demoMode) return createSyntheticFixture(fixture(), "success", `Synthetic fixture data is shown because the API returned ${response.status}.`);
        return { state: "unavailable", origin: "api", data: null, synthetic: false, message: "The observation service is currently unavailable." };
      }

      if (!response.ok) {
        throw new ApiClientError(`The API request failed (${response.status}).`, response.status);
      }

      if (accept === "text/csv") {
        return stateFromData(await response.blob() as T);
      }

      const value: unknown = await response.json();
      if (!validate(value)) throw new ApiClientError("The API returned data that does not match the provisional frontend contract.", response.status);
      return stateFromData(value);
    } catch (error) {
      const apiError = toApiError(error);
      if (demoMode && error instanceof TypeError) {
        return createSyntheticFixture(fixture(), "success", "Synthetic fixture data is shown because the API could not be reached.");
      }
      return { state: "error", origin: "api", data: null, synthetic: false, message: apiError.message };
    }
  }

  return {
    getHealth: () => get("/health", isHealthResponse, () => syntheticHealth),
    getObservations: (query: ObservationQuery, requestOptions: ApiRequestOptions = {}) => get(
      `/observations?${queryString(query)}`,
      isObservationPage,
      () => syntheticObservationPage(query),
      "application/json",
      requestOptions.signal
    ),
    getObservation: (id: string) => get(
      `/observations/${encodeURIComponent(id)}`,
      isObservation,
      () => {
        const observation = syntheticObservationPage({ ...defaultFixtureQuery, start: "2000-01-01T00:00:00Z", end: "2100-01-01T00:00:00Z" }).data.find((item) => item.id === id);
        if (!observation) throw new ApiClientError("No synthetic fixture exists for this observation id.", 404);
        return observation;
      }
    ),
    getSummary: (query: ObservationSummaryQuery, requestOptions: ApiRequestOptions = {}) => get(
      `/summary?${queryString(query, { interval: query.interval })}`,
      isSummaryResponse,
      () => syntheticSummary(query),
      "application/json",
      requestOptions.signal
    ),
    getComparison: (query: ObservationQuery, requestOptions: ApiRequestOptions = {}) => get(
      `/comparison?${queryString(query)}`,
      isComparisonResponse,
      () => syntheticComparison(query),
      "application/json",
      requestOptions.signal
    ),
    exportObservations: (query: ObservationQuery) => get<Blob>(
      `/observations/export?${queryString(query)}`,
      (value): value is Blob => value instanceof Blob,
      () => new Blob([syntheticCsv(query)], { type: "text/csv;charset=utf-8" }),
      "text/csv"
    ),
    getMetadata: () => get("/metadata", isMetadataResponse, () => syntheticMetadata)
  };
}

const defaultFixtureQuery: ObservationQuery = {
  start: "2026-11-07T00:00:00Z", end: "2026-11-15T00:00:00Z", bbox: [-180, -90, 180, 90]
};

function syntheticCsv(query: ObservationQuery): string {
  const rows = syntheticObservationPage(query).data;
  const columns: Array<keyof Observation> = ["id", "source", "source_record_id", "observed_at", "ingested_at", "latitude", "longitude", "instrument", "platform", "confidence", "frp", "frp_unit", "quality_flags", "product_version"];
  return [columns.join(","), ...rows.map((row) => columns.map((column) => {
    const value = row[column] ?? "";
    return `"${String(value).replaceAll('"', '""')}"`;
  }).join(","))].join("\r\n");
}

export const apiClient = createApiClient();
