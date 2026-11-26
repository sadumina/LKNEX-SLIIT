# Purpose of this file is to apply rule-based policies to verification and security results and choose approve, correct, block or human review

"""Deterministic policy rules for final workflow routing."""

from app.schemas.decision import (
    CorrectionStatus,
    FinalAction,
    PolicyDecision,
    WorkflowError,
)
from app.schemas.verification import RiskLevel, SecurityReport, VerificationResult


class PolicyDecisionEngine:
    """Select one final action without using an LLM."""

    def decide(
        self,
        *,
        verification_result: VerificationResult | None,
        security_report: SecurityReport | None,
        workflow_error: WorkflowError | None = None,
        correction_status: CorrectionStatus | None = None,
    ) -> PolicyDecision:
        correction_status = correction_status or CorrectionStatus()

        # A known high-risk security finding always takes precedence, even if
        # another node also failed or factual verification is incomplete.
        if security_report is not None and security_report.overall_risk == RiskLevel.HIGH:
            return PolicyDecision(
                action=FinalAction.BLOCK,
                reason="High security risk detected; response release is blocked.",
            )

        if workflow_error is not None:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                reason=(
                    f"Workflow node {workflow_error.node} failed after "
                    f"{workflow_error.attempts} attempt(s)."
                ),
                requires_human_review=True,
            )

        if security_report is None:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                reason="Security assessment is unavailable.",
                requires_human_review=True,
            )

        if security_report.overall_risk == RiskLevel.MEDIUM:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                reason="Medium security risk requires authorised human review.",
                requires_human_review=True,
            )

        if verification_result is None:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                reason="Fact verification result is unavailable.",
                requires_human_review=True,
            )

        if verification_result.contradicted_count > 0:
            if correction_status.can_retry:
                return PolicyDecision(
                    action=FinalAction.CORRECT,
                    reason="One or more claims contradict active evidence.",
                )
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                reason="Contradicted claims remain after the correction limit was reached.",
                requires_human_review=True,
            )

        if verification_result.insufficient_count > 0:
            return PolicyDecision(
                action=FinalAction.HUMAN_REVIEW,
                reason="One or more claims lack sufficient trusted evidence.",
                requires_human_review=True,
            )

        if verification_result.total_claims == 0:
            return PolicyDecision(
                action=FinalAction.APPROVE,
                reason="No factual claims require verification and security risk is low.",
            )

        if verification_result.supported_count == verification_result.total_claims:
            return PolicyDecision(
                action=FinalAction.APPROVE,
                reason="All factual claims are supported and security risk is low.",
            )

        return PolicyDecision(
            action=FinalAction.HUMAN_REVIEW,
            reason="Verification aggregates are inconsistent or incomplete.",
            requires_human_review=True,
        )


def run(state: dict, engine: PolicyDecisionEngine | None = None) -> dict:
    """Run the Policy Engine as a workflow node and return state updates."""
    policy_engine = engine or PolicyDecisionEngine()
    decision = policy_engine.decide(
        verification_result=state.get("verification_result"),
        security_report=state.get("security_report"),
        workflow_error=state.get("workflow_error"),
        correction_status=state.get("correction_status"),
    )
    return {
        "policy_decision": decision,
        "final_action": decision.action,
    }
