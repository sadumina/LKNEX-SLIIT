# Purpose of this file is to build the LangGraph workflow connecting the agents, the parallel security check and the correction loop

"""Composable workflow stages used while the complete supervisor graph is built."""

from langgraph.graph import END, START, StateGraph

from app.agents.fact_verification import FactVerificationAgent, run as run_fact_verification
from app.agents.security_assessment import (
    SecurityAssessmentAgent,
    run as run_security_assessment,
)
from app.decision.policy_engine import PolicyDecisionEngine, run as run_policy_decision
from app.orchestration.routing import route_policy_decision
from app.orchestration.state import AgentState
from app.schemas.decision import FinalAction


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


def _approve_node(state: AgentState) -> dict:
    security_report = state.get("security_report")
    safe_answer = (
        security_report.redacted_draft_answer
        if security_report is not None
        else state.get("draft_answer")
    )
    return {"current_node": "approved", "final_answer": safe_answer}


def _correct_node(state: AgentState) -> dict:
    """Mark correction as pending; the bounded correction loop is added next."""
    return {"current_node": "correction_pending", "final_answer": None}


def _block_node(state: AgentState) -> dict:
    return {"current_node": "blocked", "final_answer": None}


def _human_review_node(state: AgentState) -> dict:
    return {"current_node": "human_review", "final_answer": None}


def build_post_retrieval_graph(
    *,
    fact_agent: FactVerificationAgent | None = None,
    security_agent: SecurityAssessmentAgent | None = None,
    policy_engine: PolicyDecisionEngine | None = None,
):
    """Compile the first executable LangGraph verification subgraph.

    The graph starts after Claim Extraction and Evidence Retrieval have populated
    shared state. The ``correct`` route intentionally terminates as
    ``correction_pending`` until the bounded correction module is implemented.
    """
    graph = StateGraph(AgentState)

    def fact_node(state: AgentState) -> dict:
        update = run_fact_verification(state, agent=fact_agent)
        update["current_node"] = "fact_verification"
        return update

    def security_node(state: AgentState) -> dict:
        update = run_security_assessment(state, agent=security_agent)
        update["current_node"] = "security_assessment"
        return update

    def policy_node(state: AgentState) -> dict:
        update = run_policy_decision(state, engine=policy_engine)
        update["current_node"] = "policy_decision"
        return update

    graph.add_node("fact_verification", fact_node)
    graph.add_node("security_assessment", security_node)
    graph.add_node("policy_decision", policy_node)
    graph.add_node(FinalAction.APPROVE.value, _approve_node)
    graph.add_node(FinalAction.CORRECT.value, _correct_node)
    graph.add_node(FinalAction.BLOCK.value, _block_node)
    graph.add_node(FinalAction.HUMAN_REVIEW.value, _human_review_node)

    graph.add_edge(START, "fact_verification")
    graph.add_edge("fact_verification", "security_assessment")
    graph.add_edge("security_assessment", "policy_decision")
    graph.add_conditional_edges(
        "policy_decision",
        route_policy_decision,
        {
            action.value: action.value
            for action in FinalAction
        },
    )
    for action in FinalAction:
        graph.add_edge(action.value, END)

    return graph.compile()
