"""Summary + comparison endpoints and the converged frontend contract."""

from tests.conftest import get_client

BBOX = "22.9,37.7,24.3,38.5"
START = "2024-08-01T00:00:00Z"
END = "2024-08-31T23:59:59Z"
START_ISO = START.replace("Z", "+00:00")
END_ISO = END.replace("Z", "+00:00")


def test_summary_monthly_matches_frontend_contract():
    c = get_client()
    r = c.get(
        "/api/v1/summary",
        params={"start": START, "end": END, "bbox": BBOX, "interval": "month"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "ok"
    assert body["synthetic"] is True
    assert body["count"] == sum(b["count"] for b in body["data"]) > 0
    assert body["filters"]["interval"] == "month"
    assert body["filters"]["bbox"] == [22.9, 37.7, 24.3, 38.5]
    assert body["coverage"] == {"start": START_ISO, "end": END_ISO, "available": True}
    assert "fetched_at" in body["freshness"]
    for bucket in body["data"]:
        assert set(bucket) >= {"start", "end", "count"}
    assert body["data"][0]["start"].startswith("2024-08-01")


def test_summary_rejects_bad_interval_and_params():
    c = get_client()
    r = c.get("/api/v1/summary", params={"interval": "fortnight"})
    assert r.status_code == 422
    r = c.get(
        "/api/v1/summary",
        params={"start": START, "end": END, "bbox": BBOX, "interval": "month", "bogus": "1"},
    )
    assert r.status_code == 422
    r = c.get(
        "/api/v1/summary", params={"start": END, "end": START, "bbox": BBOX, "interval": "month"}
    )
    assert r.status_code == 422


def test_summary_unavailable_outside_fixture_coverage():
    c = get_client()
    r = c.get(
        "/api/v1/summary",
        params={
            "start": "2010-01-01T00:00:00Z",
            "end": "2010-01-31T00:00:00Z",
            "bbox": "-120,30,-110,40",
            "interval": "month",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "unavailable"
    assert body["data"] == []
    assert body["coverage"]["available"] is False


def test_observations_carries_count_and_compat_fields():
    c = get_client()
    r = c.get(
        "/api/v1/observations", params={"start": START, "end": END, "bbox": BBOX, "limit": 10}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= len(body["data"]) > 0
    assert body["filters"]["bbox"] == [22.9, 37.7, 24.3, 38.5]
    assert body["coverage"] == {"start": START_ISO, "end": END_ISO, "available": True}
    assert body["pagination"]["next_cursor"] == body["pagination"]["cursor_next"]
    assert "fetched_at" in body["freshness"]


def test_comparison_fixture_has_no_baseline_but_honest_math():
    c = get_client()
    r = c.get(
        "/api/v1/observations", params={"start": START, "end": END, "bbox": BBOX, "limit": 1000}
    )
    selected = r.json()["count"]
    r = c.get("/api/v1/comparison", params={"start": START, "end": END, "bbox": BBOX})
    assert r.status_code == 200
    body = r.json()
    assert body["selected"]["count"] == selected
    assert body["baseline"]["years"] == 0
    assert body["baseline"]["median_count"] == 0
    assert body["baseline"]["sample_years"] == []
    assert body["anomaly"]["count_delta"] == selected
    assert body["anomaly"]["direction"] == ("above" if selected else "at_baseline")
    assert "comparability_warning" in body
    assert "%" not in body["comparability_warning"]
    assert "percent_change" not in body
    assert body["filters"]["bbox"] == [22.9, 37.7, 24.3, 38.5]
    assert body["coverage"]["available"] is True
    assert "fetched_at" in body["freshness"]
    assert body["synthetic"] is True


def test_comparison_rejects_bad_params():
    c = get_client()
    r = c.get("/api/v1/comparison", params={"start": END, "end": START, "bbox": BBOX})
    assert r.status_code == 422
    r = c.get("/api/v1/comparison", params={"start": START, "end": END, "bbox": BBOX, "wat": "1"})
    assert r.status_code == 422


def test_baseline_warning_names_missing_baseline():
    from app.api.v1.comparison import _baseline_warning

    base = "Baseline context."
    assert _baseline_warning(base, [3, 5]) == base
    missing = _baseline_warning(base, [])
    assert missing.startswith(base)
    assert "no historical baseline could be computed" in missing
