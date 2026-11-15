from tests.conftest import get_client


def test_health_ok_no_secrets():
    c = get_client()
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["checked_at"]
    assert body["database"] in ("available", "unavailable")
    text = r.text.lower()
    assert "password" not in text
    assert "pyra:pyra" not in text


def test_metadata_matches_frontend_contract():
    c = get_client()
    r = c.get("/api/v1/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["synthetic"] is True
    assert {p["source"] for p in body["products"]} == {"modis", "viirs"}
    for product in body["products"]:
        for key in ("product", "version", "coverage_start", "coverage_end", "limitations"):
            assert key in product, key
        assert isinstance(product["limitations"], list)
    assert body["harmonization"]["method"]
    assert "latest_ingested_at" in body["freshness"]
    assert any("not a confirmed wildfire" in s for s in body["limitations"])
