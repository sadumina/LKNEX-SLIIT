"""Validation tests for Policy Engine and Supervisor control contracts."""

import pytest
from pydantic import ValidationError

from app.orchestration.state import initial_state
from app.schemas.decision import (
    CorrectionStatus,
    FinalAction,
    PolicyDecision,
    WorkflowError,
)


@pytest.mark.parametrize("action", list(FinalAction))
def test_policy_decision_accepts_every_supported_action(action):
    decision = PolicyDecision(
        action=action,
        reason="Deterministic policy rule matched.",
        requires_human_review=action == FinalAction.HUMAN_REVIEW,
    )

    assert decision.action == action


def test_policy_decision_rejects_unknown_action():
    with pytest.raises(ValidationError):
        PolicyDecision(action="release_anyway", reason="Invalid action")


def test_policy_decision_requires_reason():
    with pytest.raises(ValidationError):
        PolicyDecision(action=FinalAction.APPROVE, reason="")


def test_workflow_error_validates_attempt_count():
    with pytest.raises(ValidationError):
        WorkflowError(node="fact_verification", message="Provider failed", attempts=0)


def test_correction_status_is_bounded():
    status = CorrectionStatus(attempts=0, max_attempts=1)

    assert status.can_retry is True
    assert CorrectionStatus(attempts=1, max_attempts=1).can_retry is False
    with pytest.raises(ValidationError):
        CorrectionStatus(attempts=2, max_attempts=1)


def test_initial_state_contains_typed_orchestration_defaults():
    state = initial_state(question="What is the policy?", user_role="employee")

    assert state["policy_decision"] is None
    assert state["final_action"] is None
    assert state["workflow_error"] is None
    assert state["correction_status"] == CorrectionStatus()
    assert state["current_node"] is None
