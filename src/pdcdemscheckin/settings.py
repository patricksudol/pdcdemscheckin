from functools import lru_cache

from pydantic import field_validator, model_validator
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
    login_rate_limit: int = 5
    login_rate_window_seconds: int = 15 * 60
    onetap_api_key: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        if self.environment != "production":
            return self

        errors: list[str] = []
        if not self.database_url.startswith("postgresql+psycopg://"):
            errors.append("PDC_DATABASE_URL must use PostgreSQL in production")
        if not self.public_base_url.startswith("https://"):
            errors.append("PDC_PUBLIC_BASE_URL must use HTTPS in production")
        if not self.secure_cookies:
            errors.append("PDC_SECURE_COOKIES must be true in production")
        if (
            len(self.session_secret) < 32
            or self.session_secret == "development-only-change-me"
        ):
            errors.append("PDC_SESSION_SECRET must be a unique value of at least 32 characters")
        if bool(self.seed_admin_email) != bool(self.seed_admin_password):
            errors.append(
                "PDC_SEED_ADMIN_EMAIL and PDC_SEED_ADMIN_PASSWORD must be set together"
            )
        if self.seed_admin_password and len(self.seed_admin_password) < 12:
            errors.append("PDC_SEED_ADMIN_PASSWORD must be at least 12 characters")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+aiosqlite", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
