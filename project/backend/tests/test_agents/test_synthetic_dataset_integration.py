"""Integration checks using the repository's synthetic organisational dataset."""

import json
from pathlib import Path

import pytest

from app.agents.fact_verification import FactVerificationAgent
from app.agents.security_assessment import SecurityAssessmentAgent
from app.schemas.verification import Claim, EvidenceChunk, RiskLevel, Verdict


DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "synthetic"
    / "organisational_documents.json"
)


class _SupportedLLM:
    def complete(self, prompt, temperature=0.0):
        return '{"verdict": "SUPPORTED", "explanation": "Matches active policy evidence."}'


def _load_documents() -> list[dict]:
    if not DATASET_PATH.exists():
        pytest.skip("Synthetic organisational dataset is not available.")
    with DATASET_PATH.open(encoding="utf-8") as dataset_file:
        return json.load(dataset_file)


def _evidence_from_section(document: dict, section: dict) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=section["section_id"],
        text=section["text"],
        document_id=document["document_id"],
        section_id=section["section_id"],
        page=section["page"],
        document_version=document["document_version"],
        document_status=document["document_status"],
        effective_date=document["effective_date"],
        policy_topic=document["policy_topic"],
    )


def test_all_synthetic_policy_documents_avoid_security_false_positives():
    documents = _load_documents()
    evidence = [
        _evidence_from_section(document, section)
        for document in documents
        for section in document["sections"]
    ]

    report = SecurityAssessmentAgent().assess("", evidence)

    assert len(documents) == 50
    assert report.overall_risk == RiskLevel.LOW
    assert report.findings == []
    assert report.scanned_sources == len(evidence) + 1


def test_fact_verification_uses_active_policy_not_superseded_version():
    documents = _load_documents()
    annual_leave_documents = [
        document for document in documents if document["policy_topic"] == "annual_leave"
    ]
    evidence = [
        _evidence_from_section(document, document["sections"][1])
        for document in annual_leave_documents
    ]
    claim = Claim(
        claim_id="C1",
        claim_text="Full-time staff receive 21 paid annual leave days per calendar year.",
        numbers=["21 days"],
    )

    result = FactVerificationAgent(llm_client=_SupportedLLM()).verify([claim], evidence)

    assert result.claim_verdicts[0].verdict == Verdict.SUPPORTED
    assert result.claim_verdicts[0].source_references
    assert all(
        source.document_status == "ACTIVE"
        for source in result.claim_verdicts[0].source_references
    )
    assert all(
        source.document_id != "HR_POL_009"
        for source in result.claim_verdicts[0].source_references
    )
