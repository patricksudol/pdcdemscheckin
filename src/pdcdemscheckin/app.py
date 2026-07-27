import uuid
from collections import defaultdict, deque
from pathlib import Path

from pydantic import ValidationError
from sanic import Request, Sanic
from sanic.exceptions import SanicException
from sanic.response import file, json
from sqlalchemy import text

from .admin import admin_bp
from .auth import auth_bp
from .db import Database
from .public import public_bp
from .settings import Settings, get_settings


def create_app(
    settings: Settings | None = None, *, name: str = "PhoenixvilleDemocratsCheckin"
) -> Sanic:
    settings = settings or get_settings()
    app = Sanic(name)
    app.config.FALLBACK_ERROR_FORMAT = "json"
    app.ctx.settings = settings
    app.ctx.db = Database(settings.database_url)
    app.ctx.login_attempts = defaultdict(deque)
    app.blueprint(auth_bp)
    app.blueprint(public_bp)
    app.blueprint(admin_bp)

    @app.middleware("request")
    async def request_context(request: Request) -> None:
        request.ctx.request_id = request.headers.get("x-request-id", str(uuid.uuid4()))

    @app.middleware("response")
    async def normalize_response(request: Request, response):
        if isinstance(response, tuple):
            body, status = response
            response = json(body, status=status)
        elif isinstance(response, (dict, list)):
            response = json(response)

        response.headers["X-Request-ID"] = request.ctx.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.exception(ValidationError)
    async def validation_error(_request: Request, error: ValidationError):
        return json(
            {
                "error": "validation_error",
                "message": "Please check the highlighted fields",
                "details": error.errors(include_url=False, include_context=False),
            },
            status=422,
        )

    @app.exception(SanicException)
    async def sanic_error(_request: Request, error: SanicException):
        return json(
            {"error": error.__class__.__name__, "message": str(error)},
            status=error.status_code,
        )

    @app.get("/api/health")
    async def health(_request: Request):
        return {"status": "ok"}

    @app.get("/api/ready")
    async def ready(_request: Request):
        try:
            async with app.ctx.db.session() as db:
                await db.execute(text("SELECT 1"))
            return {"status": "ready"}
        except Exception:
            return json({"status": "unavailable"}, status=503)

    frontend = Path(settings.frontend_dist)
    if frontend.exists():
        app.static("/assets", frontend / "assets", name="assets")

        @app.get("/<path:path>")
        async def spa(_request: Request, path: str):
            requested = frontend / path
            if requested.is_file() and frontend in requested.resolve().parents:
                return await file(requested)
            return await file(frontend / "index.html")

        @app.get("/")
        async def spa_root(_request: Request):
            return await file(frontend / "index.html")

    @app.after_server_stop
    async def close_database(_app: Sanic):
        await _app.ctx.db.close()

    return app


app = create_app()
