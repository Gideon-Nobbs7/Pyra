from tests.conftest import get_client


def test_health_ok_no_secrets():
    c = get_client()
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    text = r.text.lower()
    assert "password" not in text
    assert "pyra:pyra" not in text


def test_metadata_synthetic_flag_and_limitations():
    c = get_client()
    r = c.get("/api/v1/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["synthetic"] is True
    assert "observed_at" in body["fields"]
    assert any("not a confirmed wildfire" in s for s in body["limitations"])
