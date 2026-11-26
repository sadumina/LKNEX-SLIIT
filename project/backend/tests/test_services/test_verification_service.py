"""SQLite integration tests for the prepared verification service."""

import pytest

from app.agents.fact_verification import FactVerificationAgent
from app.database import db
from app.orchestration.workflow import build_post_retrieval_graph
from app.schemas.decision import FinalAction
from app.schemas.verification import (
    Claim,
    EvidenceChunk,
    FactVerificationDecision,
    RiskLevel,
    Verdict,
)
from app.services.verification_service import VerificationService


class _StructuredVerifier:
    def __call__(self, system, user, schema, **kwargs):
        return FactVerificationDecision(
            verdict=Verdict.SUPPORTED,
            explanation="Active evidence supports the claim.",
        )


def _claim() -> Claim:
    return Claim(claim_id="C1", claim_text="Staff receive annual leave.")


def _evidence() -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id="HR_POL_001-S02",
        text="Staff receive annual leave.",
        document_id="HR_POL_001",
        section_id="HR_POL_001-S02",
        page=1,
        document_version="2.0",
        document_status="ACTIVE",
        effective_date="2026-09-01",
        policy_topic="annual_leave",
    )


@pytest.fixture
def connection():
    conn = db.connect(":memory:")
    yield conn
    conn.close()


def test_service_persists_approved_workflow_and_frontend_safe_response(connection):
    graph = build_post_retrieval_graph(
        fact_agent=FactVerificationAgent(llm_client=_StructuredVerifier())
    )
    service = VerificationService(connection, graph=graph)

    response = service.verify_prepared(
        question="What leave is available?",
        draft_answer="Staff receive annual leave.",
        user_role="employee",
        claims=[_claim()],
        evidence_chunks=[_evidence()],
    )

    assert response.action == FinalAction.APPROVE
    assert response.final_answer == "Staff receive annual leave."
    assert response.verification.claims[0].citations[0].chunk_id == "HR_POL_001-S02"
    assert response.security.overall_risk == RiskLevel.LOW

    saved_run = db.get_run(connection, response.run_id)
    assert saved_run["status"] == "completed"
    assert saved_run["action"] == "approve"
    assert saved_run["risk_level"] == "low"
    assert db.get_claim_results(connection, response.run_id)[0]["verdict"] == "supported"
    assert [event["event"] for event in db.get_audit_trail(connection, response.run_id)] == [
        "workflow_started",
        "verification_completed",
        "security_completed",
        "decision_created",
        "workflow_completed",
    ]


def test_service_creates_human_review_for_insufficient_evidence(connection):
    service = VerificationService(connection, graph=build_post_retrieval_graph())

    response = service.verify_prepared(
        question="What leave is available?",
        draft_answer="Staff receive an unknown allowance.",
        user_role="employee",
        claims=[Claim(claim_id="C1", claim_text="Staff receive an unknown allowance.")],
        evidence_chunks=[],
    )

    assert response.action == FinalAction.HUMAN_REVIEW
    assert response.final_answer is None
    assert db.get_claim_results(connection, response.run_id)[0]["verdict"] == "unsupported"
    pending = db.list_pending_reviews(connection)
    assert len(pending) == 1
    assert pending[0]["run_id"] == response.run_id


def test_service_marks_run_failed_when_graph_raises(connection):
    class BrokenGraph:
        def invoke(self, state):
            raise RuntimeError("Unexpected graph failure")

    service = VerificationService(connection, graph=BrokenGraph())

    with pytest.raises(RuntimeError, match="Unexpected graph failure"):
        service.verify_prepared(
            question="Question",
            draft_answer="Draft",
            user_role="employee",
            claims=[_claim()],
            evidence_chunks=[_evidence()],
        )

    runs = db.list_runs(connection)
    assert runs[0]["status"] == "failed"
    assert db.get_audit_trail(connection, runs[0]["run_id"])[-1]["event"] == "run_failed"
