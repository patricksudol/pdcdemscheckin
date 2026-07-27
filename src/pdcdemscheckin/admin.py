import csv
import hashlib
import io
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import qrcode
import qrcode.image.svg
from sanic import Blueprint, Request
from sanic.exceptions import InvalidUsage, NotFound
from sanic.response import raw, text
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from .auth import admin_required
from .models import (
    AuditEvent,
    Checkin,
    CheckinSource,
    Meeting,
    MeetingStatus,
    Organizer,
    OrganizerRole,
    PasswordSetupToken,
    Profile,
)
from .onetap import OneTapError
from .onetap import export as onetap_export
from .public import meeting_json, normalize_email, normalize_phone
from .schemas import (
    AdminProfileCreate,
    CorrectionReason,
    ManualCheckin,
    MeetingCreate,
    MeetingStatusUpdate,
    MeetingUpdate,
    MergeProfiles,
    OneTapBackfill,
    OrganizerCreate,
    OrganizerUpdate,
    ProfileUpdate,
)

admin_bp = Blueprint("admin", url_prefix="/api/v1/admin")


def profile_json(profile: Profile) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "email": profile.email,
        "phone": profile.phone,
        "consented_at": profile.consented_at.isoformat(),
        "created_at": profile.created_at.isoformat(),
        "deleted_at": profile.deleted_at.isoformat() if profile.deleted_at else None,
    }


def safe_csv(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def organizer_json(organizer: Organizer) -> dict[str, Any]:
    return {
        "id": str(organizer.id),
        "email": organizer.email,
        "display_name": organizer.display_name,
        "role": organizer.role.value,
        "active": organizer.active,
        "password_set": bool(organizer.password_hash),
        "created_at": organizer.created_at.isoformat(),
        "last_login_at": organizer.last_login_at.isoformat()
        if organizer.last_login_at
        else None,
    }


async def create_setup_link(db, request: Request, organizer: Organizer) -> str:
    now = datetime.now(UTC)
    await db.execute(
        update(PasswordSetupToken)
        .where(
            PasswordSetupToken.organizer_id == organizer.id,
            PasswordSetupToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordSetupToken(
            organizer_id=organizer.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            created_by_id=request.ctx.organizer.id,
            expires_at=now + timedelta(hours=24),
        )
    )
    settings = request.app.ctx.settings
    base_url = settings.public_base_url
    if settings.environment != "production":
        base_url = f"{request.scheme}://{request.host}"
    return f"{base_url.rstrip('/')}/setup-password/{raw_token}"


async def audit(
    db,
    request: Request,
    action: str,
    entity_type: str,
    entity_id: Any,
    *,
    reason: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=request.ctx.organizer.id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            reason=reason,
            before=before,
            after=after,
            request_id=getattr(request.ctx, "request_id", None),
        )
    )


def _onetap_time(value: Any) -> datetime:
    try:
        seconds = float(value)
        return datetime.fromtimestamp(seconds / 1000 if seconds > 100_000_000_000 else seconds, UTC)
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def _onetap_name(item: dict[str, Any]) -> tuple[str, str]:
    parts = str(item.get("name") or "OneTap Profile").strip().split(maxsplit=1)
    return parts[0][:100], (parts[1] if len(parts) > 1 else "Profile")[:100]


@admin_bp.get("/dashboard")
@admin_required()
async def dashboard(request: Request):
    async with request.app.ctx.db.session() as db:
        profile_count = await db.scalar(
            select(func.count(Profile.id)).where(Profile.deleted_at.is_(None))
        )
        checkin_count = await db.scalar(select(func.count(Checkin.id)))
        meeting_count = await db.scalar(select(func.count(Meeting.id)))
        recent = (
            await db.execute(
                select(Meeting)
                .options(selectinload(Meeting.checkins))
                .order_by(Meeting.starts_at.desc())
                .limit(6)
            )
        ).scalars()
        return {
            "counts": {
                "profiles": profile_count or 0,
                "checkins": checkin_count or 0,
                "meetings": meeting_count or 0,
            },
            "recent_meetings": [
                {**meeting_json(item), "checkin_count": len(item.checkins)} for item in recent
            ],
        }


@admin_bp.get("/meetings")
@admin_required()
async def list_meetings(request: Request):
    async with request.app.ctx.db.session() as db:
        meetings = (
            await db.execute(
                select(Meeting)
                .options(selectinload(Meeting.checkins))
                .order_by(Meeting.starts_at.desc())
            )
        ).scalars()
        return [
            {
                **meeting_json(item),
                "public_token": item.public_token,
                "checkin_count": len(item.checkins),
            }
            for item in meetings
        ]


@admin_bp.post("/meetings")
@admin_required()
async def create_meeting(request: Request):
    payload = MeetingCreate.model_validate(request.json or {})
    meeting = Meeting(
        **payload.model_dump(),
        public_token=secrets.token_urlsafe(24),
        created_by_id=request.ctx.organizer.id,
    )
    async with request.app.ctx.db.session() as db:
        db.add(meeting)
        await db.flush()
        await audit(
            db, request, "meeting.created", "meeting", meeting.id, after=meeting_json(meeting)
        )
        return {**meeting_json(meeting), "public_token": meeting.public_token}, 201


@admin_bp.patch("/meetings/<meeting_id:uuid>")
@admin_required()
async def update_meeting(request: Request, meeting_id: UUID):
    payload = MeetingUpdate.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise NotFound("Meeting not found")
        before = meeting_json(meeting)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(meeting, field, value)
        await db.flush()
        await audit(
            db,
            request,
            "meeting.updated",
            "meeting",
            meeting.id,
            before=before,
            after=meeting_json(meeting),
        )
        return {**meeting_json(meeting), "public_token": meeting.public_token}


@admin_bp.patch("/meetings/<meeting_id:uuid>/status")
@admin_required()
async def update_meeting_status(request: Request, meeting_id: UUID):
    payload = MeetingStatusUpdate.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise NotFound("Meeting not found")
        before = {"status": meeting.status.value}
        if payload.status.value == "open":
            previously_open = (
                await db.execute(
                    select(Meeting).where(
                        Meeting.status == "open",
                        Meeting.id != meeting.id,
                    )
                )
            ).scalars()
            for previous in previously_open:
                previous.status = "closed"
                await audit(
                    db,
                    request,
                    "meeting.auto_closed",
                    "meeting",
                    previous.id,
                    reason="Another meeting was made active",
                    before={"status": "open"},
                    after={"status": "closed"},
                )
            await db.flush()
        meeting.status = payload.status
        await audit(
            db,
            request,
            "meeting.status_changed",
            "meeting",
            meeting.id,
            before=before,
            after={"status": meeting.status.value},
        )
        return {**meeting_json(meeting), "public_token": meeting.public_token}


@admin_bp.get("/meetings/<meeting_id:uuid>/qr.svg")
@admin_required()
async def meeting_qr(request: Request, meeting_id: UUID):
    async with request.app.ctx.db.session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise NotFound("Meeting not found")
        url = f"{request.app.ctx.settings.public_base_url}/checkin/{meeting.public_token}"
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
        output = io.BytesIO()
        image.save(output)
        return raw(
            output.getvalue(),
            content_type="image/svg+xml",
            headers={"Content-Disposition": f'attachment; filename="meeting-{meeting.id}.svg"'},
        )


@admin_bp.get("/meetings/<meeting_id:uuid>/checkins")
@admin_required()
async def meeting_checkins(request: Request, meeting_id: UUID):
    async with request.app.ctx.db.session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise NotFound("Meeting not found")
        rows = (
            await db.execute(
                select(Checkin, Profile)
                .outerjoin(Profile, Checkin.profile_id == Profile.id)
                .where(Checkin.meeting_id == meeting_id)
                .order_by(Checkin.checked_in_at.desc())
            )
        ).all()
        return {
            "meeting": meeting_json(meeting),
            "checkins": [
                {
                    "id": str(checkin.id),
                    "profile": profile_json(profile) if profile else None,
                    "anonymized_name": checkin.anonymized_name,
                    "checked_in_at": checkin.checked_in_at.isoformat(),
                    "source": checkin.source.value,
                }
                for checkin, profile in rows
            ],
        }


@admin_bp.post("/meetings/<meeting_id:uuid>/checkins")
@admin_required()
async def manual_checkin(request: Request, meeting_id: UUID):
    payload = ManualCheckin.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        if not await db.get(Meeting, meeting_id):
            raise NotFound("Meeting not found")
        if not await db.get(Profile, payload.profile_id):
            raise NotFound("Profile not found")
        existing = await db.scalar(
            select(Checkin).where(
                Checkin.meeting_id == meeting_id, Checkin.profile_id == payload.profile_id
            )
        )
        if existing:
            return {"id": str(existing.id), "created": False}
        checkin = Checkin(
            meeting_id=meeting_id,
            profile_id=payload.profile_id,
            source=CheckinSource.admin,
            corrected_by_id=request.ctx.organizer.id,
        )
        db.add(checkin)
        await db.flush()
        await audit(
            db,
            request,
            "checkin.added",
            "checkin",
            checkin.id,
            reason=payload.reason,
            after={"meeting_id": str(meeting_id), "profile_id": str(payload.profile_id)},
        )
        return {"id": str(checkin.id), "created": True}, 201


@admin_bp.delete("/checkins/<checkin_id:uuid>")
@admin_required()
async def remove_checkin(request: Request, checkin_id: UUID):
    payload = CorrectionReason.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        checkin = await db.get(Checkin, checkin_id)
        if not checkin:
            raise NotFound("Check-in not found")
        before = {
            "meeting_id": str(checkin.meeting_id),
            "profile_id": str(checkin.profile_id),
            "checked_in_at": checkin.checked_in_at.isoformat(),
        }
        await db.delete(checkin)
        await audit(
            db,
            request,
            "checkin.removed",
            "checkin",
            checkin_id,
            reason=payload.reason,
            before=before,
        )
        return {"removed": True}


@admin_bp.get("/profiles")
@admin_required()
async def list_profiles(request: Request):
    query = str(request.args.get("q", "")).strip()
    async with request.app.ctx.db.session() as db:
        meeting_count = (
            select(func.count(Checkin.id))
            .where(Checkin.profile_id == Profile.id)
            .correlate(Profile)
            .scalar_subquery()
        )
        last_meeting_at = (
            select(func.max(Meeting.starts_at))
            .join(Checkin, Checkin.meeting_id == Meeting.id)
            .where(Checkin.profile_id == Profile.id)
            .correlate(Profile)
            .scalar_subquery()
        )
        statement = select(
            Profile,
            meeting_count.label("meeting_count"),
            last_meeting_at.label("last_meeting_at"),
        ).where(Profile.deleted_at.is_(None))
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    Profile.first_name.ilike(pattern),
                    Profile.last_name.ilike(pattern),
                    Profile.email.ilike(pattern),
                )
            )
        profiles = (
            await db.execute(statement.order_by(Profile.last_name, Profile.first_name).limit(200))
        ).all()
        return [
            {
                **profile_json(profile),
                "meeting_count": count,
                "last_meeting_at": last_meeting.isoformat() if last_meeting else None,
            }
            for profile, count, last_meeting in profiles
        ]


@admin_bp.post("/profiles")
@admin_required()
async def create_profile(request: Request):
    payload = AdminProfileCreate.model_validate(request.json or {})
    email = normalize_email(str(payload.email)) if payload.email else None
    phone = normalize_phone(payload.phone)
    try:
        async with request.app.ctx.db.session() as db:
            if email and await db.scalar(
                select(Profile).where(
                    Profile.normalized_email == email,
                    Profile.deleted_at.is_(None),
                )
            ):
                raise InvalidUsage("A profile with that email already exists")
            profile = Profile(
                first_name=payload.first_name.strip(),
                last_name=payload.last_name.strip(),
                email=email,
                normalized_email=email,
                phone=phone,
                consented_at=datetime.now(UTC),
            )
            db.add(profile)
            await db.flush()
            await audit(
                db,
                request,
                "profile.created",
                "profile",
                profile.id,
                reason="Created by an administrator",
                after=profile_json(profile),
            )
            return profile_json(profile), 201
    except IntegrityError as error:
        raise InvalidUsage("A profile with that email already exists") from error


@admin_bp.get("/profiles/<profile_id:uuid>/history")
@admin_required()
async def profile_history(request: Request, profile_id: UUID):
    async with request.app.ctx.db.session() as db:
        profile = await db.get(Profile, profile_id)
        if not profile or profile.deleted_at:
            raise NotFound("Profile not found")
        rows = (
            await db.execute(
                select(Checkin, Meeting)
                .join(Meeting, Checkin.meeting_id == Meeting.id)
                .where(Checkin.profile_id == profile_id)
                .order_by(Checkin.checked_in_at.desc())
            )
        ).all()
        dates = [checkin.checked_in_at for checkin, _meeting in rows]
        return {
            "stats": {
                "meetings_attended": len(rows),
                "first_checkin_at": min(dates).isoformat() if dates else None,
                "latest_checkin_at": max(dates).isoformat() if dates else None,
            },
            "meetings": [
                {
                    "id": str(meeting.id),
                    "title": meeting.title,
                    "starts_at": meeting.starts_at.isoformat(),
                    "checked_in_at": checkin.checked_in_at.isoformat(),
                }
                for checkin, meeting in rows
            ],
        }


@admin_bp.get("/organizers")
@admin_required(owner_only=True)
async def list_organizers(request: Request):
    async with request.app.ctx.db.session() as db:
        organizers = (
            await db.scalars(select(Organizer).order_by(Organizer.display_name))
        ).all()
        return [organizer_json(organizer) for organizer in organizers]


@admin_bp.get("/onetap/status")
@admin_required(owner_only=True)
async def onetap_status(request: Request):
    return {"configured": bool(request.app.ctx.settings.onetap_api_key)}


@admin_bp.post("/onetap/backfill")
@admin_required(owner_only=True)
async def onetap_backfill(request: Request):
    payload = OneTapBackfill.model_validate(request.json or {})
    api_key = request.app.ctx.settings.onetap_api_key
    if not api_key:
        raise InvalidUsage("Configure PDC_ONETAP_API_KEY in Render first")
    if not payload.dry_run and not payload.confirm:
        raise InvalidUsage("Confirm the import before writing data")
    try:
        lists, source_profiles, participants = await onetap_export(api_key)
    except OneTapError as error:
        raise InvalidUsage(str(error)) from error
    source_checkins = sum(
        1 for rows in participants.values() for item in rows if item.get("checkedIn")
    )
    source = {"profiles": len(source_profiles), "meetings": len(lists), "checkins": source_checkins}
    if payload.dry_run:
        return {"dry_run": True, "source": source}
    added = {"profiles": 0, "meetings": 0, "checkins": 0}
    async with request.app.ctx.db.session() as db:
        profiles = {
            profile.normalized_email: profile
            for profile in (
                await db.scalars(select(Profile).where(Profile.deleted_at.is_(None)))
            ).all()
            if profile.normalized_email
        }
        meetings = {
            (meeting.title, meeting.starts_at.replace(tzinfo=UTC)): meeting
            for meeting in (await db.scalars(select(Meeting))).all()
        }
        imported_profiles: dict[str, Profile] = {}

        def profile_for(item: dict[str, Any]) -> Profile:
            source_id = str(item.get("id") or item.get("profileId") or "")
            if source_id in imported_profiles:
                return imported_profiles[source_id]
            email = str(item.get("email") or "").strip()
            normalized = normalize_email(email) if "@" in email else None
            profile = profiles.get(normalized) if normalized else None
            if not profile:
                first_name, last_name = _onetap_name(item)
                profile = Profile(
                    first_name=first_name, last_name=last_name, email=normalized,
                    normalized_email=normalized, phone=normalize_phone(item.get("phone")),
                    consented_at=_onetap_time(
                        item.get("registrationDate") or item.get("createdAt")
                    ),
                )
                db.add(profile)
                added["profiles"] += 1
                if normalized:
                    profiles[normalized] = profile
            imported_profiles[source_id] = profile
            return profile

        for item in source_profiles:
            profile_for(item)
        await db.flush()
        imported_meetings: dict[str, Meeting] = {}
        for item in lists:
            if not item.get("date"):
                continue
            starts_at = _onetap_time(item["date"])
            title = str(item.get("name") or "OneTap meeting")[:180]
            key = (title, starts_at)
            meeting = meetings.get(key)
            if not meeting:
                meeting = Meeting(title=title, starts_at=starts_at, status=MeetingStatus.closed,
                    public_token=secrets.token_urlsafe(24), created_by_id=request.ctx.organizer.id)
                db.add(meeting)
                meetings[key] = meeting
                added["meetings"] += 1
            imported_meetings[str(item.get("id"))] = meeting
        await db.flush()
        pairs = set((await db.execute(select(Checkin.meeting_id, Checkin.profile_id))).all())
        for list_id, rows in participants.items():
            meeting = imported_meetings.get(list_id)
            if not meeting:
                continue
            for item in rows:
                if not item.get("checkedIn"):
                    continue
                profile_data = (
                    item.get("profile") if isinstance(item.get("profile"), dict) else item
                )
                profile = profile_for(
                    {**profile_data, "id": item.get("profileId") or profile_data.get("id")}
                )
                if (meeting.id, profile.id) in pairs:
                    continue
                db.add(
                    Checkin(
                        meeting_id=meeting.id,
                        profile_id=profile.id,
                        checked_in_at=_onetap_time(
                            item.get("checkInDate") or item.get("checkedInDate")
                        ),
                        source=CheckinSource.admin,
                        corrected_by_id=request.ctx.organizer.id,
                    )
                )
                pairs.add((meeting.id, profile.id))
                added["checkins"] += 1
        await audit(db, request, "onetap.backfill_completed", "onetap", "historical-data",
                    before={"source": source}, after={"imported": added})
    return {"dry_run": False, "source": source, "imported": added}


@admin_bp.post("/organizers")
@admin_required(owner_only=True)
async def create_organizer(request: Request):
    payload = OrganizerCreate.model_validate(request.json or {})
    email = str(payload.email).strip().lower()
    try:
        async with request.app.ctx.db.session() as db:
            if await db.scalar(select(Organizer).where(Organizer.email == email)):
                raise InvalidUsage("An organizer with that email already exists")
            organizer = Organizer(
                email=email,
                display_name=payload.display_name.strip(),
                role=payload.role,
                active=True,
            )
            db.add(organizer)
            await db.flush()
            setup_url = await create_setup_link(db, request, organizer)
            await audit(
                db,
                request,
                "organizer.created",
                "organizer",
                organizer.id,
                after=organizer_json(organizer),
            )
            return {**organizer_json(organizer), "setup_url": setup_url}, 201
    except IntegrityError as error:
        raise InvalidUsage("An organizer with that email already exists") from error


@admin_bp.patch("/organizers/<organizer_id:uuid>")
@admin_required(owner_only=True)
async def update_organizer(request: Request, organizer_id: UUID):
    payload = OrganizerUpdate.model_validate(request.json or {})
    changes = payload.model_dump(exclude_unset=True)
    async with request.app.ctx.db.session() as db:
        organizer = await db.get(Organizer, organizer_id)
        if not organizer:
            raise NotFound("Organizer not found")
        if organizer.id == request.ctx.organizer.id and (
            changes.get("active") is False
            or ("role" in changes and changes["role"] != OrganizerRole.owner)
        ):
            raise InvalidUsage("You cannot deactivate or demote your own owner account")
        removing_owner = (
            organizer.role == OrganizerRole.owner
            and organizer.active
            and (
                changes.get("active") is False
                or ("role" in changes and changes["role"] != OrganizerRole.owner)
            )
        )
        if removing_owner:
            active_owner_count = await db.scalar(
                select(func.count(Organizer.id)).where(
                    Organizer.role == OrganizerRole.owner,
                    Organizer.active.is_(True),
                )
            )
            if (active_owner_count or 0) <= 1:
                raise InvalidUsage("At least one active owner is required")
        before = organizer_json(organizer)
        for field, value in changes.items():
            if field == "display_name":
                value = value.strip()
            setattr(organizer, field, value)
        await db.flush()
        await audit(
            db,
            request,
            "organizer.updated",
            "organizer",
            organizer.id,
            before=before,
            after=organizer_json(organizer),
        )
        return organizer_json(organizer)


@admin_bp.delete("/organizers/<organizer_id:uuid>")
@admin_required(owner_only=True)
async def delete_organizer(request: Request, organizer_id: UUID):
    payload = CorrectionReason.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        organizer = await db.get(Organizer, organizer_id)
        if not organizer:
            raise NotFound("Organizer not found")
        if organizer.id == request.ctx.organizer.id:
            raise InvalidUsage("You cannot delete your own owner account")
        if organizer.role == OrganizerRole.owner and organizer.active:
            active_owner_count = await db.scalar(
                select(func.count(Organizer.id)).where(
                    Organizer.role == OrganizerRole.owner,
                    Organizer.active.is_(True),
                )
            )
            if (active_owner_count or 0) <= 1:
                raise InvalidUsage("At least one active owner is required")
        before = organizer_json(organizer)
        await db.execute(
            update(Meeting)
            .where(Meeting.created_by_id == organizer.id)
            .values(created_by_id=None)
        )
        await db.execute(
            update(Checkin)
            .where(Checkin.corrected_by_id == organizer.id)
            .values(corrected_by_id=None)
        )
        await db.execute(
            update(AuditEvent)
            .where(AuditEvent.actor_id == organizer.id)
            .values(actor_id=None)
        )
        await db.delete(organizer)
        await audit(
            db,
            request,
            "organizer.deleted",
            "organizer",
            organizer_id,
            reason=payload.reason,
            before=before,
            after={"deleted": True},
        )
        return {"deleted": True}


@admin_bp.post("/organizers/<organizer_id:uuid>/setup-link")
@admin_required(owner_only=True)
async def regenerate_setup_link(request: Request, organizer_id: UUID):
    async with request.app.ctx.db.session() as db:
        organizer = await db.get(Organizer, organizer_id)
        if not organizer:
            raise NotFound("Organizer not found")
        if not organizer.active:
            raise InvalidUsage("Reactivate this organizer before creating a setup link")
        setup_url = await create_setup_link(db, request, organizer)
        await audit(
            db,
            request,
            "organizer.setup_link_created",
            "organizer",
            organizer.id,
        )
        return {"setup_url": setup_url, "expires_in_hours": 24}


@admin_bp.get("/organizers/activity")
@admin_required(owner_only=True)
async def organizer_activity(request: Request):
    async with request.app.ctx.db.session() as db:
        events = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.action.like("auth.%"))
                .order_by(AuditEvent.created_at.desc())
                .limit(50)
            )
        ).all()
        return [
            {
                "id": str(event.id),
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "action": event.action,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]


@admin_bp.patch("/profiles/<profile_id:uuid>")
@admin_required()
async def update_profile(request: Request, profile_id: UUID):
    payload = ProfileUpdate.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        profile = await db.get(Profile, profile_id)
        if not profile or profile.deleted_at:
            raise NotFound("Profile not found")
        before = profile_json(profile)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field == "email":
                value = normalize_email(str(value)) if value else None
                profile.normalized_email = value
            if field == "phone":
                value = normalize_phone(value)
            setattr(profile, field, value)
        await db.flush()
        await audit(
            db,
            request,
            "profile.updated",
            "profile",
            profile.id,
            before=before,
            after=profile_json(profile),
        )
        return profile_json(profile)


@admin_bp.delete("/profiles/<profile_id:uuid>")
@admin_required()
async def delete_profile(request: Request, profile_id: UUID):
    payload = CorrectionReason.model_validate(request.json or {})
    async with request.app.ctx.db.session() as db:
        profile = await db.get(Profile, profile_id)
        if not profile or profile.deleted_at:
            raise NotFound("Profile not found")
        before = profile_json(profile)
        checkins = (
            await db.execute(select(Checkin).where(Checkin.profile_id == profile.id))
        ).scalars()
        for checkin in checkins:
            checkin.anonymized_name = "Deleted attendee"
            checkin.profile_id = None
        profile.email = None
        profile.normalized_email = None
        profile.phone = None
        profile.first_name = "Deleted"
        profile.last_name = "Attendee"
        profile.deleted_at = datetime.now(UTC)
        await audit(
            db,
            request,
            "profile.deleted",
            "profile",
            profile.id,
            reason=payload.reason,
            before=before,
            after={"deleted": True},
        )
        return {"deleted": True}


@admin_bp.post("/profiles/merge")
@admin_required()
async def merge_profiles(request: Request):
    payload = MergeProfiles.model_validate(request.json or {})
    if payload.source_profile_id == payload.target_profile_id:
        raise InvalidUsage("Source and target must be different")
    async with request.app.ctx.db.session() as db:
        source = await db.get(Profile, payload.source_profile_id)
        target = await db.get(Profile, payload.target_profile_id)
        if not source or not target or source.deleted_at or target.deleted_at:
            raise NotFound("Profile not found")
        target_meeting_ids = set(
            (
                await db.scalars(select(Checkin.meeting_id).where(Checkin.profile_id == target.id))
            ).all()
        )
        source_checkins = (
            await db.execute(select(Checkin).where(Checkin.profile_id == source.id))
        ).scalars()
        for checkin in source_checkins:
            if checkin.meeting_id in target_meeting_ids:
                await db.delete(checkin)
            else:
                checkin.profile_id = target.id
        source.email = None
        source.normalized_email = None
        source.phone = None
        source.first_name = "Merged"
        source.last_name = "Profile"
        source.deleted_at = datetime.now(UTC)
        await audit(
            db,
            request,
            "profile.merged",
            "profile",
            source.id,
            reason=payload.reason,
            before={"source_id": str(source.id)},
            after={"target_id": str(target.id)},
        )
        return {"merged": True, "target_profile_id": str(target.id)}


@admin_bp.get("/meetings/<meeting_id:uuid>/export.csv")
@admin_required()
async def export_meeting(request: Request, meeting_id: UUID):
    async with request.app.ctx.db.session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise NotFound("Meeting not found")
        rows = (
            await db.execute(
                select(Checkin, Profile)
                .outerjoin(Profile, Checkin.profile_id == Profile.id)
                .where(Checkin.meeting_id == meeting_id)
                .order_by(Checkin.checked_in_at)
            )
        ).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Meeting",
                "Meeting date",
                "First name",
                "Last name",
                "Email",
                "Phone",
                "Check-in time",
                "Source",
            ]
        )
        for checkin, profile in rows:
            writer.writerow(
                [
                    safe_csv(meeting.title),
                    meeting.starts_at.isoformat(),
                    safe_csv(profile.first_name if profile else "Deleted"),
                    safe_csv(profile.last_name if profile else "Attendee"),
                    safe_csv(profile.email if profile else ""),
                    safe_csv(profile.phone if profile else ""),
                    checkin.checked_in_at.isoformat(),
                    checkin.source.value,
                ]
            )
        return text(
            output.getvalue(),
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}.csv"'},
        )
