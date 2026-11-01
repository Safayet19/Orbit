import os
from dataclasses import dataclass

from backend.app.core.config import PROJECT_ROOT

DEFAULT_ADMIN_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class AdminConfig:
    username: str
    password_hash: str
    session_secret: str
    allowed_origins: tuple[str, ...]
    cookie_secure: bool
    environment: str


class AdminConfigurationError(RuntimeError):
    pass


def get_admin_config() -> AdminConfig:
    if not (PROJECT_ROOT / ".env").is_file():
        raise AdminConfigurationError("Project-root .env file was not found.")

    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    session_secret = os.environ.get("ADMIN_SESSION_SECRET", "")
    if not username:
        raise AdminConfigurationError("ADMIN_USERNAME is not configured.")
    if not password_hash:
        raise AdminConfigurationError("ADMIN_PASSWORD_HASH is not configured.")
    if len(session_secret) < 32:
        raise AdminConfigurationError(
            "ADMIN_SESSION_SECRET must be configured with at least 32 characters."
        )

    origins_setting = os.environ.get("ADMIN_ALLOWED_ORIGINS", "").strip()
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in origins_setting.split(",")
        if origin.strip()
    ) or DEFAULT_ADMIN_ORIGINS
    if any(not origin.startswith(("http://localhost", "http://127.0.0.1", "https://")) for origin in origins):
        raise AdminConfigurationError("Admin origins must use HTTPS or localhost.")

    secure_value = os.environ.get("ADMIN_COOKIE_SECURE")
    secure_cookie = (
        secure_value.lower() == "true"
        if secure_value is not None
        else os.environ.get("APP_ENV", "development") == "production"
    )

    return AdminConfig(
        username=username,
        password_hash=password_hash,
        session_secret=session_secret,
        allowed_origins=origins,
        cookie_secure=secure_cookie,
        environment=os.environ.get("APP_ENV", "development"),
    )
