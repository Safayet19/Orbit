import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_DATABASE = "orbit_db"

load_dotenv(PROJECT_ROOT / ".env", override=False)


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is invalid."""


def get_database_url() -> URL:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise ConfigurationError("DATABASE_URL is missing.")

    try:
        url = make_url(value)
    except ArgumentError:
        raise ConfigurationError("DATABASE_URL is invalid.") from None

    if url.database != EXPECTED_DATABASE:
        raise ConfigurationError("DATABASE_URL must target orbit_db.")
    if not url.drivername.startswith(("postgres", "postgresql")):
        raise ConfigurationError("DATABASE_URL must use PostgreSQL.")

    query = dict(url.query)
    sslmode = str(query.get("sslmode", "")).lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        query["sslmode"] = "require"

    return url.set(drivername="postgresql+psycopg", query=query)
