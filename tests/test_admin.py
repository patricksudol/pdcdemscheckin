from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select

from pdcdemscheckin.auth import hash_password, issue_session, verify_password
from pdcdemscheckin.models import (
    AuditEvent,
    Checkin,
    Meeting,
    MeetingStatus,
    Organizer,
    OrganizerRole,
    Profile,
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
async def test_owner_can_edit_existing_meeting(app, open_meeting, organizer):
    updated_time = datetime(2026, 7, 28, 0, 30, tzinfo=UTC)
    _request, response = await app.asgi_client.patch(
        f"/api/v1/admin/meetings/{open_meeting.id}",
        json={
            "title": "Updated Monthly Meeting",
            "starts_at": updated_time.isoformat(),
            "location": "Updated Location",
            "attendee_message": "Updated welcome message",
        },
        cookies=session_cookie(app, organizer),
        headers=csrf_headers(),
    )
    assert response.status == 200
    assert response.json["title"] == "Updated Monthly Meeting"
    assert response.json["location"] == "Updated Location"

    async with app.ctx.db.session() as db:
        meeting = await db.get(Meeting, open_meeting.id)
        event = await db.scalar(
            select(AuditEvent).where(AuditEvent.action == "meeting.updated")
        )
        assert meeting.title == "Updated Monthly Meeting"
        assert meeting.starts_at.replace(tzinfo=UTC) == updated_time
        assert event
        assert event.before["title"] == "July Monthly Meeting"


@pytest.mark.asyncio
async def test_admin_can_create_edit_and_delete_profile(app, open_meeting, organizer):
    cookies = session_cookie(app, organizer)
    _request, response = await app.asgi_client.post(
        "/api/v1/admin/profiles",
        json={
            "first_name": "Taylor",
            "last_name": "Example",
            "phone": "(610) 555-0100",
            "committee_person": True,
        },
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 201
    profile_id = response.json["id"]
    profile_uuid = UUID(profile_id)
    assert response.json["email"] is None
    assert response.json["committee_person"] is True

    _request, response = await app.asgi_client.patch(
        f"/api/v1/admin/profiles/{profile_id}",
        json={
            "first_name": "Tay",
            "email": "TAYLOR@example.com",
            "phone": "610-555-0199",
        },
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 200
    assert response.json["first_name"] == "Tay"

    _request, response = await app.asgi_client.patch(
        f"/api/v1/admin/profiles/{profile_id}",
        json={"email": None},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 200
    assert response.json["email"] is None

    async with app.ctx.db.session() as db:
        db.add(
            Checkin(
                meeting_id=open_meeting.id,
                profile_id=profile_uuid,
            )
        )

    _request, response = await app.asgi_client.get(
        "/api/v1/admin/profiles", cookies=cookies
    )
    assert response.status == 200
    listed_profile = next(profile for profile in response.json if profile["id"] == profile_id)
    assert listed_profile["meeting_count"] == 1
    assert listed_profile["committee_person"] is True
    assert listed_profile["last_meeting_at"].startswith("2026-07-27T23:00:00")

    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/profiles/{profile_id}",
        json={"reason": "Requested removal"},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 200

    async with app.ctx.db.session() as db:
        profile = await db.get(Profile, profile_uuid)
        checkin = await db.scalar(select(Checkin))
        actions = set((await db.scalars(select(AuditEvent.action))).all())
        assert profile.deleted_at
        assert profile.email is None
        assert checkin.profile_id is None
        assert checkin.anonymized_name == "Deleted attendee"
        assert {"profile.created", "profile.updated", "profile.deleted"} <= actions


@pytest.mark.asyncio
async def test_admin_can_manually_check_in_and_out_profile(app, open_meeting, organizer):
    profile = Profile(
        first_name="Manual",
        last_name="Attendee",
        email="manual@example.com",
        normalized_email="manual@example.com",
        consented_at=datetime.now(UTC),
    )
    async with app.ctx.db.session() as db:
        db.add(profile)
        await db.flush()

    cookies = session_cookie(app, organizer)
    _request, response = await app.asgi_client.post(
        f"/api/v1/admin/meetings/{open_meeting.id}/checkins",
        json={"profile_id": str(profile.id), "reason": "Checked in manually by organizer"},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 201
    checkin_id = response.json["id"]

    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/checkins/{checkin_id}",
        json={"reason": "Checked out manually by organizer"},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 200

    async with app.ctx.db.session() as db:
        assert await db.get(Checkin, UUID(checkin_id)) is None
        actions = set((await db.scalars(select(AuditEvent.action))).all())
        assert {"checkin.added", "checkin.removed"} <= actions


@pytest.mark.asyncio
async def test_admin_can_create_a_profile_during_manual_checkin(app, open_meeting, organizer):
    _request, response = await app.asgi_client.post(
        f"/api/v1/admin/meetings/{open_meeting.id}/checkins/new-profile",
        json={
            "first_name": "New",
            "last_name": "Attendee",
            "email": "new.attendee@example.com",
            "phone": "(610) 555-0123",
        },
        cookies=session_cookie(app, organizer),
        headers=csrf_headers(),
    )
    assert response.status == 201
    assert response.json["created"] is True
    assert response.json["profile"]["email"] == "new.attendee@example.com"

    async with app.ctx.db.session() as db:
        profile = await db.get(Profile, UUID(response.json["profile"]["id"]))
        checkin = await db.get(Checkin, UUID(response.json["id"]))
        actions = set((await db.scalars(select(AuditEvent.action))).all())
        assert profile.phone == "6105550123"
        assert checkin.profile_id == profile.id
        assert checkin.source.value == "admin"
        assert {"profile.created", "checkin.added"} <= actions


@pytest.mark.asyncio
async def test_admin_api_requires_session(app):
    _request, response = await app.asgi_client.get("/api/v1/admin/dashboard")
    assert response.status == 401


@pytest.mark.asyncio
async def test_admin_can_export_a_meetings_checked_in_attendees(app, open_meeting, organizer):
    async with app.ctx.db.session() as db:
        first = Profile(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            normalized_email="ada@example.com",
            phone="6105550100",
            consented_at=datetime.now(UTC),
        )
        second = Profile(
            first_name="Grace",
            last_name="Hopper",
            email="grace@example.com",
            normalized_email="grace@example.com",
            consented_at=datetime.now(UTC),
        )
        db.add_all([first, second])
        await db.flush()
        db.add_all([
            Checkin(meeting_id=open_meeting.id, profile_id=first.id),
            Checkin(meeting_id=open_meeting.id, profile_id=second.id),
        ])

    _request, response = await app.asgi_client.get(
        f"/api/v1/admin/meetings/{open_meeting.id}/export.csv",
        cookies=session_cookie(app, organizer),
    )

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.splitlines()
    assert lines[0].startswith("Meeting,Meeting date,First name")
    assert any("Ada,Lovelace,ada@example.com,6105550100" in line for line in lines)
    assert any("Grace,Hopper,grace@example.com,," in line for line in lines)


@pytest.mark.asyncio
async def test_meeting_export_requires_admin_session(app, open_meeting):
    _request, response = await app.asgi_client.get(
        f"/api/v1/admin/meetings/{open_meeting.id}/export.csv"
    )
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
async def test_owner_can_delete_other_organizer_but_not_self_or_last_owner(app, organizer):
    other_owner = Organizer(
        email="other.owner@example.com",
        display_name="Other Owner",
        password_hash=hash_password("other-owner-password"),
        role=OrganizerRole.owner,
    )
    admin = Organizer(
        email="delete.admin@example.com",
        display_name="Delete Admin",
        password_hash=hash_password("delete-admin-password"),
        role=OrganizerRole.admin,
    )
    async with app.ctx.db.session() as db:
        db.add_all([other_owner, admin])
        await db.flush()

    cookies = session_cookie(app, organizer)
    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/organizers/{admin.id}",
        json={"reason": "No longer serving"},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 200

    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/organizers/{organizer.id}",
        json={"reason": "Self removal"},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 400

    _request, response = await app.asgi_client.request(
        "DELETE",
        f"/api/v1/admin/organizers/{other_owner.id}",
        json={"reason": "No longer serving"},
        cookies=cookies,
        headers=csrf_headers(),
    )
    assert response.status == 200

    async with app.ctx.db.session() as db:
        assert await db.get(Organizer, admin.id) is None
        assert await db.get(Organizer, other_owner.id) is None
        event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "organizer.deleted"))
        assert event


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
