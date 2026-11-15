from app.main import cors_allowed_origins
from tests.conftest import get_client


def test_parse_comma_separated_origins():
    assert cors_allowed_origins("https://a.example, http://localhost:5173 ") == [
        "https://a.example",
        "http://localhost:5173",
    ]


def test_parse_empty_means_same_origin_only():
    assert cors_allowed_origins("") == []
    assert cors_allowed_origins("  , ") == []


def test_no_cors_headers_for_unlisted_origin():
    c = get_client()
    r = c.get("/api/v1/health", headers={"Origin": "https://not-listed.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers
