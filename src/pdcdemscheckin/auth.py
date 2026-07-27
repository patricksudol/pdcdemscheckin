import hashlib
import hmac
import secrets
from collections import deque
from datetime import UTC, datetime
from functools import wraps
from typing import Any
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sanic import Blueprint, Request
from sanic.exceptions import Forbidden, InvalidUsage, SanicException, Unauthorized
from sanic.response import json, redirect
from sqlalchemy import select

from .models import AuditEvent, Organizer, OrganizerRole
from .settings import Settings

auth_bp = Blueprint("auth", url_prefix="/api/v1/auth")
PASSWORD_ALGORITHM = "scrypt"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="pdc-admin-session")


def issue_session(
    organizer: Organizer, settings: Settings, *, csrf_token: str | None = None
) -> str:
    return _serializer(settings).dumps(
        {
            "id": str(organizer.id),
            "email": organizer.email,
            "csrf_token": csrf_token or secrets.token_urlsafe(32),
        }
    )


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


DUMMY_PASSWORD_HASH = hash_password(
    "not-a-real-organizer-password",
    salt=b"\0" * 16,
)


async def current_organizer(request: Request) -> Organizer:
    token = request.cookies.get("pdc_session")
    if not token:
        raise Unauthorized("Organizer sign-in required")
    session_data = read_session(token, request.app.ctx.settings)
    if not session_data:
        raise Unauthorized("Organizer session expired")
    request.ctx.session_data = session_data
    try:
        organizer_id = UUID(session_data["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise Unauthorized("Organizer session is invalid") from error
    async with request.app.ctx.db.session() as db:
        organizer = await db.get(Organizer, organizer_id)
        if not organizer or not organizer.active:
            raise Unauthorized("Organizer access is inactive")
        return organizer


def require_csrf(request: Request) -> None:
    expected = request.ctx.session_data.get("csrf_token", "")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise Forbidden("Invalid CSRF token")


def admin_required(owner_only: bool = False):
    def decorator(handler):
        @wraps(handler)
        async def wrapped(request: Request, *args: Any, **kwargs: Any):
            organizer = await current_organizer(request)
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                require_csrf(request)
            if owner_only and organizer.role != OrganizerRole.owner:
                raise Forbidden("Owner access required")
            request.ctx.organizer = organizer
            return await handler(request, *args, **kwargs)

        return wrapped

    return decorator


def _login_key(request: Request, email: str) -> str:
    return hashlib.sha256(f"{request.ip}\0{email}".encode()).hexdigest()


def _check_login_rate_limit(request: Request, email: str, settings: Settings) -> str:
    key = _login_key(request, email)
    attempts: deque[datetime] = request.app.ctx.login_attempts[key]
    now = datetime.now(UTC)
    cutoff = now.timestamp() - settings.login_rate_window_seconds
    while attempts and attempts[0].timestamp() < cutoff:
        attempts.popleft()
    if len(attempts) >= settings.login_rate_limit:
        raise SanicException(
            "Too many sign-in attempts. Try again later.",
            status_code=429,
        )
    return key


@auth_bp.post("/login")
async def login(request: Request):
    settings: Settings = request.app.ctx.settings
    payload = request.json or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not email or not password:
        raise InvalidUsage("Email and password are required")
    attempt_key = _check_login_rate_limit(request, email, settings)
    authenticated = False
    organizer: Organizer | None = None
    async with request.app.ctx.db.session() as db:
        organizer = (
            await db.execute(select(Organizer).where(Organizer.email == email))
        ).scalar_one_or_none()
        password_hash = organizer.password_hash if organizer else DUMMY_PASSWORD_HASH
        password_valid = verify_password(password, password_hash)
        authenticated = bool(organizer and organizer.active and password_valid)
        if authenticated and organizer:
            organizer.last_login_at = datetime.now(UTC)
            db.add(
                AuditEvent(
                    actor_id=organizer.id,
                    action="auth.login_succeeded",
                    entity_type="organizer",
                    entity_id=str(organizer.id),
                    request_id=getattr(request.ctx, "request_id", None),
                )
            )
        else:
            request.app.ctx.login_attempts[attempt_key].append(datetime.now(UTC))
            db.add(
                AuditEvent(
                    action="auth.login_failed",
                    entity_type="login",
                    entity_id=hashlib.sha256(email.encode()).hexdigest(),
                    reason="Invalid credentials",
                    request_id=getattr(request.ctx, "request_id", None),
                )
            )

    if not authenticated or not organizer:
        raise Unauthorized("Email or password is incorrect")

    request.app.ctx.login_attempts.pop(attempt_key, None)
    csrf_token = secrets.token_urlsafe(32)
    response = json({"signed_in": True, "csrf_token": csrf_token})
    response.add_cookie(
        "pdc_session",
        issue_session(organizer, settings, csrf_token=csrf_token),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="Lax",
        max_age=settings.session_max_age_seconds,
        path="/",
    )
    return response


@auth_bp.post("/logout")
@admin_required()
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
        "csrf_token": request.ctx.session_data["csrf_token"],
    }
