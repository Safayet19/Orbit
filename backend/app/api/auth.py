import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.schemas import AuthenticatedUser, LoginRequest
from backend.app.core.admin_config import AdminConfig, AdminConfigurationError, get_admin_config
from backend.app.db.models import AdminSession

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SESSION_COOKIE = "orbit_admin_session"
SESSION_HOURS = 8
LOGIN_WINDOW_SECONDS = 900
LOGIN_MAX_ATTEMPTS = 5
PASSWORD_HASHER = PasswordHash.recommended()
_login_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def _admin_config() -> AdminConfig:
    try:
        return get_admin_config()
    except AdminConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator authentication is not configured.",
        ) from None


def _check_origin(request: Request, config: AdminConfig) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in config.allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def _hash_session_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _hash_csrf_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _allowed_login_attempt(client_id: str) -> bool:
    now = time.monotonic()
    cutoff = now - LOGIN_WINDOW_SECONDS
    with _attempts_lock:
        if len(_login_attempts) > 1024:
            for key in list(_login_attempts):
                attempts = [item for item in _login_attempts[key] if item > cutoff]
                if attempts:
                    _login_attempts[key] = attempts
                else:
                    _login_attempts.pop(key, None)
        attempts = [item for item in _login_attempts.get(client_id, []) if item > cutoff]
        _login_attempts[client_id] = attempts
        return len(attempts) < LOGIN_MAX_ATTEMPTS


def _record_failed_login(client_id: str) -> None:
    with _attempts_lock:
        _login_attempts.setdefault(client_id, []).append(time.monotonic())


def _clear_login_attempts(client_id: str) -> None:
    with _attempts_lock:
        _login_attempts.pop(client_id, None)


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookie(
    response: Response,
    token: str,
    config: AdminConfig,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_HOURS * 60 * 60,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/api",
    )


def get_admin_session(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AdminSession:
    config = _admin_config()
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    token_hash = _hash_session_token(token, config.session_secret)
    admin_session = session.scalar(
        select(AdminSession)
        .where(AdminSession.token_hash == token_hash)
        .where(AdminSession.expires_at > datetime.now(timezone.utc))
    )
    if admin_session is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    return admin_session


def require_csrf(
    request: Request,
    csrf_token: str | None,
    admin_session: AdminSession,
    config: AdminConfig,
) -> None:
    _check_origin(request, config)
    if not csrf_token or not hmac.compare_digest(
        _hash_csrf_token(csrf_token),
        admin_session.csrf_hash,
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


@router.post("/login", response_model=AuthenticatedUser)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> AuthenticatedUser:
    config = _admin_config()
    _check_origin(request, config)
    client_id = _client_id(request)
    if not _allowed_login_attempt(client_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )

    username_matches = hmac.compare_digest(payload.username, config.username)
    try:
        password_matches = PASSWORD_HASHER.verify(
            payload.password,
            config.password_hash,
        )
    except Exception:
        password_matches = False

    if not username_matches or not password_matches:
        _record_failed_login(client_id)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    _clear_login_attempts(client_id)
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session.execute(
        delete(AdminSession).where(AdminSession.expires_at <= now)
    )
    session.add(
        AdminSession(
            token_hash=_hash_session_token(token, config.session_secret),
            csrf_hash=_hash_csrf_token(csrf_token),
            expires_at=now + timedelta(hours=SESSION_HOURS),
        )
    )
    session.commit()
    _set_session_cookie(response, token, config)
    return AuthenticatedUser(username=config.username, csrf_token=csrf_token)


@router.get("/session", response_model=AuthenticatedUser)
def session_status(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
) -> AuthenticatedUser:
    config = _admin_config()
    _check_origin(request, config)
    csrf_token = secrets.token_urlsafe(32)
    admin_session.csrf_hash = _hash_csrf_token(csrf_token)
    session.commit()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _set_session_cookie(response, token, config)
    return AuthenticatedUser(username=config.username, csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Response:
    config = _admin_config()
    require_csrf(request, csrf_token, admin_session, config)
    session.delete(admin_session)
    session.commit()
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/api",
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
