import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, env_file_encoding="utf-8", extra="ignore")

    database_url: str = ""
    database_url_fallback: str = ""
    database_url_local: str = ""
    firms_map_key: str = ""
    firms_api_products: str = ""
    ee_project: str = ""
    ee_credentials_path: str = ""
    cache_backend: str = "lru"
    watch_bboxes: str = ""
    worker_enabled: bool = False
    worker_interval_s: int = 10
    worker_recent_days: int = 7
    worker_max_jobs: int = 3
    cors_origins: str = ""
    database_connect_timeout: int = 12
    database_pool_min_size: int = 1
    database_pool_max_size: int = 10
    database_pool_timeout: float = 20.0


class _PlainSettings(Settings):

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def _drop_empty_env_masked_by(dotenv_file) -> None:
    try:
        from dotenv import dotenv_values

        file_values = dotenv_values(dotenv_file)
    except Exception:
        return
    for field in Settings.model_fields:
        env_name = field.upper()
        if os.environ.get(env_name) == "" and file_values.get(env_name):
            del os.environ[env_name]


def get_settings() -> Settings:
    """Fresh settings from process env + dotenv."""
    override = os.environ.get("PYRA_ENV_FILE")
    if override:

        class _FileSettings(Settings):
            model_config = SettingsConfigDict(
                env_file=override, env_file_encoding="utf-8", extra="ignore"
            )

        _drop_empty_env_masked_by(override)
        return _FileSettings()
    if override is not None:
        return _PlainSettings()
    _drop_empty_env_masked_by(_ROOT_ENV)
    return Settings()
