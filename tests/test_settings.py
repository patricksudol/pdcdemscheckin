import pytest
from pydantic import ValidationError

from pdcdemscheckin.settings import Settings


def production_settings(**overrides):
    values = {
        "environment": "production",
        "database_url": "postgresql://pdc:secret@db.example/pdc",
        "public_base_url": "https://checkins.phoenixvilledems.org",
        "session_secret": "a-unique-production-secret-that-is-long-enough",
        "secure_cookies": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_render_database_url_uses_psycopg_driver():
    settings = production_settings()
    assert settings.database_url == "postgresql+psycopg://pdc:secret@db.example/pdc"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "sqlite+aiosqlite:///production.db"),
        ("public_base_url", "http://checkins.phoenixvilledems.org"),
        ("session_secret", "too-short"),
        ("secure_cookies", False),
    ],
)
def test_production_rejects_insecure_configuration(field, value):
    with pytest.raises(ValidationError):
        production_settings(**{field: value})


def test_production_seed_credentials_must_be_complete_and_strong():
    with pytest.raises(ValidationError):
        production_settings(seed_admin_email="owner@example.com")
    with pytest.raises(ValidationError):
        production_settings(
            seed_admin_email="owner@example.com",
            seed_admin_password="short",
        )
