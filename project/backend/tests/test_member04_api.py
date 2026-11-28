"""Automated tests for Member 04 FastAPI endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_verify_runs_complete_pipeline(monkeypatch):
    from app.services.verification_service import VerificationService

    monkeypatch.setattr(
        VerificationService,
        "verify_complete",
        lambda self, **kwargs: {
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
        },
    )
    response = client.post(
        "/api/verify",
        json={
            "question": "What is AI?",
            "draft_answer": "AI means artificial intelligence.",
            "user_role": "employee",
            "mode": "multi_agent",
        },
    )

    assert response.status_code == 200
    assert response.json()["action"] == "approve"
    assert response.json()["run_id"] == "test-run"


def test_verify_rejects_missing_question():
    response = client.post(
        "/api/verify",
        json={
            "draft_answer": "AI means artificial intelligence.",
            "mode": "multi_agent",
        },
    )

    assert response.status_code == 422


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
