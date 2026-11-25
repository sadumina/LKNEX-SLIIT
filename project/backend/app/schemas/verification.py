# Purpose of this file is to define the models for claims, evidence chunks, claim verdicts and security reports

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Claim(BaseModel):
    """An atomic factual claim extracted from an AI-generated response."""
    claim_id: str = Field(..., description="Unique identifier for the claim")
    claim_text: str = Field(..., description="The factual statement to verify")
    entities: Optional[List[str]] = Field(default=None, description="Named entities mentioned in the claim")
    dates: Optional[List[str]] = Field(default=None, description="Date references in the claim")
    numbers: Optional[List[str]] = Field(default=None, description="Numeric values in the claim")
    negated: bool = Field(default=False, description="Whether the claim contains factual negation")


class ExtractedClaim(BaseModel):
    """Minimal structured claim returned by the claim-extraction LLM."""

    text: str = Field(..., min_length=1, description="Atomic factual statement")
    entities: List[str] = Field(default_factory=list, description="Named entities in the statement")
    negated: bool = Field(default=False, description="Whether the statement is negated")


class ExtractionResult(BaseModel):
    """Validated LLM output before deterministic claim finalisation."""

    claims: List[ExtractedClaim] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    """A passage of evidence retrieved from a trusted organisational document."""
    chunk_id: str = Field(..., description="Unique identifier for the evidence chunk")
    text: str = Field(..., description="The evidence text")
    document_id: str = Field(..., description="Source document ID (e.g., HR_POL_001)")
    section_id: str = Field(..., description="Source section ID (e.g., HR_POL_001-S02)")
    page: int = Field(..., description="Page number in the source document")
    document_version: str = Field(..., description="Document version (e.g., 2.0)")
    document_status: str = Field(..., description="ACTIVE or SUPERSEDED")
    effective_date: str = Field(..., description="Effective date of the document")
    policy_topic: str = Field(..., description="Policy topic category")
    relevance_score: Optional[float] = Field(default=None, description="Semantic similarity score")


class ClaimVerdict(BaseModel):
    """The verification result for a single claim."""
    claim_id: str = Field(..., description="Reference to the original claim")
    verdict: Verdict = Field(..., description="SUPPORTED, CONTRADICTED, or INSUFFICIENT_EVIDENCE")
    explanation: str = Field(..., description="Reasoning for the classification")
    source_references: List[EvidenceChunk] = Field(default_factory=list, description="Evidence chunks used")


class VerificationResult(BaseModel):
    """Aggregated verification output for all claims in a response."""
    claim_verdicts: List[ClaimVerdict] = Field(default_factory=list)
    overall_status: str = Field(..., description="e.g., all_supported, partially_supported, all_contradicted")
    total_claims: int = Field(..., description="Number of claims verified")
    supported_count: int = Field(..., description="Count of SUPPORTED verdicts")
    contradicted_count: int = Field(..., description="Count of CONTRADICTED verdicts")
    insufficient_count: int = Field(..., description="Count of INSUFFICIENT_EVIDENCE verdicts")
