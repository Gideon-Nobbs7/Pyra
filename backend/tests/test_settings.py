"""Settings: empty-string env must not mask dotenv values. No live provider, no real DB."""

from app.settings import get_settings


def _env_file(tmp_path, monkeypatch, body):
    env_file = tmp_path / ".env"
    env_file.write_text(body)
    monkeypatch.setenv("PYRA_ENV_FILE", str(env_file))


def test_empty_env_does_not_mask_dotenv(tmp_path, monkeypatch):
    _env_file(tmp_path, monkeypatch, "DATABASE_URL=postgresql://file/db\n")
    monkeypatch.setenv("DATABASE_URL", "")
    assert get_settings().database_url == "postgresql://file/db"


def test_nonempty_env_still_wins_over_dotenv(tmp_path, monkeypatch):
    _env_file(tmp_path, monkeypatch, "DATABASE_URL=postgresql://file/db\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://shell/db")
    assert get_settings().database_url == "postgresql://shell/db"


def test_empty_env_without_file_value_stays_empty(tmp_path, monkeypatch):
    _env_file(tmp_path, monkeypatch, "CACHE_BACKEND=lru\n")
    monkeypatch.setenv("FIRMS_MAP_KEY", "")
    assert get_settings().firms_map_key == ""


def test_hermetic_mode_ignores_dotenv(tmp_path, monkeypatch):
    _env_file(tmp_path, monkeypatch, "DATABASE_URL=postgresql://file/db\n")
    monkeypatch.setenv("PYRA_ENV_FILE", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_settings().database_url == ""
