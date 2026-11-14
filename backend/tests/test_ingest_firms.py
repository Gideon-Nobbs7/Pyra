"""Offline ingest tests: sample FIRMS CSVs, never the live provider."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ingest_firms import (  # noqa: E402
    detect_family,
    harmonize,
    parse_firms_csv,
    prepare_records,
    synth_source_record_id,
    upsert_records,
)

MODIS_HEADER = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,"
    "satellite,confidence,version,bright_t31,frp,daynight"
)
MODIS_CSV = (
    MODIS_HEADER
    + """
6.71,-1.62,320.5,1.0,1.0,2024-08-15,1330,T,n,6.1NRT,295.1,12.3,D
6.72,-1.60,300.1,1.2,1.0,2024-08-16,0140,A,h,6.1NRT,290.0,,N
95.0,-1.60,300.1,1.2,1.0,2024-08-16,0140,A,h,6.1NRT,290.0,,N
6.73,-1.61,310.0,1.0,1.0,not-a-date,0140,A,n,6.1NRT,290.0,5.0,D
"""
)

VIIRS_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    "satellite,confidence,version,bright_ti5,frp,daynight"
)
VIIRS_CSV = (
    VIIRS_HEADER
    + """
6.70,-1.63,340.0,0.375,0.375,2024-08-15,1245,N20,n,1.0NRT,290.5,8.1,D
6.69,-1.61,350.2,0.375,0.375,2024-08-17,1310,N21,l,1.0NRT,292.0,,D
"""
)

INGESTED_AT = datetime(2024, 9, 1, 12, 0, 0, tzinfo=UTC)
GHANA_BBOX = (-3.3, 4.5, 1.2, 11.2)


def test_detect_family():
    assert detect_family(["latitude", "bright_t31", "brightness"]) == "modis"
    assert detect_family(["latitude", "bright_ti4", "bright_ti5"]) == "viirs"
    with pytest.raises(ValueError):
        detect_family(["latitude", "foo"])


def test_parse_modis_skips_bad_rows():
    rows = parse_firms_csv(MODIS_CSV, family="modis")
    assert len(rows) == 2  # bad lat + bad date skipped
    assert rows[0]["observed_at"] == datetime(2024, 8, 15, 13, 30, tzinfo=UTC)


def test_harmonize_modis_mapping():
    rows = parse_firms_csv(MODIS_CSV, family="modis")
    rec = harmonize(rows[0], "modis", INGESTED_AT)
    assert rec["platform"] == "Terra"
    assert rec["instrument"] == "MODIS"
    assert rec["confidence"] == "n"  # verbatim, not invented
    assert rec["frp"] == 12.3 and rec["frp_unit"] == "MW"
    assert rec["product_version"] == "6.1NRT"
    assert rec["ingested_at"] == INGESTED_AT
    props = json.loads(rec["raw_properties"])
    assert props["bright_t31"] == "295.1"

    rec2 = harmonize(rows[1], "modis", INGESTED_AT)
    assert rec2["platform"] == "Aqua"
    assert rec2["frp"] is None and rec2["frp_unit"] is None  # null stays null


def test_harmonize_viirs_platforms():
    rows = parse_firms_csv(VIIRS_CSV)
    platforms = [harmonize(r, "viirs", INGESTED_AT)["platform"] for r in rows]
    assert platforms == ["NOAA-20", "NOAA-21"]


def test_synth_id_stable_and_distinct():
    obs = datetime(2024, 8, 15, 13, 30, tzinfo=UTC)
    a = synth_source_record_id("modis", "T", obs, 6.71, -1.62, "320.5")
    b = synth_source_record_id("modis", "T", obs, 6.71, -1.62, "320.5")
    c = synth_source_record_id("modis", "T", obs, 6.72, -1.62, "320.5")
    assert a == b and len(a) == 40
    assert a != c


def test_prepare_dedupe_and_bbox_filter():
    doubled = MODIS_CSV + MODIS_CSV.splitlines()[0] + "\n"  # header only, no dup rows
    recs = prepare_records(doubled, "modis", INGESTED_AT, GHANA_BBOX)
    assert len(recs) == 2
    ids = [r["id"] for r in recs]
    assert all(i.startswith("modis-") for i in ids)

    recs = prepare_records(MODIS_CSV, "modis", INGESTED_AT, (22.9, 37.7, 24.3, 38.5))
    assert recs == []  # Attica filter drops Ghana rows


def test_snpp_rejected():
    with pytest.raises(ValueError, match="Suomi NPP"):
        prepare_records(VIIRS_CSV, "viirs_snpp", INGESTED_AT, GHANA_BBOX)


LIVE_DB = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs PostGIS DATABASE_URL")


@LIVE_DB
def test_upsert_roundtrip_idempotent():
    import psycopg
    import psycopg.rows

    url = os.environ["DATABASE_URL"]
    schema = Path(__file__).resolve().parent.parent / "schema.sql"
    with psycopg.connect(url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(schema.read_text())
        conn.commit()

    recs = prepare_records(MODIS_CSV, "modis", INGESTED_AT, GHANA_BBOX)
    assert upsert_records(recs, url) == 2
    assert upsert_records(recs, url) == 2  # idempotent re-run

    with psycopg.connect(url, connect_timeout=10, row_factory=psycopg.rows.dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM observations WHERE source='modis'")
            assert cur.fetchone()["n"] >= 2

    # Cleanup only the rows this test inserted.
    with psycopg.connect(url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM observations WHERE source_record_id = ANY(%s)",
                ([r["source_record_id"] for r in recs],),
            )
        conn.commit()


def test_load_api_products_default_and_override(monkeypatch):
    from scripts import ingest_firms as ing

    monkeypatch.delenv("FIRMS_API_PRODUCTS", raising=False)
    assert ing.load_api_products() == ing.DEFAULT_API_PRODUCTS

    monkeypatch.setenv("FIRMS_API_PRODUCTS", '{"modis": "MODIS_NEXT_Global_24h"}')
    products = ing.load_api_products()
    assert products["modis"] == "MODIS_NEXT_Global_24h"
    assert products["viirs_n20"] == ing.DEFAULT_API_PRODUCTS["viirs_n20"]


def test_load_api_products_rejects_bad_config(monkeypatch):
    from scripts import ingest_firms as ing

    monkeypatch.setenv("FIRMS_API_PRODUCTS", "not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        ing.load_api_products()

    monkeypatch.setenv("FIRMS_API_PRODUCTS", '{"terra": "..."}')
    with pytest.raises(ValueError, match="unknown products"):
        ing.load_api_products()


def test_api_check_pass_and_fail(monkeypatch):
    from scripts import ingest_firms as ing

    monkeypatch.setenv("FIRMS_MAP_KEY", "DUMMY")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FIRMS_API_PRODUCTS", raising=False)
    monkeypatch.setattr(ing, "fetch_api_csv", lambda *a: VIIRS_CSV)
    assert ing.main(["api", "--bbox=-3.3,4.5,1.2,11.2", "--date", "2024-08-20", "--check"]) == 0

    monkeypatch.setattr(ing, "fetch_api_csv", lambda *a: "Invalid MAP_KEY\n")
    assert ing.main(["api", "--bbox=-3.3,4.5,1.2,11.2", "--date", "2024-08-20", "--check"]) == 1


def test_api_partial_failure_is_loud_but_commits_healthy(monkeypatch):
    from scripts import ingest_firms as ing

    monkeypatch.setenv("FIRMS_MAP_KEY", "DUMMY")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.delenv("FIRMS_API_PRODUCTS", raising=False)
    committed = []

    def fake_fetch(product, bbox, day_range, date, key):
        if product == ing.DEFAULT_API_PRODUCTS["viirs_n20"]:
            raise RuntimeError("HTTP 400: renamed product")
        return MODIS_CSV if "MODIS" in product else VIIRS_CSV

    monkeypatch.setattr(ing, "fetch_api_csv", fake_fetch)
    monkeypatch.setattr(
        ing, "upsert_records", lambda records, url: committed.extend(records) or len(records)
    )
    rc = ing.main(["api", "--bbox=-3.3,4.5,1.2,11.2", "--date", "2024-08-20", "--day-range", "5"])
    assert rc == 1
    sources = {r["source"] for r in committed}
    assert sources == {"modis", "viirs"}  # healthy products still committed


def test_api_rejects_day_range_over_firms_cap(monkeypatch):
    from scripts import ingest_firms as ing

    monkeypatch.setenv("FIRMS_MAP_KEY", "DUMMY")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    rc = ing.main(["api", "--bbox=-3.3,4.5,1.2,11.2", "--date", "2024-08-20", "--day-range", "7"])
    assert rc == 2


def test_stream_archive_reads_zip_without_extracting(tmp_path, monkeypatch):
    import zipfile

    import app.firms as firms_lib
    from scripts import ingest_firms as ing

    stored = []
    monkeypatch.setattr(
        firms_lib, "upsert_records", lambda recs, url: stored.extend(recs) or len(recs)
    )
    zp = tmp_path / "sample.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("fires.csv", MODIS_CSV)
    summary = ing.stream_archive(
        str(zp),
        "modis",
        INGESTED_AT,
        GHANA_BBOX,
        "postgresql://u:p@localhost:5432/db",
        batch_size=1,
    )
    assert summary["scanned"] == 2
    assert summary["kept"] == 2
    assert summary["stored"] == 2
    assert len(stored) == 2
