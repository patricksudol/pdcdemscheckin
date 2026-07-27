import re
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from sanic import Blueprint, Request
from sanic.exceptions import InvalidUsage, NotFound, SanicException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import Checkin, Meeting, MeetingStatus, Profile
from .schemas import EmailLookup, ExistingCheckin, ProfileCreate

public_bp = Blueprint("public", url_prefix="/api/v1/public")
_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    value = re.sub(r"[^\d+]", "", phone)
    if len(re.sub(r"\D", "", value)) < 7:
        raise InvalidUsage("Please enter a valid phone number")
    return value


def check_rate_limit(request: Request, token: str) -> None:
    key = f"{request.remote_addr}:{token}"
    now = datetime.now(UTC)
    window = _attempts[key]
    while window and window[0] < now - timedelta(minutes=1):
        window.popleft()
    if len(window) >= request.app.ctx.settings.checkin_rate_limit:
        raise SanicException("Please wait a minute and try again", status_code=429)
    window.append(now)


async def get_open_meeting(db, token: str) -> Meeting:
    meeting = (
        await db.execute(select(Meeting).where(Meeting.public_token == token))
    ).scalar_one_or_none()
    if not meeting:
        raise NotFound("Meeting not found")
    return meeting


def meeting_json(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": str(meeting.id),
        "title": meeting.title,
        "starts_at": meeting.starts_at.isoformat(),
        "location": meeting.location,
        "attendee_message": meeting.attendee_message,
        "status": meeting.status.value,
    }


@public_bp.get("/meetings/<token:str>")
async def meeting_details(request: Request, token: str):
    check_rate_limit(request, token)
    async with request.app.ctx.db.session() as db:
        return meeting_json(await get_open_meeting(db, token))


@public_bp.get("/meetings/active")
async def active_meeting(request: Request):
    async with request.app.ctx.db.session() as db:
        meeting = (
            await db.execute(
                select(Meeting)
                .where(Meeting.status == MeetingStatus.open)
                .order_by(Meeting.starts_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not meeting:
            return {"active": False, "meeting": None}
        return {
            "active": True,
            "meeting": {**meeting_json(meeting), "public_token": meeting.public_token},
        }


@public_bp.post("/meetings/<token:str>/lookup")
async def lookup_profile(request: Request, token: str):
    check_rate_limit(request, token)
    payload = EmailLookup.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        meeting = await get_open_meeting(db, token)
        if meeting.status != MeetingStatus.open:
            raise SanicException("Check-in is not open for this meeting", status_code=409)
        profile = (
            await db.execute(
                select(Profile).where(
                    Profile.normalized_email == normalize_email(str(payload.email)),
                    Profile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not profile:
            return {"found": False}
        existing = (
            await db.execute(
                select(Checkin.id).where(
                    Checkin.meeting_id == meeting.id, Checkin.profile_id == profile.id
                )
            )
        ).scalar_one_or_none()
        return {
            "found": True,
            "first_name": profile.first_name,
            "already_checked_in": existing is not None,
        }


@public_bp.post("/meetings/<token:str>/checkins")
async def checkin_existing(request: Request, token: str):
    check_rate_limit(request, token)
    payload = ExistingCheckin.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        meeting = await get_open_meeting(db, token)
        if meeting.status != MeetingStatus.open:
            raise SanicException("Check-in is not open for this meeting", status_code=409)
        profile = (
            await db.execute(
                select(Profile).where(
                    Profile.normalized_email == normalize_email(str(payload.email)),
                    Profile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not profile:
            raise NotFound("Profile not found")
        profile_first_name = profile.first_name
        checkin = Checkin(meeting_id=meeting.id, profile_id=profile.id)
        db.add(checkin)
        try:
            await db.flush()
            created = True
        except IntegrityError:
            await db.rollback()
            created = False
        return {"checked_in": True, "created": created, "first_name": profile_first_name}


@public_bp.post("/meetings/<token:str>/profiles")
async def create_profile_and_checkin(request: Request, token: str):
    check_rate_limit(request, token)
    payload = ProfileCreate.model_validate(request.json or {})
    email = normalize_email(str(payload.email))
    async with request.app.ctx.db.session() as db:
        meeting = await get_open_meeting(db, token)
        if meeting.status != MeetingStatus.open:
            raise SanicException("Check-in is not open for this meeting", status_code=409)
        existing = (
            await db.execute(
                select(Profile).where(
                    Profile.normalized_email == email, Profile.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise SanicException("A profile already exists for that email", status_code=409)
        profile = Profile(
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=email,
            normalized_email=email,
            phone=normalize_phone(payload.phone),
            consented_at=datetime.now(UTC),
        )
        db.add(profile)
        await db.flush()
        db.add(Checkin(meeting_id=meeting.id, profile_id=profile.id))
        await db.flush()
        return {
            "checked_in": True,
            "created": True,
            "profile_id": str(profile.id),
            "first_name": profile.first_name,
        }, 201
