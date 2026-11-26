# Purpose of this file is to hold the conditional routing rules that decide which step runs next

"""Conditional routing functions for the LangGraph supervisor."""

from app.schemas.decision import FinalAction


def route_policy_decision(state: dict) -> str:
    """Return a safe graph route for the current policy decision."""
    action = state.get("final_action")
    if action is None and state.get("policy_decision") is not None:
        action = state["policy_decision"].action

    try:
        return FinalAction(action).value
    except (TypeError, ValueError):
        # Missing or invalid policy output must never release the response.
        return FinalAction.HUMAN_REVIEW.value


def route_correction_result(state: dict) -> str:
    """Re-verify successful corrections or route failures to policy handling."""
    error = state.get("workflow_error")
    if error is not None and error.node == "correction":
        return "failed"
    return "reverify"
