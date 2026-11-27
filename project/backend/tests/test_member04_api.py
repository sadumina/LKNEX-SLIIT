"""Automated tests for Member 04 FastAPI endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_verify_supervisor_not_ready():
    response = client.post(
        "/api/verify",
        json={
            "question": "What is AI?",
            "draft_answer": "AI means artificial intelligence.",
            "mode": "multi_agent",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Verification supervisor is not integrated yet."
    )


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


def test_prepared_verify_requires_api_key(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    response = client.post(
        "/api/verify/prepared",
        json={
            "question": "What leave is available?",
            "draft_answer": "Staff receive annual leave.",
            "claims": [
                {
                    "claim_id": "C1",
                    "claim_text": "Staff receive annual leave."
                }
            ],
            "evidence_chunks": []
        },
    )

    assert response.status_code == 401


def test_prepared_verify_rejects_reviewer(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    response = client.post(
        "/api/verify/prepared",
        headers={"X-API-Key": "test-reviewer-key"},
        json={
            "question": "What leave is available?",
            "draft_answer": "Staff receive annual leave.",
            "claims": [
                {
                    "claim_id": "C1",
                    "claim_text": "Staff receive annual leave."
                }
            ],
            "evidence_chunks": []
        },
    )

    assert response.status_code == 403


def test_prepared_verify_rejects_empty_claims(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    response = client.post(
        "/api/verify/prepared",
        headers={"X-API-Key": "test-admin-key"},
        json={
            "question": "What leave is available?",
            "draft_answer": "Staff receive annual leave.",
            "claims": [],
            "evidence_chunks": []
        },
    )

    assert response.status_code == 422


def test_prepared_verify_saves_result(monkeypatch, tmp_path):
    from app.database import db
    from app.agents.fact_verification import FactVerificationAgent
    from app.orchestration.workflow import build_post_retrieval_graph
    from app.services.verification_service import VerificationService
    from app.schemas.verification import FactVerificationDecision, Verdict
    from app.api.routes import verify

    monkeypatch.setenv("AEGIS_API_KEY", "test-admin-key")
    monkeypatch.setenv("AEGIS_REVIEWER_API_KEY", "test-reviewer-key")

    def fake_llm(system, user, schema, **kwargs):
        return FactVerificationDecision(
            verdict=Verdict.SUPPORTED,
            explanation="Active evidence supports the claim.",
        )

    def create_test_service(connection):
        graph = build_post_retrieval_graph(
            fact_agent=FactVerificationAgent(llm_client=fake_llm)
        )
        return VerificationService(connection, graph=graph)

    monkeypatch.setattr(
        verify, "VerificationService", create_test_service
    )

    test_db = tmp_path / "prepared_verify.sqlite3"

    def get_test_db():
        connection = db.connect(str(test_db))
        db.init_db(connection)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[db.get_db] = get_test_db

    headers = {"X-API-Key": "test-admin-key"}

    try:
        response = client.post(
            "/api/verify/prepared",
            headers=headers,
            json={
                "question": "What leave is available?",
                "draft_answer": "Staff receive annual leave.",
                "claims": [
                    {
                        "claim_id": "C1",
                        "claim_text": "Staff receive annual leave."
                    }
                ],
                "evidence_chunks": [
                    {
                        "chunk_id": "HR_POL_001-S02",
                        "text": "Staff receive annual leave.",
                        "document_id": "HR_POL_001",
                        "section_id": "HR_POL_001-S02",
                        "page": 1,
                        "document_version": "2.0",
                        "document_status": "ACTIVE",
                        "effective_date": "2026-09-01",
                        "policy_topic": "annual_leave"
                    }
                ]
            },
        )

        assert response.status_code == 200

        result = response.json()

        assert result["action"] == "approve"
        assert result["verification"]["supported_count"] == 1
        assert result["security"]["overall_risk"] == "low"

        run_id = result["run_id"]

        audit = client.get(
            f"/api/audit/runs/{run_id}",
            headers=headers,
        )

        assert audit.status_code == 200

        data = audit.json()

        assert data["run"]["status"] == "completed"
        assert data["run"]["action"] == "approve"
        assert len(data["claims"]) == 1

        events = [event["event"] for event in data["events"]]

        assert "workflow_started" in events
        assert "workflow_completed" in events

    finally:
        app.dependency_overrides.pop(db.get_db, None)
