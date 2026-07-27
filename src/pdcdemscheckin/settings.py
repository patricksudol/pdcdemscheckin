from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PDC_", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./pdcdemscheckin.db"
    public_base_url: str = "http://localhost:8000"
    session_secret: str = "development-only-change-me"
    seed_admin_email: str = ""
    seed_admin_password: str = ""
    seed_admin_name: str = "Test Organizer"
    frontend_dist: str = "frontend/dist"
    secure_cookies: bool = False
    session_max_age_seconds: int = 8 * 60 * 60
    checkin_rate_limit: int = 30

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+aiosqlite", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
