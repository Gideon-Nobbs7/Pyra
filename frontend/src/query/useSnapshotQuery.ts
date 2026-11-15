import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "../api";
import type { ApiResult, ComparisonResponse, Observation, ObservationPage, ObservationQuery, SummaryResponse } from "../api/types";

export type SensorScope = "all" | "modis" | "viirs";
export type QuerySelection = {
  bbox: [west: number, south: number, east: number, north: number];
  areaLabel: string;
  center: { lat: number; lon: number };
  radiusKm: number;
  start: string;
  end: string;
  selectedMonth: string;
  products: Array<"modis" | "viirs">;
  sensorScope: SensorScope;
  liveMode: boolean;
  areaSource: "default" | "place" | "coordinates" | "location";
};

export type SnapshotView = {
  state: "idle" | "loading" | "success" | "empty" | "unavailable" | "error" | "stale";
  query: QuerySelection;
  data: ObservationPage | null;
  dataQuery: QuerySelection | null;
  retrievedAt: string | null;
  synthetic: boolean;
  message?: string;
  summary: ApiResult<SummaryResponse> | null;
  dailySummary: ApiResult<SummaryResponse> | null;
  yearSummary: ApiResult<SummaryResponse> | null;
  comparison: ApiResult<ComparisonResponse> | null;
};

export const DEFAULT_CENTER = { lat: 20, lon: 0 };
export const DEFAULT_RADIUS_KM = 500;
export const WORLD_BBOX: QuerySelection["bbox"] = [-180, -90, 180, 90];

function defaultDates(): Pick<QuerySelection, "start" | "end" | "selectedMonth"> {
  const end = new Date();
  end.setUTCHours(23, 59, 59, 999);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 7);
  return {
    start: start.toISOString(),
    end: end.toISOString(),
    selectedMonth: end.toISOString().slice(0, 7)
  };
}

export function radiusToBbox(lat: number, lon: number, radiusKm: number): QuerySelection["bbox"] {
  const safeRadius = Math.max(1, Math.min(500, radiusKm));
  const latDelta = safeRadius / 111.32;
  const lonDelta = safeRadius / (111.32 * Math.max(0.01, Math.cos((lat * Math.PI) / 180)));
  return [Math.max(-180, lon - lonDelta), Math.max(-90, lat - latDelta), Math.min(180, lon + lonDelta), Math.min(90, lat + latDelta)];
}

function validBbox(value: string | null): QuerySelection["bbox"] | null {
  if (!value) return null;
  const values = value.split(",").map(Number);
  if (values.length !== 4 || values.some((item) => !Number.isFinite(item))) return null;
  const [west, south, east, north] = values;
  if (west < -180 || east > 180 || south < -90 || north > 90 || west > east || south > north) return null;
  return [west, south, east, north];
}

function validDateParam(value: string | null): string | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : null;
}

function readSelectionFromUrl(): QuerySelection {
  const params = new URLSearchParams(window.location.search);
  const defaults = defaultDates();
  const centerValue = params.get("center")?.split(",").map(Number);
  const center = centerValue?.length === 2 && centerValue.every(Number.isFinite) && Math.abs(centerValue[0]) <= 90 && Math.abs(centerValue[1]) <= 180
    ? { lat: centerValue[0], lon: centerValue[1] }
    : DEFAULT_CENTER;
  const radiusParam = Number(params.get("radiusKm"));
  const radiusKm = Number.isFinite(radiusParam) && radiusParam >= 1 && radiusParam <= 500 ? radiusParam : DEFAULT_RADIUS_KM;
  const bbox = validBbox(params.get("bbox")) ?? [...WORLD_BBOX];
  const productParams = (params.get("products") ?? "modis,viirs").split(",").filter((item): item is "modis" | "viirs" => item === "modis" || item === "viirs");
  const sensor = params.get("sensorScope");
  const sensorScope: SensorScope = sensor === "modis" || sensor === "viirs" ? sensor : "all";
  let start = validDateParam(params.get("start")) ?? defaults.start;
  let end = validDateParam(params.get("end")) ?? defaults.end;
  if (start > end) { start = defaults.start; end = defaults.end; }
  const monthParam = params.get("selectedMonth");
  const selectedMonth = monthParam && /^\d{4}-(0[1-9]|1[0-2])$/.test(monthParam) ? monthParam : end.slice(0, 7);
  return {
    bbox,
    areaLabel: (params.get("area") || "Global view").slice(0, 120),
    areaSource: params.has("area") ? "place" : "default",
    center,
    radiusKm,
    start,
    end,
    selectedMonth: /^\d{4}-\d{2}$/.test(selectedMonth) ? selectedMonth : end.slice(0, 7),
    products: productParams.length ? productParams : ["modis", "viirs"],
    sensorScope,
    liveMode: params.get("live") === "1"
  };
}

function writeSelectionToUrl(selection: QuerySelection): void {
  const params = new URLSearchParams(window.location.search);
  if (selection.areaSource === "location") {
    // A one-time location fix must not be persisted in a share URL or browser history.
    params.delete("bbox");
    params.delete("area");
    params.delete("center");
    params.delete("radiusKm");
  } else {
    params.set("bbox", selection.bbox.join(","));
    params.set("area", selection.areaLabel);
    params.set("center", `${selection.center.lat},${selection.center.lon}`);
    params.set("radiusKm", String(selection.radiusKm));
  }
  params.set("start", selection.start);
  params.set("end", selection.end);
  params.set("selectedMonth", selection.selectedMonth);
  params.set("products", selection.products.join(","));
  params.set("sensorScope", selection.sensorScope);
  if (selection.liveMode) params.set("live", "1");
  else params.delete("live");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}${window.location.hash}`);
}

export function toObservationQuery(selection: QuerySelection): ObservationQuery {
  const products = selection.sensorScope === "all" ? selection.products : [selection.sensorScope];
  return {
    start: selection.start,
    end: selection.end,
    bbox: selection.bbox,
    products,
    limit: 1000,
    ...(selection.liveMode ? { live: true } : {})
  };
}

function mapApiResult(result: ApiResult<ObservationPage>, selection: QuerySelection): SnapshotView {
  const data = result.data;
  return {
    state: result.state,
    query: selection,
    data,
    dataQuery: data ? selection : null,
    retrievedAt: data?.freshness.fetched_at ?? null,
    synthetic: result.synthetic,
    message: result.message,
    summary: null,
    dailySummary: null,
    yearSummary: null,
    comparison: null
  };
}

export function toGlobeObservations(observations: Observation[]): Array<{
  id: string;
  source: "modis" | "viirs";
  observedAt: string;
  ingestedAt: string;
  latitude: number;
  longitude: number;
  confidence: string | null;
  frp: number | null;
  frpUnit: string | null;
}> {
  return observations.map((observation) => ({
    id: observation.id,
    source: observation.source,
    observedAt: observation.observed_at,
    ingestedAt: observation.ingested_at,
    latitude: observation.latitude,
    longitude: observation.longitude,
    confidence: observation.confidence === null ? null : String(observation.confidence),
    frp: observation.frp,
    frpUnit: observation.frp_unit
  }));
}

export function useSnapshotQuery() {
  const [query, setQuery] = useState<QuerySelection>(readSelectionFromUrl);
  const [snapshot, setSnapshot] = useState<SnapshotView>(() => ({
    state: "idle", query: readSelectionFromUrl(), data: null, dataQuery: null, retrievedAt: null, synthetic: false,
    summary: null, dailySummary: null, yearSummary: null, comparison: null
  }));
  const requestIdRef = useRef(0);
  const dirtyRef = useRef(false);
  const lastGoodRef = useRef<SnapshotView | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const queryKey = useMemo(() => JSON.stringify(query), [query]);

  const retry = useCallback(() => setRetryCount((count) => count + 1), []);

  useEffect(() => {
    // Leave a fresh URL bare: only persist once the user acts or the URL
    // already carries a selection (share link, back/forward navigation).
    if (dirtyRef.current || window.location.search.length > 1) writeSelectionToUrl(query);
    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    const requestedQuery = toObservationQuery(query);
    setSnapshot({ state: "loading", query, data: null, dataQuery: null, retrievedAt: null, synthetic: false, summary: null, dailySummary: null, yearSummary: null, comparison: null });

    // Live mode is an observations-only pull: summary, comparison, and CSV keep
    // the stored archive for the same filters so the panels stay comparable.
    const storedQuery = { ...requestedQuery };
    delete storedQuery.live;
    // Year-wide monthly buckets feed the burning activity calendar so all
    // twelve months of the selected year render with figures and color.
    // Stored archive, like the chart: live mode never changes history.
    const year = query.selectedMonth.slice(0, 4);
    void Promise.all([
      apiClient.getObservations(requestedQuery, { signal: controller.signal }),
      apiClient.getSummary({ ...storedQuery, interval: "month" }, { signal: controller.signal }),
      apiClient.getSummary({ ...storedQuery, interval: "day" }, { signal: controller.signal }),
      apiClient.getSummary({
        ...storedQuery,
        interval: "month",
        start: `${year}-01-01T00:00:00.000Z`,
        end: `${year}-12-31T23:59:59.999Z`
      }, { signal: controller.signal }),
      apiClient.getComparison(storedQuery, { signal: controller.signal })
    ]).then(([result, summary, dailySummary, yearSummary, comparison]) => {
      if (controller.signal.aborted || requestId !== requestIdRef.current) return;
      const next = { ...mapApiResult(result, query), summary, dailySummary, yearSummary, comparison };
      if (result.state === "error" && lastGoodRef.current?.data) {
        const lastGood = lastGoodRef.current;
        setSnapshot({
          ...lastGood,
          state: "stale",
          query,
          message: `Showing the previous successful result from ${lastGood.retrievedAt ?? "an earlier query"}. The current query failed${result.message ? `: ${result.message}` : "."}`
        });
        return;
      }
      setSnapshot(next);
      if ((result.state === "success" || result.state === "empty") && result.data) lastGoodRef.current = next;
    });

    return () => controller.abort();
  // queryKey captures every shareable filter field and triggers exactly one request per selection.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, retryCount]);

  useEffect(() => {
    const handlePopState = () => {
      dirtyRef.current = window.location.search.length > 1;
      setQuery(readSelectionFromUrl());
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const updateQuery = useCallback((update: Partial<QuerySelection>) => {
    dirtyRef.current = true;
    setQuery((current) => ({ ...current, ...update }));
  }, []);

  return { query, snapshot, updateQuery, retry };
}
