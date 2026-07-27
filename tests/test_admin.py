from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from pdcdemscheckin.auth import issue_session, verify_password
from pdcdemscheckin.models import (
    AuditEvent,
    Meeting,
    MeetingStatus,
    Organizer,
    OrganizerRole,
)

CSRF_TOKEN = "test-csrf-token"


def session_cookie(app, organizer):
    return {
        "pdc_session": issue_session(
            organizer,
            app.ctx.settings,
            csrf_token=CSRF_TOKEN,
        )
    }


def csrf_headers():
    return {"X-CSRF-Token": CSRF_TOKEN}


@pytest.mark.asyncio
async def test_opening_meeting_closes_previous_active(app, open_meeting, organizer):
    next_meeting = Meeting(
        title="August Monthly Meeting",
        starts_at=datetime(2026, 8, 24, 23, 0, tzinfo=UTC),
        status=MeetingStatus.draft,
        public_token="august-meeting-token",
    )
    async with app.ctx.db.session() as db:
        db.add(next_meeting)
        await db.flush()

    _request, response = await app.asgi_client.patch(
        f"/api/v1/admin/meetings/{next_meeting.id}/status",
        json={"status": "open"},
        cookies=session_cookie(app, organizer),
        headers=csrf_headers(),
    )
    assert response.status == 200
    assert response.json["status"] == "open"

    async with app.ctx.db.session() as db:
        old = await db.get(Meeting, open_meeting.id)
        new = await db.get(Meeting, next_meeting.id)
        events = (await db.scalars(AuditEvent.__table__.select())).all()
        assert old.status == MeetingStatus.closed
        assert new.status == MeetingStatus.open
        assert len(events) == 2


@pytest.mark.asyncio
async def test_admin_api_requires_session(app):
    _request, response = await app.asgi_client.get("/api/v1/admin/dashboard")
    assert response.status == 401


@pytest.mark.asyncio
async def test_organizer_can_sign_in_with_password(app, organizer):
    _request, response = await app.asgi_client.post(
        "/api/v1/auth/login",
        json={"email": organizer.email.upper(), "password": "test-password"},
    )
    assert response.status == 200
    assert response.json["signed_in"] is True
    assert response.json["csrf_token"]
    assert response.cookies["pdc_session"]


@pytest.mark.asyncio
async def test_organizer_login_rejects_wrong_password(app, organizer):
    _request, response = await app.asgi_client.post(
        "/api/v1/auth/login",
        json={"email": organizer.email, "password": "wrong-password"},
    )
    assert response.status == 401

    async with app.ctx.db.session() as db:
        events = (await db.scalars(select(AuditEvent))).all()
        assert len(events) == 1
        assert events[0].action == "auth.login_failed"


@pytest.mark.asyncio
async def test_admin_mutation_requires_csrf(app, open_meeting, organizer):
    _request, response = await app.asgi_client.patch(
        f"/api/v1/admin/meetings/{open_meeting.id}/status",
        json={"status": "closed"},
        cookies=session_cookie(app, organizer),
    )
    assert response.status == 403


@pytest.mark.asyncio
async def test_login_rate_limit(app, organizer):
    app.ctx.settings.login_rate_limit = 2
    try:
        for _attempt in range(2):
            _request, response = await app.asgi_client.post(
                "/api/v1/auth/login",
                json={"email": organizer.email, "password": "wrong-password"},
            )
            assert response.status == 401

        _request, limited = await app.asgi_client.post(
            "/api/v1/auth/login",
            json={"email": organizer.email, "password": "wrong-password"},
        )
        assert limited.status == 429
    finally:
        app.ctx.settings.login_rate_limit = 5
        app.ctx.login_attempts.clear()


@pytest.mark.asyncio
async def test_owner_can_provision_organizer_with_one_time_setup_link(app, organizer):
    _request, created = await app.asgi_client.post(
        "/api/v1/admin/organizers",
        json={
            "email": "new.admin@example.com",
            "display_name": "New Admin",
            "role": "admin",
        },
        cookies=session_cookie(app, organizer),
        headers=csrf_headers(),
    )
    assert created.status == 201
    assert created.json["password_set"] is False
    token = created.json["setup_url"].rsplit("/", 1)[-1]

    _request, details = await app.asgi_client.get(
        f"/api/v1/auth/password-setup/{token}"
    )
    assert details.status == 200
    assert details.json["email"] == "new.admin@example.com"

    _request, completed = await app.asgi_client.post(
        f"/api/v1/auth/password-setup/{token}",
        json={"password": "a-strong-new-password"},
    )
    assert completed.status == 200

    _request, reused = await app.asgi_client.post(
        f"/api/v1/auth/password-setup/{token}",
        json={"password": "another-strong-password"},
    )
    assert reused.status == 400

    async with app.ctx.db.session() as db:
        provisioned = await db.scalar(
            select(Organizer).where(Organizer.email == "new.admin@example.com")
        )
        assert provisioned
        assert verify_password("a-strong-new-password", provisioned.password_hash)


@pytest.mark.asyncio
async def test_non_owner_cannot_manage_organizers(app):
    admin = Organizer(
        email="admin@example.com",
        display_name="Admin",
        password_hash="not-used",
        role=OrganizerRole.admin,
    )
    async with app.ctx.db.session() as db:
        db.add(admin)
        await db.flush()
    _request, response = await app.asgi_client.get(
        "/api/v1/admin/organizers",
        cookies=session_cookie(app, admin),
    )
    assert response.status == 403


@pytest.mark.asyncio
async def test_owner_cannot_demote_or_deactivate_self(app, organizer):
    for changes in ({"role": "admin"}, {"active": False}):
        _request, response = await app.asgi_client.patch(
            f"/api/v1/admin/organizers/{organizer.id}",
            json=changes,
            cookies=session_cookie(app, organizer),
            headers=csrf_headers(),
        )
        assert response.status == 400


@pytest.mark.asyncio
async def test_password_change_invalidates_existing_session(app, organizer):
    cookies = session_cookie(app, organizer)
    _request, changed = await app.asgi_client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "test-password",
            "password": "a-new-strong-password",
        },
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert changed.status == 200

    _request, stale = await app.asgi_client.get(
        "/api/v1/auth/me",
        cookies=cookies,
    )
    assert stale.status == 401
