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

## Viewing the Hetzner development app from an iPad

The Hetzner server runs the app on its own loopback port 8000. In Blink Shell on the iPad, open a
dedicated session and keep it running:

```bash
ssh -N -L 8080:127.0.0.1:8000 root@178.156.217.239
```

Then open this URL in Safari:

```text
http://127.0.0.1:8080
```

The `-N` option creates only the tunnel, so a blank Blink screen is normal. Keep Blink connected
while using Safari; iPadOS may suspend the tunnel if Blink is force-closed. Port 8080 is the
iPad-side port, while port 8000 is the Hetzner-side application port.

## Google organizer sign-in

Public splash and check-in pages work without Google configuration. The organizer dashboard
requires a Google OAuth web client.

For local development, register this authorized redirect URI:

```text
http://localhost:8000/api/v1/auth/callback
```

For production, register:

```text
https://checkins.phoenixvilledems.org/api/v1/auth/callback
```

Set these values in `.env`:

```dotenv
PDC_PUBLIC_BASE_URL=http://localhost:8000
PDC_SESSION_SECRET=generate-a-long-random-value
PDC_GOOGLE_CLIENT_ID=your-client-id
PDC_GOOGLE_CLIENT_SECRET=your-client-secret
PDC_ADMIN_ALLOWLIST=first.organizer@example.com,second.organizer@example.com
```

Generate a session secret with:

```bash
openssl rand -hex 32
```

Restart after configuration changes:

```bash
docker compose up -d --force-recreate app
```

The first allowlisted organizer to sign in becomes the owner. Later allowlisted accounts become
admins. On the HTTP local stack, Compose deliberately sets secure cookies off. Production must use
HTTPS and `PDC_SECURE_COOKIES=true`.

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

The target production URL is `https://checkins.phoenixvilledems.org`. The existing Wix site can
link or redirect its `/checkin` page to that subdomain without moving the Wix site itself.

See [infra/README.md](infra/README.md) for the AWS App Runner, private RDS, VPC, secrets, DNS, and
backup requirements.

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
