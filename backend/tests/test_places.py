"""GET /api/v1/places: validation, slimming, honest provider failures. No live provider."""

import httpx

import app.api.v1.places as places_lib
from tests.conftest import get_client


class FakeResponse:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


PHOTON_OK = {
    "features": [
        {
            "geometry": {"coordinates": [-0.84, 9.4]},
            "properties": {"name": "Tamale", "city": "Tamale", "country": "Ghana"},
        },
        {
            "geometry": {"coordinates": [0.0, 5.0]},
            "properties": {"name": "X", "extra": 1},
        },
    ]
}


def _mock_get(monkeypatch, response=None, error=None):
    calls = []

    async def fake_fetch(params):
        calls.append({"url": places_lib.PHOTON_URL, "params": params})
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(places_lib, "_fetch", fake_fetch)
    return calls


def test_places_ok_slimmed(monkeypatch):
    calls = _mock_get(monkeypatch, FakeResponse(200, PHOTON_OK))
    r = get_client().get("/api/v1/places", params={"q": "Tamale"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == [
        {
            "name": "Tamale",
            "city": "Tamale",
            "state": None,
            "country": "Ghana",
            "latitude": 9.4,
            "longitude": -0.84,
        },
        {
            "name": "X",
            "city": None,
            "state": None,
            "country": None,
            "latitude": 5.0,
            "longitude": 0.0,
        },
    ]
    assert calls[0]["url"] == "https://photon.komoot.io/api/"
    assert calls[0]["params"]["q"] == "Tamale"


def test_places_rejects_bad_params():
    c = get_client()
    assert c.get("/api/v1/places").status_code == 422
    assert c.get("/api/v1/places", params={"q": "x"}).status_code == 422
    assert c.get("/api/v1/places", params={"q": "Tamale", "limit": "99"}).status_code == 422
    assert c.get("/api/v1/places", params={"q": "Tamale", "zzz": "1"}).status_code == 422
    assert c.get("/api/v1/places", params={"q": "Tamale", "lang": "english"}).status_code == 422


def test_places_provider_failure_is_503_not_empty(monkeypatch):
    _mock_get(monkeypatch, error=httpx.ConnectError("down"))
    r = get_client().get("/api/v1/places", params={"q": "Tamale"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"


def test_places_provider_http_error_is_503(monkeypatch):
    _mock_get(monkeypatch, FakeResponse(500, {}))
    r = get_client().get("/api/v1/places", params={"q": "Tamale"})
    assert r.status_code == 503


def test_shared_client_is_reused():
    first = places_lib._shared_client()
    try:
        assert places_lib._shared_client() is first
    finally:
        import asyncio

        asyncio.run(places_lib.close_client())


def test_places_bad_shape_is_503(monkeypatch):
    _mock_get(monkeypatch, FakeResponse(200, {"features": "nope"}))
    r = get_client().get("/api/v1/places", params={"q": "Tamale"})
    assert r.status_code == 503
    _mock_get(monkeypatch, FakeResponse(200, None, bad_json=True))
    r = get_client().get("/api/v1/places", params={"q": "Tamale"})
    assert r.status_code == 503
