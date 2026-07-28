# Phoenixville Democrats Check-In

A mobile-first attendance application for Phoenixville Democratic Committee monthly meetings.
An organizer opens one meeting, making it the active meeting. Visitors to the app's root URL are
sent directly to its check-in form; when nothing is active, they see a branded splash page.

## Stack

- Python 3.14 and Sanic 25.12 LTS
- SQLAlchemy 2 and Psycopg 3 for async application access and synchronous Alembic migrations
- PostgreSQL 17
- React 19, TypeScript, Vite, and TanStack Query
- `uv` for Python versions, dependencies, and `uv.lock`
- NVM with Node 24 LTS; npm and `package-lock.json` for frontend dependencies
- Docker Engine, Compose, and Buildx
- AWS App Runner and Amazon RDS deployment target

## Quick start with Docker

This is the recommended development path. Host Python, Node, and PostgreSQL are not required
because the image supplies them.

### 1. Install Docker on Ubuntu 26.04

Run as root, or prefix the commands with `sudo`:

```bash
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
```

Create `/etc/apt/sources.list.d/docker.sources`:

```text
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: resolute
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
```

Then install Docker:

```bash
apt-get update
apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version
docker compose version
```

### 2. Configure and start the app

```bash
cd /root/Code/pdcdemscheckin
cp .env.example .env
docker compose up --build -d
docker compose ps
```

The Compose environment uses Psycopg 3:

```text
postgresql+psycopg://pdc:pdc@db:5432/pdcdemscheckin
```

Alembic migrations run automatically when the app container starts. PostgreSQL data persists in
the `postgres-data` Docker volume.

Verify the app:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/v1/public/meetings/active
```

Expected responses on a fresh installation:

```json
{"status":"ok"}
{"active":false,"meeting":null}
```

Open `http://127.0.0.1:8000`. Before an organizer opens a meeting, the no-active-meeting splash
page is expected.

Useful commands:

```bash
docker compose logs -f app
docker compose restart app
docker compose down
docker compose down -v  # also deletes the local PostgreSQL volume
```

The final command is destructive and should only be used when intentionally resetting local data.

## Organizer sign-in

Organizer access uses email and password credentials. For local development, set the seeded
test account in `.env`:

```dotenv
PDC_PUBLIC_BASE_URL=http://localhost:8000
PDC_SESSION_SECRET=generate-a-long-random-value
PDC_SEED_ADMIN_EMAIL=admin@pdc.test
PDC_SEED_ADMIN_PASSWORD=demo2026
PDC_SEED_ADMIN_NAME=Test Organizer
```

Generate a session secret with:

```bash
openssl rand -hex 32
```

The seed command only creates the organizer when that email does not already exist. Restart after
configuration changes:

```bash
docker compose up -d --force-recreate app
```

On the HTTP local stack, Compose deliberately sets secure cookies off. Production must use HTTPS,
strong credentials stored as secrets, and `PDC_SECURE_COOKIES=true`.

### Provisioning additional organizers

Owners can open **Admin > Organizers** to create accounts, select an `admin` or `owner` role,
deactivate access, review recent authentication activity, and generate password setup links.
Setup links:

- contain a cryptographically random token whose SHA-256 hash is stored in the database;
- expire after 24 hours;
- are invalidated when a replacement link is generated;
- can be used only once; and
- invalidate any existing sessions when a password is set.

No email provider is configured. The owner must copy the generated setup link and send it to the
organizer through a trusted channel. Organizers can change their own password under **My
password**, which signs out their existing session. The API prevents an owner from deactivating
or demoting their own account and always requires at least one active owner.

## Native development without Docker

Use this path when editing with hot reload.

### Install and select the toolchains

Install `uv`, then let it provision Python 3.14:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /root/Code/pdcdemscheckin
uv python install 3.14
uv sync --all-groups
```

Install NVM using its official installation instructions, then:

```bash
cd /root/Code/pdcdemscheckin
nvm install
nvm use
node --version  # v24.x
cd frontend
npm install
```

NVM manages the Node/npm runtime. npm remains the frontend package manager and uses
`frontend/package-lock.json`.

### Run PostgreSQL and the development servers

Start only PostgreSQL with Docker:

```bash
docker compose up -d db
```

Copy `.env.example` to `.env`, and keep its host-facing database URL:

```text
postgresql+psycopg://pdc:pdc@localhost:5432/pdcdemscheckin
```

Apply migrations and start Sanic:

```bash
uv run alembic upgrade head
uv run sanic pdcdemscheckin.app:app --dev --host 0.0.0.0 --port 8000
```

In a second terminal:

```bash
cd /root/Code/pdcdemscheckin
nvm use
cd frontend
npm run dev
```

Vite runs on port 5173 and proxies `/api` requests to Sanic on port 8000.

## Verification

Backend:

```bash
uv run ruff check .
uv run pytest
```

Frontend:

```bash
cd frontend
nvm use
npm run lint
npm run build
npm audit --omit=dev
```

Production container:

```bash
docker compose build --no-cache app
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/api/health
```

## Active meeting behavior

- Meetings begin in `draft`.
- Opening a meeting makes it the single active meeting.
- Opening another meeting automatically closes the previous active meeting.
- The database also enforces that at most one meeting is open.
- The root URL loads the active check-in; without one, it displays the splash page.
- Each profile can check in only once per meeting.

## Deployment

Render is the primary production target. The checked-in `render.yaml` Blueprint creates:

- a Starter Docker web service in Virginia;
- a private Basic-256MB PostgreSQL 17 database;
- a generated session-signing secret;
- a database migration pre-deploy command;
- a one-time organizer seed hook;
- readiness checks at `/api/ready`; and
- deployment from `main` only after GitHub CI passes.

### First deployment

1. In Render, choose **New > Blueprint** and connect this repository.
2. During the initial Blueprint form, provide a real organizer email, a unique password of at
   least 12 characters, and the organizer's display name for the three `PDC_SEED_ADMIN_*`
   variables.
3. Apply the Blueprint and wait for the database, migration, initial seed, and web service to
   complete.
4. Verify `/api/ready`, sign in at `/admin`, and confirm a test meeting and QR code.
5. Remove `PDC_SEED_ADMIN_EMAIL` and `PDC_SEED_ADMIN_PASSWORD` from the Render service after the
   organizer exists. The seed is idempotent, but production credentials should not remain in the
   runtime environment.
6. In Wix DNS, point the `checkins` CNAME to the hostname Render supplies and verify the custom
   domain in Render.

The Render target URL is `https://pdcdemscheckin.onrender.com`. Wix should link its **Check In**
menu item to that URL; the app intentionally prevents iframe embedding.

Production settings are validated at startup. Production refuses to run with SQLite, HTTP, an
insecure cookie, or a short/default session secret. Render's `postgresql://` connection string is
automatically normalized to the Psycopg 3 SQLAlchemy driver.

The GitHub Actions workflow runs backend lint and tests plus frontend lint and build checks.
Render waits for those checks before deploying.

AWS App Runner remains an alternative target. See [infra/README.md](infra/README.md) for the older
AWS architecture notes.

## GitHub

The configured remote is:

```text
git@github.com:patricksudol/pdcdemscheckin.git
```

After authenticating the machine with GitHub:

```bash
git branch -M main
git push -u origin main
```
