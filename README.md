# Orbit

Orbit is a data collection platform with a Python collection pipeline,
historical PostgreSQL storage, a FastAPI administration API, and a React
dashboard. The initial collector retrieves Bangladesh annual inflation data
from the World Bank API.

## What is supported

- The registered `worldbank-bd-inflation` source, including API pagination.
- Per-record normalization and Pydantic validation.
- PostgreSQL current records, append-only observation versions, invalid-record
  diagnostics, and collection-run statistics.
- Stable record identities and SHA-256 content fingerprints to distinguish new,
  changed, and unchanged observations.
- An authenticated admin API for overview, sources, collection operations,
  records, history, data quality, and system status.
- A responsive dashboard with login, filtering, CSV export, and record-version
  comparisons.
- A CLI for collection runs, database migrations, and administrator password
  hash generation.

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

Apply pending additive schema migrations:

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli migrate
```

Collect current World Bank observations:

```powershell
.\.venv\Scripts\python.exe -m backend.app.cli collect --source worldbank-bd-inflation
```

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

Install frontend dependencies and start the API and dashboard in separate
PowerShell terminals:

```powershell
Set-Location frontend
npm install
npm run dev
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Open `http://localhost:5173`. The dashboard uses the API at
`http://localhost:8000` by default. To create a production frontend build, run
`npm run build` from `frontend`.

## Storage and history

Migrations create the collection tables and `orbit_admin_sessions`. A
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
