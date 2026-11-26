# Purpose of this file is to build the LangGraph workflow connecting the agents, the parallel security check and the correction loop

"""Composable workflow stages used while the complete supervisor graph is built."""

from app.agents.fact_verification import FactVerificationAgent, run as run_fact_verification
from app.agents.security_assessment import (
    SecurityAssessmentAgent,
    run as run_security_assessment,
)
from app.orchestration.state import AgentState


def run_post_retrieval_checks(
    state: AgentState | dict,
    *,
    fact_agent: FactVerificationAgent | None = None,
    security_agent: SecurityAssessmentAgent | None = None,
) -> AgentState:
    """Run the two agent checks that consume retrieved evidence.

    Evidence Retrieval remains responsible for populating ``claims`` and
    ``evidence_chunks``. This stage preserves the incoming state and adds Fact
    Verification and Security Assessment outputs. It can later be wrapped as a
    LangGraph node or replaced by parallel graph branches without changing the
    agent interfaces.
    """
    updated_state = AgentState(state.copy())
    updated_state.update(run_fact_verification(updated_state, agent=fact_agent))
    updated_state.update(run_security_assessment(updated_state, agent=security_agent))
    return updated_state
