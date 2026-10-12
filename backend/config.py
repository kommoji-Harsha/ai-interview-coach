from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "AI Interview Coach"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://coach:coach@localhost:5432/coach"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # LLM Gateway
    primary_provider: str = "google"
    primary_model: str = "gemini-2.0-flash"
    google_api_key: str = ""

    secondary_provider: str = "openai_compat"
    secondary_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_compat_base_url: str = "https://api.openai.com/v1"

    local_provider: str = "openai_compat"
    local_base_url: str = "http://localhost:11434/v1"
    local_model: str = "llama3.2"

    # Gateway behavior
    llm_cache_enabled: bool = True
    llm_cache_ttl_seconds: int = 3600
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def get_settings() -> Settings:
    return Settings()
