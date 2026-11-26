"""Decision-table tests for the deterministic Policy Engine."""

import pytest

from app.decision.policy_engine import PolicyDecisionEngine, run
from app.schemas.decision import CorrectionStatus, FinalAction, WorkflowError
from app.schemas.verification import RiskLevel, SecurityReport, VerificationResult


def _security(risk: RiskLevel) -> SecurityReport:
    return SecurityReport(
        findings=[],
        overall_risk=risk,
        scanned_sources=1,
        recommended_action={
            RiskLevel.LOW: "approve",
            RiskLevel.MEDIUM: "human_review",
            RiskLevel.HIGH: "block",
        }[risk],
        redacted_draft_answer="Safe answer.",
    )


def _verification(
    *,
    total: int,
    supported: int = 0,
    contradicted: int = 0,
    insufficient: int = 0,
) -> VerificationResult:
    return VerificationResult(
        claim_verdicts=[],
        overall_status="test_status",
        total_claims=total,
        supported_count=supported,
        contradicted_count=contradicted,
        insufficient_count=insufficient,
    )


@pytest.mark.parametrize(
    ("risk", "verification", "correction", "expected"),
    [
        (RiskLevel.HIGH, _verification(total=1, supported=1), CorrectionStatus(), FinalAction.BLOCK),
        (
            RiskLevel.MEDIUM,
            _verification(total=1, supported=1),
            CorrectionStatus(),
            FinalAction.HUMAN_REVIEW,
        ),
        (
            RiskLevel.LOW,
            _verification(total=1, contradicted=1),
            CorrectionStatus(attempts=0, max_attempts=1),
            FinalAction.CORRECT,
        ),
        (
            RiskLevel.LOW,
            _verification(total=1, contradicted=1),
            CorrectionStatus(attempts=1, max_attempts=1),
            FinalAction.HUMAN_REVIEW,
        ),
        (
            RiskLevel.LOW,
            _verification(total=1, insufficient=1),
            CorrectionStatus(),
            FinalAction.HUMAN_REVIEW,
        ),
        (
            RiskLevel.LOW,
            _verification(total=1, supported=1),
            CorrectionStatus(),
            FinalAction.APPROVE,
        ),
        (
            RiskLevel.LOW,
            _verification(total=0),
            CorrectionStatus(),
            FinalAction.APPROVE,
        ),
    ],
)
def test_policy_decision_table(risk, verification, correction, expected):
    decision = PolicyDecisionEngine().decide(
        verification_result=verification,
        security_report=_security(risk),
        correction_status=correction,
    )

    assert decision.action == expected
    assert decision.requires_human_review is (expected == FinalAction.HUMAN_REVIEW)


def test_high_security_risk_overrides_workflow_error_and_fact_result():
    decision = PolicyDecisionEngine().decide(
        verification_result=_verification(total=1, contradicted=1),
        security_report=_security(RiskLevel.HIGH),
        workflow_error=WorkflowError(
            node="fact_verification",
            message="Provider failed",
            attempts=2,
        ),
    )

    assert decision.action == FinalAction.BLOCK


def test_unresolved_workflow_error_routes_to_human_review():
    decision = PolicyDecisionEngine().decide(
        verification_result=None,
        security_report=_security(RiskLevel.LOW),
        workflow_error=WorkflowError(
            node="evidence_retrieval",
            message="Vector store unavailable",
            retryable=True,
            attempts=2,
        ),
    )

    assert decision.action == FinalAction.HUMAN_REVIEW
    assert decision.requires_human_review is True


@pytest.mark.parametrize(
    ("verification", "security", "reason_fragment"),
    [
        (None, _security(RiskLevel.LOW), "Fact verification"),
        (_verification(total=1, supported=1), None, "Security assessment"),
    ],
)
def test_missing_required_agent_output_fails_closed(verification, security, reason_fragment):
    decision = PolicyDecisionEngine().decide(
        verification_result=verification,
        security_report=security,
    )

    assert decision.action == FinalAction.HUMAN_REVIEW
    assert reason_fragment in decision.reason


def test_inconsistent_verification_aggregate_routes_to_human_review():
    decision = PolicyDecisionEngine().decide(
        verification_result=_verification(total=2, supported=1),
        security_report=_security(RiskLevel.LOW),
    )

    assert decision.action == FinalAction.HUMAN_REVIEW


def test_policy_workflow_node_returns_typed_decision_and_action():
    update = run(
        {
            "verification_result": _verification(total=1, supported=1),
            "security_report": _security(RiskLevel.LOW),
            "workflow_error": None,
            "correction_status": CorrectionStatus(),
        }
    )

    assert update["policy_decision"].action == FinalAction.APPROVE
    assert update["final_action"] == FinalAction.APPROVE
