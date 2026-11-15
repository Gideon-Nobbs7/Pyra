-- Pyra M1 schema (PostGIS). Reversible: drop table to roll back.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('modis', 'viirs')),
  source_record_id TEXT,
  observed_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL,
  latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  geom GEOGRAPHY(Point, 4326),
  instrument TEXT,
  platform TEXT,
  confidence TEXT,
  frp DOUBLE PRECISION,
  frp_unit TEXT,
  quality_flags TEXT,
  product_version TEXT,
  raw_properties JSONB,
  CONSTRAINT uq_source_record UNIQUE (source, source_record_id)
);

CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations (observed_at);
CREATE INDEX IF NOT EXISTS idx_observations_geom ON observations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_observations_source ON observations (source);

-- Gap-fill job queue: user query bboxes the store cannot serve yet.
-- The API enqueues on a stored-data miss; the worker claims oldest-first.
-- Rerunnable: IF NOT EXISTS throughout.
CREATE TABLE IF NOT EXISTS ingest_jobs (
  id BIGSERIAL PRIMARY KEY,
  min_lon DOUBLE PRECISION NOT NULL,
  min_lat DOUBLE PRECISION NOT NULL,
  max_lon DOUBLE PRECISION NOT NULL,
  max_lat DOUBLE PRECISION NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'claimed', 'done', 'failed')),
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_ingest_job UNIQUE (min_lon, min_lat, max_lon, max_lat, start_date, end_date)
);

CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs (status, created_at);
