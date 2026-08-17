from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_name: str = "SetuHaul"
    environment: str = "local"
    api_prefix: str = "/api"
    jwt_secret: str = "setuhaul-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 12
    database_path: str = str(ROOT / "data" / "setuhaul_freight_operations.db")
    seed_sql_path: str = str(ROOT / "database" / "instructions" / "setuhaul_schema_and_seed.sql")
    migrations_dir: str = str(ROOT / "database" / "migrations")
    classroom_now: str = "2026-08-04T09:40:00+05:30"
    soft_hold_ttl_seconds: int = 120
    pending_warehouse_ttl_minutes: int = 15
    max_clarification_turns: int = 4
    expand_seed: str = "full"  # full | crunch | off
    location_stale_seconds: int = 120
    geoapify_hard_fail: bool = False
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    geoapify_api_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "setuhaul-fde"
    langchain_tracing_v2: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"


@lru_cache
def _cached_settings(env_mtime: float | None) -> Settings:
    return Settings()


def get_settings() -> Settings:
    """Reload settings when .env changes (mtime), so key/model updates apply without a hard restart."""
    env_path = ROOT / ".env"
    mtime = env_path.stat().st_mtime if env_path.exists() else None
    return _cached_settings(mtime)
