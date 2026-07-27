import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from functools import wraps
from typing import Any
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sanic import Blueprint, Request
from sanic.exceptions import Forbidden, InvalidUsage, Unauthorized
from sanic.response import json, redirect
from sqlalchemy import select

from .models import Organizer, OrganizerRole
from .settings import Settings

auth_bp = Blueprint("auth", url_prefix="/api/v1/auth")
PASSWORD_ALGORITHM = "scrypt"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="pdc-admin-session")


def issue_session(organizer: Organizer, settings: Settings) -> str:
    return _serializer(settings).dumps({"id": str(organizer.id), "email": organizer.email})


def read_session(token: str, settings: Settings) -> dict[str, str] | None:
    try:
        return _serializer(settings).loads(token, max_age=settings.session_max_age_seconds)
    except BadSignature, SignatureExpired:
        return None


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{PASSWORD_ALGORITHM}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, salt_hex, expected_hex = encoded.split("$", 2)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


async def current_organizer(request: Request) -> Organizer:
    token = request.cookies.get("pdc_session")
    if not token:
        raise Unauthorized("Organizer sign-in required")
    session_data = read_session(token, request.app.ctx.settings)
    if not session_data:
        raise Unauthorized("Organizer session expired")
    async with request.app.ctx.db.session() as db:
        organizer = await db.get(Organizer, UUID(session_data["id"]))
        if not organizer or not organizer.active:
            raise Unauthorized("Organizer access is inactive")
        return organizer


def admin_required(owner_only: bool = False):
    def decorator(handler):
        @wraps(handler)
        async def wrapped(request: Request, *args: Any, **kwargs: Any):
            organizer = await current_organizer(request)
            if owner_only and organizer.role != OrganizerRole.owner:
                raise Forbidden("Owner access required")
            request.ctx.organizer = organizer
            return await handler(request, *args, **kwargs)

        return wrapped

    return decorator


@auth_bp.post("/login")
async def login(request: Request):
    settings: Settings = request.app.ctx.settings
    payload = request.json or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not email or not password:
        raise InvalidUsage("Email and password are required")
    async with request.app.ctx.db.session() as db:
        organizer = (
            await db.execute(select(Organizer).where(Organizer.email == email))
        ).scalar_one_or_none()
        if not organizer or not organizer.active or not verify_password(
            password, organizer.password_hash
        ):
            raise Unauthorized("Email or password is incorrect")
        organizer.last_login_at = datetime.now(UTC)

    response = json({"signed_in": True})
    response.add_cookie(
        "pdc_session",
        issue_session(organizer, settings),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="Lax",
        max_age=settings.session_max_age_seconds,
        path="/",
    )
    return response


@auth_bp.post("/logout")
async def logout(request: Request):
    response = redirect("/")
    response.delete_cookie("pdc_session", path="/")
    return response


@auth_bp.get("/me")
@admin_required()
async def me(request: Request):
    organizer = request.ctx.organizer
    return {
        "id": str(organizer.id),
        "email": organizer.email,
        "display_name": organizer.display_name,
        "role": organizer.role.value,
    }
