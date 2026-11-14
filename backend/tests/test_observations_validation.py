from tests.conftest import get_client

BBOX = "22.9,37.7,24.3,38.5"
START = "2024-08-01T00:00:00Z"
END = "2024-08-31T23:59:59Z"


def test_observations_ok_time_area_together():
    c = get_client()
    r = c.get(
        "/api/v1/observations",
        params={"start": START, "end": END, "bbox": BBOX, "limit": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["synthetic"] is True
    assert body["coverage_status"] == "ok"
    assert len(body["data"]) == 10
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["cursor_next"]
    f = body["filters_applied"]
    assert f["bbox"] == [22.9, 37.7, 24.3, 38.5]
    assert body["freshness"]["synthetic"] is True


def test_pagination_cursor_stable():
    c = get_client()
    r1 = c.get(
        "/api/v1/observations",
        params={"start": START, "end": END, "bbox": BBOX, "limit": 5},
    )
    cur = r1.json()["pagination"]["cursor_next"]
    assert cur
    r2 = c.get(
        "/api/v1/observations",
        params={"start": START, "end": END, "bbox": BBOX, "limit": 5, "cursor": cur},
    )
    ids1 = [o["id"] for o in r1.json()["data"]]
    ids2 = [o["id"] for o in r2.json()["data"]]
    assert not set(ids1) & set(ids2)


def test_reject_end_before_start():
    c = get_client()
    r = c.get(
        "/api/v1/observations",
        params={"start": END, "end": START, "bbox": BBOX},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_params"


def test_reject_bad_bbox_and_limit_and_unknown():
    c = get_client()
    assert (
        c.get(
            "/api/v1/observations", params={"start": START, "end": END, "bbox": "1,2,3"}
        ).status_code
        == 422
    )
    assert (
        c.get(
            "/api/v1/observations",
            params={"start": START, "end": END, "bbox": "24.3,38.5,22.9,37.7"},
        ).status_code
        == 422
    )
    assert (
        c.get(
            "/api/v1/observations",
            params={"start": START, "end": END, "bbox": BBOX, "limit": 5000},
        ).status_code
        == 422
    )
    assert (
        c.get(
            "/api/v1/observations",
            params={"start": START, "end": END, "bbox": BBOX, "cursor": "!!!"},
        ).status_code
        == 422
    )
    r = c.get(
        "/api/v1/observations",
        params={"start": START, "end": END, "bbox": BBOX, "foo": "bar"},
    )
    assert r.status_code == 422
    assert "unknown parameters" in r.json()["error"]["message"]


def test_products_filter():
    c = get_client()
    r = c.get(
        "/api/v1/observations",
        params={"start": START, "end": END, "bbox": BBOX, "limit": 100, "products": "modis"},
    )
    assert r.status_code == 200
    assert all(o["source"] == "modis" for o in r.json()["data"])
