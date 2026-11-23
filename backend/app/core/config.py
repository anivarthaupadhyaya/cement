from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://cement:cement@localhost:5433/cement"
    secret_key: str = "dev-only-secret"
    session_hours: int = 12
    cookie_secure: bool = False
    cookie_name: str = "cement_session"


@lru_cache
def get_settings() -> Settings:
    return Settings()
