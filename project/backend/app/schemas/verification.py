# Purpose of this file is to define the models for claims, evidence chunks, claim verdicts and security reports

from enum import Enum
from typing import List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class UserContext(BaseModel):
    """Authenticated user information passed through the verification pipeline."""

    user_id: str
    role: str


class Verdict(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class FactVerificationDecision(BaseModel):
    """Validated semantic-verification response returned by an LLM provider."""

    verdict: Verdict
    explanation: str = Field(..., min_length=1)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SecurityFindingType(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    SENSITIVE_INFORMATION = "sensitive_information"


class SecuritySource(str, Enum):
    DRAFT_ANSWER = "draft_answer"
    EVIDENCE = "evidence"


class Claim(BaseModel):
    """An atomic claim supporting both pipeline field-name conventions."""

    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(
        ...,
        validation_alias=AliasChoices("claim_id", "id"),
        description="Unique identifier for the claim",
    )
    claim_text: str = Field(
        ...,
        validation_alias=AliasChoices("claim_text", "text"),
        description="The factual statement to verify",
    )
    entities: List[str] = Field(default_factory=list, description="Named entities mentioned in the claim")
    dates: List[str] = Field(default_factory=list, description="Date references in the claim")
    numbers: List[str] = Field(default_factory=list, description="Numeric values in the claim")
    negated: bool = Field(default=False, description="Whether the claim contains factual negation")

    @property
    def id(self) -> str:
        """Incoming member-compatible alias for ``claim_id``."""
        return self.claim_id

    @property
    def text(self) -> str:
        """Incoming member-compatible alias for ``claim_text``."""
        return self.claim_text


class ExtractedClaim(BaseModel):
    """Minimal structured claim returned by the claim-extraction LLM."""

    text: str = Field(..., min_length=1, description="Atomic factual statement")
    entities: List[str] = Field(default_factory=list, description="Named entities in the statement")
    negated: bool = Field(default=False, description="Whether the statement is negated")


class ExtractionResult(BaseModel):
    """Validated LLM output before deterministic claim finalisation."""

    claims: List[ExtractedClaim] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    """Evidence passage supporting both retrieval and verification names."""

    model_config = ConfigDict(populate_by_name=True)

    chunk_id: str = Field(..., description="Unique identifier for the evidence chunk")
    text: str = Field(..., description="The evidence text")
    document_id: str = Field(
        ...,
        validation_alias=AliasChoices("document_id", "doc_id"),
        description="Source document ID (e.g., HR_POL_001)",
    )
    doc_title: Optional[str] = Field(default=None, description="Human-readable document title")
    section_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("section_id", "section"),
        description="Source section ID (e.g., HR_POL_001-S02)",
    )
    page: int = Field(..., description="Page number in the source document")
    document_version: str = Field(
        ...,
        validation_alias=AliasChoices("document_version", "version"),
        description="Document version (e.g., 2.0)",
    )
    document_status: str = Field(
        ...,
        validation_alias=AliasChoices("document_status", "status"),
        description="ACTIVE or SUPERSEDED",
    )
    effective_date: Optional[str] = Field(default=None, description="Effective date of the document")
    policy_topic: str = Field(default="unknown", description="Policy topic category")
    relevance_score: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("relevance_score", "score"),
        description="Semantic similarity score",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_document_status(cls, values):
        """Normalize retrieval status values to the verification convention."""
        if isinstance(values, dict):
            values = dict(values)
            status_key = "document_status" if "document_status" in values else "status"
            if status_key in values and isinstance(values[status_key], str):
                status = values[status_key].strip().upper()
                values[status_key] = {
                    "CURRENT": "ACTIVE",
                    "ACTIVE": "ACTIVE",
                    "SUPERSEDED": "SUPERSEDED",
                }.get(status, status)
        return values

    @property
    def doc_id(self) -> str:
        return self.document_id

    @property
    def version(self) -> str:
        return self.document_version

    @property
    def section(self) -> Optional[str]:
        return self.section_id

    @property
    def status(self) -> str:
        return "current" if self.document_status == "ACTIVE" else self.document_status.lower()

    @property
    def score(self) -> Optional[float]:
        return self.relevance_score


class SecurityFinding(BaseModel):
    """A security concern detected without exposing the matched sensitive value."""

    finding_type: SecurityFindingType
    severity: RiskLevel
    source: SecuritySource
    source_id: str = Field(..., description="draft_answer or the evidence chunk ID")
    rule_id: str = Field(..., description="Stable identifier for the matched detector")
    description: str
    detected_in_encoded_content: bool = Field(
        default=False, description="Whether the finding was detected after safe decoding"
    )


class SecurityReport(BaseModel):
    """Aggregated output from the Security and Risk Assessment Agent."""

    findings: List[SecurityFinding] = Field(default_factory=list)
    overall_risk: RiskLevel
    scanned_sources: int = Field(..., ge=0)
    recommended_action: str = Field(..., description="approve, human_review, or block")
    redacted_draft_answer: str = Field(
        ..., description="Draft answer with supported sensitive values masked"
    )


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
