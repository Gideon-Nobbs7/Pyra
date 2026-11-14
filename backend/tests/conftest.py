import pytest
from fastapi.testclient import TestClient

from app.cache import cache_state
from app.main import app


@pytest.fixture(autouse=True)
def _fixture_mode(monkeypatch):
    """Hermetic default: fixture-backed API unless a test opts into DB mode."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_FALLBACK", raising=False)
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)


def get_client() -> TestClient:
    cache_state.cache.invalidate()
    return TestClient(app)
