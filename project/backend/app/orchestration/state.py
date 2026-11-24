# Purpose of this file is to define the shared state passed between all agents and to document which component owns each key

from typing import Any, Dict, List, Optional

from app.schemas.verification import Claim, ClaimVerdict, EvidenceChunk, VerificationResult


class AgentState(Dict[str, Any]):
    """
    Shared workflow state passed between all agents.

    Key ownership:
    - question: Supervisor (input)
    - draft_answer: Draft Chatbot / Claim Extraction (input)
    - claims: Claim Extraction Agent (output) -> Fact Verification Agent (input)
    - evidence_chunks: Evidence Retrieval Agent (output) -> Fact Verification Agent (input)
    - claim_verdicts: Fact Verification Agent (output) -> Supervisor (input)
    - verification_result: Fact Verification Agent (output) -> Policy Decision Engine (input)
    - security_report: Security & Risk Assessment Agent (output) -> Supervisor (input)
    - final_action: Policy Decision Engine (output)
    - final_answer: Correction Module (output)
    - run_id: Supervisor (input/output)
    - user_role: Supervisor (input)
    - mode: Supervisor (input)
    - error: Any agent (output on failure)
    - retry_count: Supervisor (input/output)
    """

    # Required keys
    question: str
    user_role: str
    mode: str
    run_id: str

    # Agent inputs/outputs
    draft_answer: Optional[str]
    claims: Optional[List[Claim]]
    evidence_chunks: Optional[List[EvidenceChunk]]
    claim_verdicts: Optional[List[ClaimVerdict]]
    verification_result: Optional[VerificationResult]
    security_report: Optional[Dict[str, Any]]
    final_action: Optional[str]
    final_answer: Optional[str]

    # Control
    error: Optional[str]
    retry_count: int


def initial_state(
    *,
    question: str,
    user_role: str,
    mode: str = "multi_agent",
    run_id: Optional[str] = None,
    draft_answer: Optional[str] = None,
) -> AgentState:
    """Create a fresh AgentState for a new verification request."""
    import uuid

    return AgentState(
        question=question,
        user_role=user_role,
        mode=mode,
        run_id=run_id or uuid.uuid4().hex,
        draft_answer=draft_answer,
        claims=None,
        evidence_chunks=None,
        claim_verdicts=None,
        verification_result=None,
        security_report=None,
        final_action=None,
        final_answer=None,
        error=None,
        retry_count=0,
    )
