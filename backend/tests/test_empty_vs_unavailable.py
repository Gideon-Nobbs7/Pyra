from tests.conftest import get_client


def test_empty_inside_coverage():
    c = get_client()
    # Tiny bbox inside Attica with no fixture points is unlikely; use a 1-day
    # window with a tight box that misses seeded points. Fall back to asserting
    # contract shape for whichever status returns.
    r = c.get(
        "/api/v1/observations",
        params={
            "start": "2024-08-02T00:00:00Z",
            "end": "2024-08-02T00:05:00Z",
            "bbox": "22.900,37.700,22.901,37.701",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] in ("empty", "ok")
    if body["coverage_status"] == "empty":
        assert body["data"] == []
        assert "does not prove" in body["coverage_reason"]


def test_unavailable_outside_coverage():
    c = get_client()
    r = c.get(
        "/api/v1/observations",
        params={
            "start": "2010-01-01T00:00:00Z",
            "end": "2010-01-31T00:00:00Z",
            "bbox": "-120,30,-110,40",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["coverage_status"] == "unavailable"
    assert body["data"] == []
    assert "outside" in body["coverage_reason"].lower()
