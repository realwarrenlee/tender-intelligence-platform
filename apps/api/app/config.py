from functools import lru_cache

from app.tenders.usage_budget import ModelPrice
from app.tenders.notice_sources import NoticeJob
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)

    database_url: SecretStr
    supabase_url: str
    supabase_secret_key: SecretStr
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_prices: dict[str, ModelPrice] = {}
    openai_decisions_model: str | None = None
    notice_source_jobs: list[NoticeJob] = []


@lru_cache
def get_settings():
    return Settings()
