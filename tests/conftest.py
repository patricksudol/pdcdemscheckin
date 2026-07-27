from datetime import UTC, datetime

import pytest
import pytest_asyncio

from pdcdemscheckin.app import create_app
from pdcdemscheckin.auth import hash_password
from pdcdemscheckin.models import Base, Meeting, MeetingStatus, Organizer, OrganizerRole
from pdcdemscheckin.settings import Settings


@pytest.fixture(scope="session")
def app(tmp_path_factory: pytest.TempPathFactory):
    database_path = tmp_path_factory.mktemp("db") / "test.sqlite3"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database_path}",
        session_secret="test-secret",
        public_base_url="http://localhost:8000",
    )
    return create_app(settings, name="PhoenixvilleDemocratsCheckinTests")


@pytest_asyncio.fixture(autouse=True)
async def clean_database(app):
    app.ctx.login_attempts.clear()
    app.asgi_client.cookies.clear()
    async with app.ctx.db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def open_meeting(app):
    meeting = Meeting(
        title="July Monthly Meeting",
        starts_at=datetime(2026, 7, 27, 23, 0, tzinfo=UTC),
        location="Phoenixville Recreation Center",
        status=MeetingStatus.open,
        public_token="july-meeting-token",
    )
    async with app.ctx.db.session() as db:
        db.add(meeting)
        await db.flush()
    return meeting


@pytest_asyncio.fixture
async def organizer(app):
    item = Organizer(
        email="owner@example.com",
        display_name="PDC Owner",
        password_hash=hash_password("test-password"),
        role=OrganizerRole.owner,
    )
    async with app.ctx.db.session() as db:
        db.add(item)
        await db.flush()
    return item
