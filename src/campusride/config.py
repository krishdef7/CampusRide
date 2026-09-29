"""Runtime configuration, read from environment variables (or a .env file)."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# India has no DST, so a fixed offset is exact and avoids needing tzdata on Windows.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_ist() -> datetime:
    return datetime.now(IST)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://campusride:campusride@localhost:5433/campusride"
    db_pool_min: int = 5
    db_pool_max: int = 20

    # Matching
    match_radius_tiers_m: list[int] = [1500, 4000]
    match_capacity_waste_penalty_m: float = 150.0  # metres of extra distance we'd accept to avoid wasting a seat
    driver_stale_after_s: int = 60
    dispatch_interval_s: float = 1.0
    schedule_lookahead_min: int = 5  # scheduled rides get matched this many minutes before pickup

    # LLM
    llm_provider: str = "openai"  # openai (any OpenAI-compatible endpoint) | anthropic | fake
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_timeout_s: float = 30.0
    llm_rpm: float = 0.0  # client-side rate limit (requests/minute) for free tiers; 0 = unlimited
    llm_max_attempts: int = 6  # attempts on rate-limit / overload errors (exponential backoff)
    llm_max_repairs: int = 2
    llm_cache_path: str | None = None  # set for evals: deterministic, free re-runs

    # Observability
    log_level: str = "INFO"
    log_json: bool = True
    otel_exporter_otlp_endpoint: str | None = None  # e.g. http://localhost:4318
    service_name: str = "campusride-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
