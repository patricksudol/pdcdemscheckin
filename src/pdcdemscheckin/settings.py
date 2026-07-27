from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PDC_", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./pdcdemscheckin.db"
    public_base_url: str = "http://localhost:8000"
    session_secret: str = "development-only-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    admin_allowlist: Annotated[tuple[str, ...], NoDecode] = Field(default_factory=tuple)
    frontend_dist: str = "frontend/dist"
    secure_cookies: bool = False
    session_max_age_seconds: int = 8 * 60 * 60
    checkin_rate_limit: int = 30

    @field_validator("admin_allowlist", mode="before")
    @classmethod
    def split_allowlist(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip().lower() for part in value.split(",") if part.strip())
        return value

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+aiosqlite", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
