# Purpose of this file is to test that fact verification labels claims correctly, including wrong numbers and dates

import pytest

from app.agents.fact_verification import FactVerificationAgent, run
from app.schemas.verification import Claim, EvidenceChunk, Verdict


class FakeLLM:
    """Stub LLM that returns canned JSON responses for verification prompts."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def complete(self, prompt, temperature=0.0):
        self.calls.append(prompt)
        return self.responses.pop(0)


class FakeVectorStore:
    """Stub vector store - not used directly in these tests since evidence is passed in."""


def _make_claim(claim_id, text, entities=None, dates=None, numbers=None):
    return Claim(
        claim_id=claim_id,
        claim_text=text,
        entities=entities or [],
        dates=dates or [],
        numbers=numbers or [],
    )


def _make_evidence(chunk_id, text, document_id, section_id, page=1, version="1.0", status="ACTIVE"):
    return EvidenceChunk(
        chunk_id=chunk_id,
        text=text,
        document_id=document_id,
        section_id=section_id,
        page=page,
        document_version=version,
        document_status=status,
        effective_date="2026-01-01",
        policy_topic="annual_leave",
    )


# ------------------------------------------------------------------
# SUPPORTED
# ------------------------------------------------------------------
def test_supported_when_evidence_agrees():
    llm = FakeLLM([
        '{"verdict": "SUPPORTED", "explanation": "The policy states 21 days, matching the claim."}'
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())

    claims = [_make_claim("C1", "Full-time staff receive 21 paid annual leave days per calendar year.",
                          numbers=["21"])]
    evidence = [_make_evidence("E1", "Full-time staff receive 21 paid annual leave days per calendar year.",
                               "HR_POL_001", "HR_POL_001-S02", page=1)]

    result = agent.verify(claims, evidence)

    assert result.total_claims == 1
    assert result.supported_count == 1
    assert result.contradicted_count == 0
    assert result.insufficient_count == 0
    assert result.claim_verdicts[0].verdict == Verdict.SUPPORTED
    assert "21 days" in result.claim_verdicts[0].explanation
    assert result.claim_verdicts[0].source_references[0].document_id == "HR_POL_001"


# ------------------------------------------------------------------
# CONTRADICTED - wrong number
# ------------------------------------------------------------------
def test_contradicted_when_number_mismatch():
    llm = FakeLLM([
        '{"verdict": "CONTRADICTED", "explanation": "Claim says 18 days but evidence says 21 days."}'
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())

    claims = [_make_claim("C1", "Full-time staff receive 18 paid annual leave days per calendar year.",
                          numbers=["18"])]
    evidence = [_make_evidence("E1", "Full-time staff receive 21 paid annual leave days per calendar year.",
                               "HR_POL_001", "HR_POL_001-S02", page=1)]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.CONTRADICTED
    assert result.contradicted_count == 1


# ------------------------------------------------------------------
# CONTRADICTED - wrong date
# ------------------------------------------------------------------
def test_contradicted_when_date_mismatch():
    llm = FakeLLM([
        '{"verdict": "CONTRADICTED", "explanation": "Claim says 2024 but evidence says 2026."}'
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())

    claims = [_make_claim("C1", "The policy was created in 2024.", dates=["2024"])]
    evidence = [_make_evidence("E1", "The policy was created in 2026.",
                               "HR_POL_001", "HR_POL_001-S01", page=1)]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.CONTRADICTED


# ------------------------------------------------------------------
# INSUFFICIENT_EVIDENCE
# ------------------------------------------------------------------
def test_insufficient_when_no_evidence():
    agent = FactVerificationAgent(llm_client=FakeLLM([]), vector_store=FakeVectorStore())

    claims = [_make_claim("C1", "Some obscure claim with no matching evidence.", numbers=["999"])]
    evidence = []

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert result.insufficient_count == 1


# ------------------------------------------------------------------
# Multiple claims
# ------------------------------------------------------------------
def test_multiple_claims_different_verdicts():
    llm = FakeLLM([
        '{"verdict": "SUPPORTED", "explanation": "Matches evidence."}',
        '{"verdict": "CONTRADICTED", "explanation": "Conflicts with evidence."}',
        '{"verdict": "INSUFFICIENT_EVIDENCE", "explanation": "No relevant evidence."}',
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())

    claims = [
        _make_claim("C1", "Claim one supported.", numbers=["10"]),
        _make_claim("C2", "Claim two contradicted.", numbers=["20"]),
        _make_claim("C3", "Claim three insufficient.", numbers=["30"]),
    ]
    evidence = [
        _make_evidence("E1", "Evidence for claim one with number 10.", "DOC_1", "DOC_1-S01"),
        _make_evidence("E2", "Evidence for claim two with number 99.", "DOC_2", "DOC_2-S01"),
    ]

    result = agent.verify(claims, evidence)

    assert result.total_claims == 3
    assert result.supported_count == 1
    assert result.contradicted_count == 1
    assert result.insufficient_count == 1
    assert result.claim_verdicts[0].verdict == Verdict.SUPPORTED
    assert result.claim_verdicts[1].verdict == Verdict.CONTRADICTED
    assert result.claim_verdicts[2].verdict == Verdict.INSUFFICIENT_EVIDENCE


# ------------------------------------------------------------------
# Empty claims
# ------------------------------------------------------------------
def test_empty_claims_returns_empty_result():
    agent = FactVerificationAgent(llm_client=FakeLLM([]), vector_store=FakeVectorStore())

    result = agent.verify([], [])

    assert result.total_claims == 0
    assert result.supported_count == 0
    assert result.overall_status == "no_claims"


def test_unrelated_numeric_evidence_does_not_create_false_contradiction():
    agent = FactVerificationAgent(llm_client=FakeLLM([]), vector_store=FakeVectorStore())

    claims = [_make_claim("C1", "Employees receive a transport allowance of 5000.", numbers=["5000"])]
    evidence = [
        _make_evidence(
            "E1",
            "Contractors must submit invoices within 21 calendar days.",
            "HR_POL_001",
            "HR_POL_001-S02",
        )
    ]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert result.claim_verdicts[0].source_references == []


def test_superseded_evidence_is_not_used():
    agent = FactVerificationAgent(llm_client=FakeLLM([]), vector_store=FakeVectorStore())
    claims = [_make_claim("C1", "Staff receive 21 annual leave days.", numbers=["21"])]
    evidence = [
        _make_evidence(
            "E1",
            "Staff receive 21 annual leave days.",
            "HR_POL_OLD",
            "HR_POL_OLD-S01",
            status="SUPERSEDED",
        )
    ]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert result.claim_verdicts[0].source_references == []


def test_markdown_fenced_json_response_is_accepted():
    llm = FakeLLM([
        '```json\n{"verdict": "SUPPORTED", "explanation": "The evidence matches."}\n```'
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())
    claims = [_make_claim("C1", "Staff receive annual leave.")]
    evidence = [_make_evidence("E1", "Staff receive annual leave.", "HR_POL_001", "HR_POL_001-S01")]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.SUPPORTED


def test_malformed_llm_response_fails_closed():
    agent = FactVerificationAgent(llm_client=FakeLLM(["not-json"]), vector_store=FakeVectorStore())
    claims = [_make_claim("C1", "Staff receive annual leave.")]
    evidence = [_make_evidence("E1", "Staff receive annual leave.", "HR_POL_001", "HR_POL_001-S01")]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert "failed" in result.claim_verdicts[0].explanation.lower()


def test_workflow_node_returns_verdicts_and_aggregate_result():
    llm = FakeLLM([
        '{"verdict": "SUPPORTED", "explanation": "The evidence matches."}'
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())
    state = {
        "claims": [_make_claim("C1", "Staff receive annual leave.")],
        "evidence_chunks": [
            _make_evidence("E1", "Staff receive annual leave.", "HR_POL_001", "HR_POL_001-S01")
        ],
    }

    update = run(state, agent=agent)

    assert update["claim_verdicts"][0].verdict == Verdict.SUPPORTED
    assert update["verification_result"].overall_status == "all_supported"


def test_number_with_unit_matches_plain_number_in_evidence():
    llm = FakeLLM([
        '{"verdict": "SUPPORTED", "explanation": "Both specify 21 days."}'
    ])
    agent = FactVerificationAgent(llm_client=llm, vector_store=FakeVectorStore())
    claims = [_make_claim("C1", "Staff receive 21 days of leave.", numbers=["21 days"])]
    evidence = [
        _make_evidence(
            "E1",
            "Staff receive 21 paid annual leave days.",
            "HR_POL_001",
            "HR_POL_001-S01",
        )
    ]

    result = agent.verify(claims, evidence)

    assert result.claim_verdicts[0].verdict == Verdict.SUPPORTED
    assert len(llm.calls) == 1
