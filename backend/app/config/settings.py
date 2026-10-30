from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]   # <root>/backend
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # repository root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[PROJECT_ROOT / ".env", BACKEND_DIR / ".env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_name: str = "AgenticWhats"
    api_v1_prefix: str = "/api"

    # Database / cache
    database_url: str = "sqlite:///./agenticwhats.db"
    redis_url: str = "redis://localhost:6379/0"

    # LLM (provider abstraction; "mock" runs a deterministic rule-based agent offline)
    llm_provider: str = "mock"  # mock | openai (any OpenAI-compatible endpoint)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Embeddings (mock = local deterministic hashing embeddings)
    embedding_provider: str = "mock"  # mock | openai
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 384

    # WhatsApp Cloud API
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: str = "agenticwhats-verify"
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"

    # Auth
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:3000"

    # Seed demo data
    demo_owner_email: str = "owner@demo.com"
    demo_owner_password: str = "demo1234"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_database_url(self) -> str:
        """Resolve relative SQLite paths against the backend dir so the app
        works regardless of the current working directory."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix) and not self.database_url.startswith("sqlite:////"):
            path = self.database_url[len(prefix):]
            if path != ":memory:" and not Path(path).is_absolute():
                return prefix + (BACKEND_DIR / path).as_posix()
        return self.database_url

    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url().startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
