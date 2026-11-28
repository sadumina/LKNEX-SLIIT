"""Automated tests for Member 04 FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.database import db
from app.main import app

client = TestClient(app)


@pytest.fixture
def account_headers(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_DB_PATH", str(tmp_path / "accounts.sqlite3"))
    credentials = {"email": "account@example.com", "password": "Demo1234"}
    with TestClient(app) as auth_client:
        signup = auth_client.post("/api/auth/signup", json={**credentials, "role": "admin"})
        assert signup.status_code == 201
        assert signup.json()["role"] == "user"
        login = auth_client.post("/api/auth/login", json=credentials)
        assert login.status_code == 200
        return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_verify_runs_complete_pipeline(monkeypatch, account_headers):
    from app.services.verification_service import VerificationService

    def verify(self, **kwargs):
        assert kwargs["user_role"] == "user"
        return {
            "run_id": "test-run",
            "action": "approve",
            "decision_reason": "All claims are supported.",
            "final_answer": kwargs["draft_answer"],
            "verification": {
                "overall_status": "all_supported",
                "total_claims": 1,
                "supported_count": 1,
                "contradicted_count": 0,
                "insufficient_count": 0,
                "claims": [],
            },
            "security": {
                "overall_risk": "low",
                "recommended_action": "allow",
                "findings": [],
            },
            "latency_ms": 1,
            "llm_calls": 1,
        }

    monkeypatch.setattr(VerificationService, "verify_complete", verify)
    response = client.post(
        "/api/verify",
        headers=account_headers,
        json={
            "question": "What is AI?",
            "draft_answer": "AI means artificial intelligence.",
            "user_role": "admin",
            "mode": "multi_agent",
        },
    )

    assert response.status_code == 200
    assert response.json()["action"] == "approve"
    assert response.json()["run_id"] == "test-run"


def test_verify_rejects_missing_question(account_headers):
    response = client.post(
        "/api/verify",
        headers=account_headers,
        json={
            "draft_answer": "AI means artificial intelligence.",
            "mode": "multi_agent",
        },
    )

    assert response.status_code == 422


def test_account_roles_and_session_expiry(account_headers):
    history = "/api/audit/runs"
    stats = "/api/audit/stats/actions"
    assert client.get(history, headers=account_headers).status_code == 403
    assert client.post("/api/verify", json={"question": "Q", "draft_answer": "A"}).status_code == 401

    connection = db.connect()
    try:
        with connection:
            connection.execute("UPDATE user_sessions SET expires_at = 0")
        assert client.get(history, headers=account_headers).status_code == 401
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("domain", "role", "env_var", "history_status", "stats_status"),
    [
        ("admin.com", "admin", "AEGIS_ADMIN_SIGNUP_CODE", 200, 200),
        ("systemengineer.com", "systems_engineer", "AEGIS_SYSTEMS_ENGINEER_SIGNUP_CODE", 200, 403),
        ("hr.com", "hr", "AEGIS_HR_SIGNUP_CODE", 403, 403),
    ],
)
def test_domain_roles(monkeypatch, tmp_path, domain, role, env_var, history_status, stats_status):
    monkeypatch.setenv("AEGIS_DB_PATH", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv(env_var, "test-signup-code")
    credentials = {"email": f"ExampleUser@{domain.upper()}", "password": "Demo1234"}
    with TestClient(app) as auth_client:
        assert auth_client.post("/api/auth/signup", json=credentials).status_code == 403
        signup = auth_client.post(
            "/api/auth/signup", json={**credentials, "signup_code": "test-signup-code"}
        )
        assert signup.status_code == 201
        assert signup.json()["role"] == role
        login = auth_client.post("/api/auth/login", json=credentials)
        assert login.status_code == 200
        assert login.json()["user"]["role"] == role
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert auth_client.get("/api/audit/runs", headers=headers).status_code == history_status
        assert auth_client.get("/api/audit/stats/actions", headers=headers).status_code == stats_status


def test_audit_rejects_missing_api_key(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    response = client.get("/api/audit/runs")

    assert response.status_code == 401


def test_reviewer_cannot_access_admin_statistics(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    response = client.get(
        "/api/audit/stats/actions",
        headers={"X-API-Key": "test-reviewer-key"},
    )

    assert response.status_code == 403


def test_invalid_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    response = client.get(
        "/api/audit/runs",
        headers={"X-API-Key": "invalid-key"},
    )

    assert response.status_code == 401


def test_admin_can_read_audit_runs(monkeypatch, tmp_path):
    from app.database import db

    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    test_db = tmp_path / "member04_test.sqlite3"
    conn = db.connect(str(test_db))
    db.init_db(conn)
    conn.close()

    def get_test_db():
        connection = db.connect(str(test_db))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[db.get_db] = get_test_db

    try:
        response = client.get(
            "/api/audit/runs",
            headers={"X-API-Key": "test-admin-key"},
        )

        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.pop(db.get_db, None)


def test_audit_retrieves_saved_event(monkeypatch, tmp_path):
    from app.database import db

    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    test_db = tmp_path / "audit_event_test.sqlite3"
    conn = db.connect(str(test_db))
    db.init_db(conn)

    run_id = db.start_run(
        conn,
        mode="multi_agent",
        user_role="tester",
        question="What is AI?",
        draft_answer="AI means artificial intelligence.",
    )

    db.log_event(
        conn,
        run_id,
        agent="backend_test",
        event="test_created",
        details={"source": "automated_test"},
    )

    conn.commit()
    conn.close()

    def get_test_db():
        connection = db.connect(str(test_db))
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[db.get_db] = get_test_db

    try:
        response = client.get(
            f"/api/audit/runs/{run_id}",
            headers={"X-API-Key": "test-admin-key"},
        )

        assert response.status_code == 200

        data = response.json()
        assert data["run"]["run_id"] == run_id
        assert data["events"][0]["event"] == "test_created"
        assert data["events"][0]["agent"] == "backend_test"
    finally:
        app.dependency_overrides.pop(db.get_db, None)
