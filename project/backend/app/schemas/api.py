"""Request and response models for the AEGIS AI API."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.decision import FinalAction
from app.schemas.verification import RiskLevel, SecurityFinding, Verdict


class VerifyRequest(BaseModel):
    question: str = Field(min_length=1)
    draft_answer: str = Field(min_length=1)
    user_role: str = Field(default="employee", min_length=1)
    mode: Literal["multi_agent", "single_agent", "passthrough"] = "multi_agent"


class VerifyResponse(BaseModel):
    status: str
    message: str
    run_id: str | None = None


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    section_id: Optional[str] = None
    page: int
    document_version: str


class ClaimDecisionResponse(BaseModel):
    claim_id: str
    verdict: Verdict
    explanation: str
    citations: List[CitationResponse] = Field(default_factory=list)


class VerificationSummaryResponse(BaseModel):
    overall_status: str
    total_claims: int
    supported_count: int
    contradicted_count: int
    insufficient_count: int
    claims: List[ClaimDecisionResponse] = Field(default_factory=list)


class SecuritySummaryResponse(BaseModel):
    overall_risk: RiskLevel
    recommended_action: str
    findings: List[SecurityFinding] = Field(default_factory=list)


class WorkflowResultResponse(BaseModel):
    """Frontend-safe result returned by the verification service."""

    run_id: str
    action: FinalAction
    decision_reason: str
    final_answer: Optional[str] = None
    verification: VerificationSummaryResponse
    security: SecuritySummaryResponse
    latency_ms: int
    llm_calls: int
