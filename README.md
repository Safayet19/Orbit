# Orbit

Orbit is a data collection platform with a Python collection pipeline,
historical PostgreSQL storage, a FastAPI administration API, and a React
dashboard. Its independent autonomous worker manages approved Bangladesh
economic and demographic collections from the World Bank API.

## What is supported

- Three approved World Bank Bangladesh sources, including API pagination:
  inflation, GDP growth, and population.
- Per-record normalization and Pydantic validation.
- PostgreSQL current records, append-only observation versions, invalid-record
  diagnostics, and collection-run statistics.
- Stable record identities and SHA-256 content fingerprints to distinguish new,
  changed, and unchanged observations.
- An authenticated admin API for overview, sources, collection operations,
  records, history, data quality, and system status.
- An independent persistent worker with scheduling policies, leases, bounded
  retries, crash recovery, and explainable decisions.
- A responsive dashboard with login, filtering, CSV export, record-version
  comparisons, and an Agent Control Center for worker state, schedules, jobs,
  quality, and decision history.
- A CLI for collection runs, worker startup, database migrations, and
  administrator password hash generation.

## Project structure

```text
backend/
  app/
    agents/
    api/
    collectors/
    core/
    db/
    pipeline/
    schemas/
    cli.py
    main.py
  migrations/
    env.py
    versions/
  tests/
frontend/
  src/
  package.json
alembic.ini
requirements.txt
```

## Requirements and configuration

Orbit uses Python 3.13, HTTPX, Pydantic, SQLAlchemy 2.x, psycopg 3,
python-dotenv, Alembic, pytest, and Node.js/npm for the dashboard. The World
Bank adapter uses the JSON API; HTML parsing libraries are not needed for this
source.

The root `.env` must define `DATABASE_URL` for the existing PostgreSQL database
`orbit_db`. The application loads this file for local development without
overriding system-provided environment variables. The URL must address
`orbit_db`; the application enforces PostgreSQL TLS (`sslmode=require`) if a
stronger TLS mode is not already configured. Never put real credentials in
`.env.example`, source code, logs, or documentation.

From Windows PowerShell, install the pinned Python dependencies into the
existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the existing Neon connection URL in `.env`, ensuring the selected database
is `orbit_db`. The application verifies the server-side database name before
running migrations or collection. Do not copy a URL or password into shell
commands.

## Migrations and collection

Apply pending additive schema migrations, including the autonomous-agent
tables. Existing collection data and admin sessions are preserved:

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli migrate
```

Run a one-time collection manually:

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli collect --source worldbank-bd-inflation
```

Other approved source IDs are `worldbank-bd-gdp-growth` and
`worldbank-bd-population`.

The CLI summarizes fetched, new, changed, unchanged, and invalid records. It
returns a nonzero exit code on failure. Request retries are bounded, incomplete
paginated responses are not persisted, and invalid records are quarantined
without storing raw response bodies.

## Admin dashboard

Configure these values in the root `.env` before signing in:

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD_HASH` — generate an Argon2id hash with
  `.\.venv\Scripts\python.exe -m backend.app.cli hash-password`. The command
  prompts for the password without echoing it.
- `ADMIN_SESSION_SECRET` — a random secret of at least 32 characters.
- `ADMIN_ALLOWED_ORIGINS` — comma-separated trusted browser origins. Local
  development uses `http://localhost:5173`.

Authentication is disabled until those required admin settings are configured;
Orbit does not provide default credentials. Admin sessions are opaque,
server-managed, HTTP-only cookies with CSRF protection and a limited lifetime.
The API never returns the database URL or password.

## Autonomous agent and dashboard

Apply migrations before starting the worker. Run the API, frontend, and
autonomous worker in separate Windows PowerShell terminals from the project
root:

Terminal 1 — FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Terminal 2 — React dashboard:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Terminal 3 — persistent autonomous worker:

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli agent start
```

Open `http://localhost:5173`. The dashboard uses the API at
`http://localhost:8000` by default. To create a production frontend build, run
`npm run build` from `frontend`. For a single worker scheduling/recovery cycle
and exit, use:

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli agent --once
```

The worker seeds only the approved World Bank sources and preserves existing
administrator policy when it starts. By default, schedules are adaptive with
bounded intervals; authenticated administrators can pause/resume sources or
adjust mode, interval, and priority from Agent Control Center.

### Docker Compose development

Docker Desktop with Docker Compose Watch support is required. Compose builds
the frontend, FastAPI backend, and autonomous worker as separate services.
Ports are published only on localhost. The existing root `.env` is mounted
read-only at runtime, never copied into an image. The API reads its existing
settings from that file; the worker extracts only `DATABASE_URL` into its
process environment. Pass `.env.example` to Compose so its interpolation
parser never expands credential characters from the private `.env`. Compose
does not apply database migrations automatically.

Apply migrations manually when needed:

```powershell
docker compose --env-file .env.example run --rm --no-deps backend python -m backend.app.cli migrate
```

Start the complete development environment from the project root:

```powershell
docker compose --env-file .env.example up --build --watch
```

Vite hot reload uses polling for Windows Docker Desktop file synchronization;
FastAPI runs Uvicorn with reload. Frontend/backend source changes sync into
their containers, and worker source changes sync before Compose gracefully
restarts the worker. Dependency manifest changes rebuild the affected image.
This Compose configuration is for local development; production deployment
should use separate runtime, networking, and secret-management configuration.

## Storage and history

Migrations create the collection tables, `orbit_admin_sessions`, and persistent
agent worker, job, schedule, and decision state. A
source/external-ID unique constraint prevents duplicate current observations.
Each new record gets version 1; a changed content fingerprint appends a version
and updates the current record. Unchanged observations update
`last_observed_at` without adding a version. Collection timestamps and other
incidental metadata are excluded from fingerprints. Missing source observations
are not treated as deletions.

Database writes for each completed collection are transactional. Collection
failures are recorded with sanitized error summaries, and logs never include
the database URL or request credentials.

## Data access

The adapter accesses the public World Bank API. Users are responsible for
checking source terms, attribution, access rules, and any permission required
for their intended use, especially commercial reuse.
