# Harmonization method (M1): MODIS + VIIRS active-fire hotspots

Source of truth for how Pyra turns two sensor products into one hotspot
time series. Verified against NASA FIRMS docs (Earthdata FIRMS page,
active-fire attribute tables, Archive Download page), November 2026.
Re-verify product strings and coverage before each ingest.

## Products (verified)

| Pyra `source` | FIRMS product | Coverage (per FIRMS Archive Download) | Pixel | Instrument / platform |
|---|---|---|---|---|
| `modis` | MODIS Collection 6.1 NRT (`MCD14DL`) | 1 Nov 2000 – present | 1 km at nadir (grows toward scan edge; see `scan`/`track`) | MODIS on Terra (`T`) and Aqua (`A`) |
| `viirs` | VIIRS 375 m NRT, NOAA-20 (`VJ114IMGTDL_NRT`) | 1 Apr 2018 – present | ~375 m at nadir | VIIRS on NOAA-20 (`N20`) |
| `viirs` | VIIRS 375 m NRT, NOAA-21 (`VJ214IMGTDL_NRT`) | 1 Mar 2023 – present | ~375 m at nadir | VIIRS on NOAA-21 (`N21`) |

Excluded: VIIRS Suomi NPP (`VNP14IMGTDL_NRT`) — spacecraft stopped
delivering data 2 Nov 2026. Pre-cutoff SNPP rows already stored stay
queryable with their true `observed_at`; no new SNPP ingests.

Burned-area products are out of scope (separate UMD download, not FIRMS).

## NRT vs standard processing

Archive files older than ~7 days are eventually replaced by standard
science-quality data (~5 month lag). NRT and standard rows for the same
fire may differ. Pyra keeps both distinguished:

- `observed_at` = satellite overpass time (`acq_date` + `acq_time`, UTC).
- `ingested_at` = time the row was loaded into Postgres. Never derived
  from the observation.
- `product_version` = FIRMS `version` verbatim (e.g. `6.1NRT`, `1.0NRT`,
  `6.1`, `1.0`), so NRT vs standard is visible per record.
- Re-ingesting an area may update rows; `freshness.latest_ingested_at`
  always reflects the latest successful load.

## Field mapping (verbatim unless stated)

No invented values. Unmapped or missing fields stay null; null never
means zero.

### MODIS C6.1 NRT

| FIRMS column | Pyra field | Notes |
|---|---|---|
| `latitude`, `longitude` | `latitude`, `longitude` | Center of 1 km pixel, not the fire's exact location |
| `acq_date` + `acq_time` | `observed_at` | UTC, normalized to RFC 3339 |
| — (load time) | `ingested_at` | Distinct from `observed_at` |
| `satellite` (`T`/`A`) | `platform` | `T`→`Terra`, `A`→`Aqua` |
| — | `instrument` | Constant `MODIS` |
| `confidence` (`l`/`n`/`h`) | `confidence` | Verbatim; source-defined low/nominal/high |
| `version` | `product_version` | Verbatim, e.g. `6.1NRT` |
| `frp` | `frp`, `frp_unit='MW'` | Null stays null; unit only when value present |
| `bright_t31` (K) | `raw_properties.bright_t31` | Preserved, not interpreted |
| `brightness` (ch 21/22, K) | `raw_properties.brightness` | Preserved, not interpreted |
| `scan`, `track` | `raw_properties.scan/track` | Actual pixel size (km) |
| `daynight` (`D`/`N`) | `raw_properties.daynight` | Preserved |
| `type` (0–3) | `raw_properties.type` | Standard-quality files only |

### VIIRS 375 m NRT (NOAA-20 / NOAA-21)

| FIRMS column | Pyra field | Notes |
|---|---|---|
| `latitude`, `longitude` | `latitude`, `longitude` | Center of nominal 375 m pixel |
| `acq_date` + `acq_time` | `observed_at` | UTC |
| — (load time) | `ingested_at` | Distinct from `observed_at` |
| `satellite` (`N20`/`N21`) | `platform` | `N20`→`NOAA-20`, `N21`→`NOAA-21` (`N`→`Suomi NPP`, legacy rows only) |
| — | `instrument` | Constant `VIIRS` |
| `confidence` (`l`/`n`/`h`) | `confidence` | Verbatim; see note below |
| `version` | `product_version` | Verbatim, e.g. `1.0NRT` |
| `frp` | `frp`, `frp_unit='MW'` | Hybrid 375/750 m retrieval; viable only for small/low-intensity fires |
| `bright_ti5` (K) | `raw_properties.bright_ti5` | I-5 channel |
| `bright_ti4` (K) | `raw_properties.brightness` | I-4 channel driving detection |
| `scan`, `track` | `raw_properties.scan/track` | Actual pixel size (km) |
| `daynight` (`D`/`N`) | `raw_properties.daynight` | Preserved |

VIIRS confidence note: low-confidence daytime pixels cluster around sun
glint and weak (<15 K) mid-IR anomalies; low-confidence nighttime pixels
occur only in the South Atlantic Magnetic Anomaly belt. FIRMS removes the
worst SAMA false alarms before distribution. Treat `l` as "possible
detection", never as confirmed fire.

## Record identity (FIRMS ships no stable ID)

FIRMS rows carry no detection ID, so Pyra synthesizes one deterministically:

```
source_record_id = sha1("{source}|{satellite}|{observed_at_utc}|{lat:.5f}|{lon:.5f}|{brightness}")
id = "{source}-{digest[:16]}"
```

Same input bytes → same ID across re-runs, so re-ingest is idempotent via
`ON CONFLICT (source, source_record_id) DO UPDATE`. Rounding to 5 decimals
(~1 m) absorbs float-format jitter without merging distinct pixels.

## What a harmonized count means

One harmonized count = one harmonized record matching the query filters.
It is a detection count, not a fire count, burned area, or perimeter.
MODIS 1 km and VIIRS 375 m pixels differ in size, sensitivity, overpass
time, and false-alarm behavior, so raw counts are not directly comparable
across sensors. Comparability rules:

- Within one sensor family over time: comparable for the same bbox and
  processing tier (mind NRT→standard replacement).
- MODIS vs VIIRS in one window: show side by side with this warning, never
  as a single blended "fire" number and never as a ratio.
- Never divide by a zero baseline; missing coverage is `unavailable`,
  never zero.

## Provenance (required by FIRMS terms)

Every response carrying FIRMS-backed rows must keep per-record `source`,
`platform`, `product_version`, both timestamps, and surface this text in
metadata/UI: data from NASA FIRMS (LANCE/ESDIS), provided "as is".

## On-demand live fetch (bounded)

When Postgres holds zero rows for a query, the request path may pull the
missing slice live instead of answering empty — only if every bound holds:

- `FIRMS_MAP_KEY` configured (server-side; never in the frontend);
- zero DB rows (never mixed with or replacing stored data);
- recent window (request end within 10 days of now);
- small area (bbox ≤ 50 deg², e.g. Ghana ≈ 30);
- global rate limit (one provider call per 60 s per process);
- fetch window clamped to the last 5 days (FIRMS API day-range cap [1..5]).

The pull upserts into Postgres, the response is re-read from the database,
and the result warms the in-process cache — so the next identical visit is
served from cache/DB with no provider call. Per-key single-flight prevents
concurrent duplicates. History (older than 10 days) is never fetched live;
it comes from archive ingest. A failed live pull degrades to the stored
result (empty with the honest copy, or 503 if the store itself is down).
