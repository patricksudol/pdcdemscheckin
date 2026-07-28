from datetime import UTC, datetime

import pytest

from pdcdemscheckin.models import Checkin, Profile


@pytest.mark.asyncio
async def test_root_active_meeting_endpoint(app, open_meeting):
    _request, response = await app.asgi_client.get("/api/v1/public/meetings/active")
    assert response.status == 200
    assert response.json["active"] is True
    assert response.json["meeting"]["public_token"] == open_meeting.public_token


@pytest.mark.asyncio
async def test_no_active_meeting(app):
    _request, response = await app.asgi_client.get("/api/v1/public/meetings/active")
    assert response.status == 200
    assert response.json == {"active": False, "meeting": None}


@pytest.mark.asyncio
async def test_new_profile_then_returning_checkin_is_idempotent(app, open_meeting):
    payload = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": " Ada@Example.COM ",
        "phone": "(610) 555-1212",
        "consent": True,
    }
    _request, created = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/profiles", json=payload
    )
    assert created.status == 201
    assert created.json["checked_in"] is True

    _request, lookup = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/lookup",
        json={"email": "ada@example.com"},
    )
    assert lookup.json == {
        "found": True,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "phone": "6105551212",
        "committee_person": False,
        "already_checked_in": True,
    }

    _request, duplicate = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/checkins",
        json={"email": "ada@example.com"},
    )
    assert duplicate.status == 200
    assert duplicate.json["created"] is False

    async with app.ctx.db.session() as db:
        assert len((await db.scalars(Profile.__table__.select())).all()) == 1
        assert len((await db.scalars(Checkin.__table__.select())).all()) == 1


@pytest.mark.asyncio
async def test_returning_attendee_can_update_profile_while_checking_in(app, open_meeting):
    async with app.ctx.db.session() as db:
        profile = Profile(
            first_name="Ada",
            last_name="Byron",
            email="ada@example.com",
            normalized_email="ada@example.com",
            phone="6105550100",
            consented_at=datetime.now(UTC),
        )
        db.add(profile)
        await db.flush()
        profile_id = profile.id

    _request, response = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/checkins",
        json={
            "email": "ada@example.com",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "new_email": "ada.lovelace@example.com",
            "phone": "(610) 555-1212",
        },
    )
    assert response.status == 200
    assert response.json["created"] is True
    assert response.json["first_name"] == "Ada"

    async with app.ctx.db.session() as db:
        profile = await db.get(Profile, profile_id)
        assert profile.last_name == "Lovelace"
        assert profile.email == "ada.lovelace@example.com"
        assert profile.normalized_email == "ada.lovelace@example.com"
        assert profile.phone == "6105551212"


@pytest.mark.asyncio
async def test_committee_person_flag_is_visible_to_attendee(app, open_meeting):
    async with app.ctx.db.session() as db:
        profile = Profile(
            first_name="Committee",
            last_name="Person",
            email="committee@example.com",
            normalized_email="committee@example.com",
            committee_person=True,
            consented_at=datetime.now(UTC),
        )
        db.add(profile)
        await db.flush()

    _request, lookup = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/lookup",
        json={"email": "committee@example.com"},
    )
    assert lookup.status == 200
    assert lookup.json["committee_person"] is True

    _request, checkin = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/checkins",
        json={"email": "committee@example.com"},
    )
    assert checkin.status == 200
    assert checkin.json["committee_person"] is True


@pytest.mark.asyncio
async def test_consent_is_required(app, open_meeting):
    _request, response = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/profiles",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
            "consent": False,
        },
    )
    assert response.status == 422


@pytest.mark.asyncio
async def test_closed_meeting_rejects_checkin(app, open_meeting):
    async with app.ctx.db.session() as db:
        meeting = await db.get(type(open_meeting), open_meeting.id)
        meeting.status = "closed"
    _request, response = await app.asgi_client.post(
        f"/api/v1/public/meetings/{open_meeting.public_token}/lookup",
        json={"email": "nobody@example.com"},
    )
    assert response.status == 409
