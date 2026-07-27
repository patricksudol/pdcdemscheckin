from datetime import UTC, datetime
from functools import wraps
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sanic import Blueprint, Request
from sanic.exceptions import Forbidden, Unauthorized
from sanic.response import redirect
from sqlalchemy import select

from .models import Organizer, OrganizerRole
from .settings import Settings

auth_bp = Blueprint("auth", url_prefix="/api/v1/auth")


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="pdc-admin-session")


def issue_session(organizer: Organizer, settings: Settings) -> str:
    return _serializer(settings).dumps({"id": str(organizer.id), "email": organizer.email})


def read_session(token: str, settings: Settings) -> dict[str, str] | None:
    try:
        return _serializer(settings).loads(token, max_age=settings.session_max_age_seconds)
    except BadSignature, SignatureExpired:
        return None


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


@auth_bp.get("/login")
async def login(request: Request):
    settings: Settings = request.app.ctx.settings
    if not settings.google_client_id:
        raise Forbidden("Google sign-in is not configured")
    redirect_uri = f"{settings.public_base_url}/api/v1/auth/callback"
    state = _serializer(settings).dumps({"purpose": "google_oauth"})
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return redirect(url)


@auth_bp.get("/callback")
async def callback(request: Request):
    settings: Settings = request.app.ctx.settings
    state = request.args.get("state", "")
    try:
        state_data = _serializer(settings).loads(state, max_age=600)
    except (BadSignature, SignatureExpired) as error:
        raise Forbidden("Invalid or expired sign-in request") from error
    if state_data.get("purpose") != "google_oauth" or not request.args.get("code"):
        raise Forbidden("Invalid sign-in request")
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": request.args["code"],
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": f"{settings.public_base_url}/api/v1/auth/callback",
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        user_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_response.raise_for_status()
        user = user_response.json()
    email = str(user["email"]).strip().lower()
    if not user.get("email_verified") or email not in settings.admin_allowlist:
        raise Forbidden("This Google account is not approved")

    async with request.app.ctx.db.session() as db:
        organizer = (
            await db.execute(select(Organizer).where(Organizer.email == email))
        ).scalar_one_or_none()
        if not organizer:
            existing_count = len((await db.scalars(select(Organizer.id))).all())
            organizer = Organizer(
                google_subject=str(user["sub"]),
                email=email,
                display_name=str(user.get("name") or email),
                role=OrganizerRole.owner if existing_count == 0 else OrganizerRole.admin,
            )
            db.add(organizer)
            await db.flush()
        organizer.google_subject = str(user["sub"])
        organizer.display_name = str(user.get("name") or email)
        organizer.last_login_at = datetime.now(UTC)

    response = redirect("/admin")
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
