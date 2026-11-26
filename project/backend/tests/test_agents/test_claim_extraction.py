# Purpose of this file is to test that the claim extraction agent splits answers into correct atomic claims

from app.agents.claim_extraction import run
from app.schemas.verification import Claim, ExtractionResult, ExtractedClaim


def test_claim_extraction_uses_shared_claim_schema():
    def fake_llm(system, user, schema):
        assert schema is ExtractionResult
        return ExtractionResult(
            claims=[
                ExtractedClaim(
                    text="Employees receive 21 days of annual leave.",
                    entities=["Employees"],
                )
            ]
        )

    update = run(
        {
            "question": "How much annual leave is provided?",
            "draft_answer": "Employees receive 21 days of annual leave.",
        },
        llm=fake_llm,
    )

    claim = update["claims"][0]
    assert claim.claim_id == "C1"
    assert claim.claim_text == "Employees receive 21 days of annual leave."
    assert claim.numbers == ["21 days"]
    assert claim.negated is False


def test_claim_extraction_output_is_accepted_by_fact_verification_schema():
    def fake_llm(system, user, schema):
        return ExtractionResult(
            claims=[ExtractedClaim(text="The policy was not created in 2024.")]
        )

    claim = run(
        {"question": "When was it created?", "draft_answer": "The policy was not created in 2024."},
        llm=fake_llm,
    )["claims"][0]

    assert claim.claim_id == "C1"
    assert claim.dates == ["2024"]
    assert claim.negated is True


def test_claim_accepts_incoming_member_field_names():
    claim = Claim(
        id="C9",
        text="Incoming schema remains compatible.",
        entities=["Incoming schema"],
    )

    assert claim.claim_id == "C9"
    assert claim.claim_text == "Incoming schema remains compatible."
    assert claim.id == claim.claim_id
    assert claim.text == claim.claim_text
