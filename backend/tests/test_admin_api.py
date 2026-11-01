import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.dependencies import get_session
from backend.app.api.routes.records import _safe_csv_value
from backend.app.core.admin_config import (
    AdminConfigurationError,
    get_admin_config,
)
from backend.app.db.models import Base
from backend.app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ADMIN_USERNAME", "test-admin")
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        get_admin_config_password_hash(),
    )
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "test-session-secret-" + "x" * 32)
    monkeypatch.setenv("ADMIN_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("APP_ENV", "test")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def get_admin_config_password_hash() -> str:
    from backend.app.api.auth import PASSWORD_HASHER

    return PASSWORD_HASHER.hash("test-only-password")


def test_missing_session_secret_reports_exact_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "test-admin")
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        get_admin_config_password_hash(),
    )
    monkeypatch.delenv("ADMIN_SESSION_SECRET", raising=False)

    with pytest.raises(
        AdminConfigurationError,
        match="ADMIN_SESSION_SECRET must be configured with at least 32 characters.",
    ):
        get_admin_config()


def test_admin_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/api/admin/overview")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_login_session_and_logout(client: TestClient) -> None:
    login_response = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "test-only-password"},
        headers={"Origin": "http://localhost:5173"},
    )

    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["username"] == "test-admin"
    assert "csrf_token" in login_body
    assert "orbit_admin_session" in client.cookies

    session_response = client.get(
        "/api/auth/session",
        headers={"Origin": "http://localhost:5173"},
    )
    assert session_response.status_code == 200
    csrf_token = session_response.json()["csrf_token"]

    logout_response = client.post(
        "/api/auth/logout",
        headers={
            "Origin": "http://localhost:5173",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert logout_response.status_code == 204
    assert client.get("/api/auth/session").status_code == 401


@pytest.mark.parametrize("value", ["=1+1", "  @SUM(A1:A2)", "+cmd", "-1", "\tdata"])
def test_csv_values_are_safe_for_spreadsheets(value: str) -> None:
    assert _safe_csv_value(value).startswith("'")


def test_csv_values_preserve_non_formula_text() -> None:
    assert _safe_csv_value("World Bank") == "World Bank"
