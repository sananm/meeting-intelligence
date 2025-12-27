from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Meeting Intelligence"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/meeting_intelligence"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 500  # Max audio file size

    # ML Models
    whisper_model: str = "base"  # tiny, base, small, medium, large
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Auth
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Google Gemini API (for summarization)
    gemini_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
