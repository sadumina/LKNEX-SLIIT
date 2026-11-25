# Purpose of this file is to define the models for claims, evidence chunks, claim verdicts and security reports

from typing import Literal
from pydantic import BaseModel, Field


class UserContext(BaseModel):
    user_id: str
    role: str


# Claim Extraction output
class ExtractedClaim(BaseModel):
    text: str = Field(
        description="One self-contained factual statement. Numbers, units and dates exactly as written."
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Named organisations, products, documents, roles or places mentioned in the claim.",
    )
    negated: bool = Field(
        default=False,
        description="True if the claim asserts that something is NOT the case.",
    )


class ExtractionResult(BaseModel):
    """The structured output returned by the LLM."""

    claims: list[ExtractedClaim]


class Claim(ExtractedClaim):
    """A validates claim as it travels through the pipeline."""

    id: str
    numbers: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)


# Evidence Retrieval output
class EvidenceChunk(BaseModel):
    """One passage of a trusted document returned as evidence for a claim."""

    chunk_id: str
    doc_id: str
    doc_title: str
    version: str
    page: int
    section: str | None = None
    status: Literal["current", "superseded"]
    effective_date: str | None = None
    text: str
    score: float
