from datetime import UTC, datetime

import pytest

from pdcdemscheckin.auth import issue_session
from pdcdemscheckin.models import AuditEvent, Meeting, MeetingStatus


def session_cookie(app, organizer):
    return {"pdc_session": issue_session(organizer, app.ctx.settings)}


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
    assert response.json == {"signed_in": True}
    assert response.cookies["pdc_session"]


@pytest.mark.asyncio
async def test_organizer_login_rejects_wrong_password(app, organizer):
    _request, response = await app.asgi_client.post(
        "/api/v1/auth/login",
        json={"email": organizer.email, "password": "wrong-password"},
    )
    assert response.status == 401
