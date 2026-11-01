from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.dependencies import get_session
from backend.app.collectors.worldbank import register_world_bank_sources
from backend.app.db.models import Base
from backend.app.main import app
from backend.app.api.auth import PASSWORD_HASHER


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_USERNAME", "agent-test-admin")
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        PASSWORD_HASHER.hash("agent-test-password"),
    )
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "agent-test-only-secret-" + "x" * 32)
    monkeypatch.setenv("ADMIN_ALLOWED_ORIGINS", "http://localhost:5173")

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        register_world_bank_sources(session, datetime.now(timezone.utc))

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


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": "agent-test-admin", "password": "agent-test-password"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_agent_api_requires_administrator_session(client: TestClient) -> None:
    response = client.get("/api/admin/agent/status")

    assert response.status_code == 401


def test_agent_status_reports_worker_offline_without_heartbeat(
    client: TestClient,
) -> None:
    _login(client)
    response = client.get("/api/admin/agent/status")

    assert response.status_code == 200
    assert response.json()["worker_online"] is False
    assert response.json()["workers"] == []
    assert response.json()["scheduled_sources"] == 3


def test_schedule_pause_resume_requires_csrf_and_records_decisions(
    client: TestClient,
) -> None:
    csrf_token = _login(client)
    source_key = "worldbank-bd-gdp-growth"
    headers = {
        "Origin": "http://localhost:5173",
        "X-CSRF-Token": csrf_token,
    }

    denied = client.post(f"/api/admin/agent/schedules/{source_key}/pause")
    assert denied.status_code == 403

    paused = client.post(
        f"/api/admin/agent/schedules/{source_key}/pause",
        headers=headers,
    )
    assert paused.status_code == 200
    schedule = client.get("/api/admin/agent/schedules").json()["items"]
    paused_item = next(item for item in schedule if item["source_id"] == source_key)
    assert paused_item["mode"] == "paused"
    assert paused_item["health_status"] == "paused"

    resumed = client.post(
        f"/api/admin/agent/schedules/{source_key}/resume",
        headers=headers,
    )
    assert resumed.status_code == 200
    schedule = client.get("/api/admin/agent/schedules").json()["items"]
    resumed_item = next(item for item in schedule if item["source_id"] == source_key)
    assert resumed_item["mode"] == "adaptive"
    assert resumed_item["next_due_at"] is not None

    decisions = client.get("/api/admin/agent/decisions").json()["items"]
    assert [item["reason_code"] for item in decisions[:2]] == [
        "administrator_resumed_schedule",
        "administrator_paused_schedule",
    ]


def test_schedule_interval_changes_are_validated_and_cannot_expose_secrets(
    client: TestClient,
) -> None:
    csrf_token = _login(client)
    response = client.patch(
        "/api/admin/agent/schedules/worldbank-bd-population",
        json={
            "base_interval_seconds": 3600,
            "minimum_interval_seconds": 86400,
        },
        headers={
            "Origin": "http://localhost:5173",
            "X-CSRF-Token": csrf_token,
        },
    )
    assert response.status_code == 409

    status = client.get("/api/admin/agent/status")
    assert status.status_code == 200
    assert "agent-test-only-secret" not in status.text
