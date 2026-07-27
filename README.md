# Phoenixville Democrats Check-In

A mobile-first meeting attendance application for the Phoenixville Democratic Committee.
Organizers create and open a meeting, and attendees visit the root URL or scan that meeting's QR
code to check in with an existing profile or create a new one.

## Technology

- Python 3.14, Sanic 25.12 LTS, Pydantic, SQLAlchemy, Alembic, and PostgreSQL
- React 19, TypeScript, Vite, and TanStack Query
- `uv` for Python/toolchain management
- Docker, AWS App Runner, and Amazon RDS for deployment

## Local development

1. Copy `.env.example` to `.env` and configure the values.
2. Select Node 24 LTS: `nvm install && nvm use`.
3. Install the backend: `uv sync --all-groups`.
4. Create the database: `uv run alembic upgrade head`.
5. Install the frontend: `cd frontend && npm install`.
6. Run Sanic: `uv run sanic pdcdemscheckin.app:app --dev --port 8000`.
7. In another terminal, run Vite: `cd frontend && npm run dev`.

For a production-like local environment, use `docker compose up --build`.

## Active meeting behavior

There can be only one active meeting. Opening a meeting closes any meeting that was previously
open. The root application URL loads the active check-in automatically. If no meeting is open,
visitors see a branded no-active-meeting page.

## Google organizer sign-in

Create a Google OAuth web client with this callback:

`https://checkins.phoenixvilledems.org/api/v1/auth/callback`

Set the client ID/secret and a comma-separated organizer allowlist. The first allowlisted
organizer to sign in becomes the owner; later accounts become admins.

## Verification

```bash
uv run ruff check .
uv run pytest
cd frontend
npm run build
npm run test
```

See [infra/README.md](infra/README.md) for AWS deployment notes.
