# Purpose of this file is to test that the claim extraction agent splits answers into correct atomic claims
import pytest
from pydantic import ValidationError

from app.agents import claim_extraction
from app.agents.claim_extraction import (
    ClaimExtractionError,
    numbers_in,
    tag_dates,
    tag_numbers,
)
from app.core.fakes import ScriptedLLM
from app.schemas.verification import ExtractedClaim, ExtractionResult

DRAFT = (
    "Customers can return online orders within 30 days of delivery. Shipping fees are refunded in full. "
    "Items must be unused. Refunds are processed within 5 business days."
)


def _result(*texts, negated=()):
    return ExtractionResult(
        claims=[ExtractedClaim(text=t, negated=(t in negated)) for t in texts]
    )


FOUR = _result(
    "Customers can return online orders within 30 days of delivery.",
    "Shipping fees are refunded in full.",
    "Items must be unused.",
    "Refunds are processed within 5 business days.",
)


def test_refund_draft_gives_four_claims_with_ids_and_numbers():
    out = claim_extraction.run({"draft_answer": DRAFT}, llm=ScriptedLLM([FOUR]))
    claims = out["claims"]
    assert [c.id for c in claims] == ["C1", "C2", "C3", "C4"]
    assert claims[0].numbers == ["30 days"]
    assert claims[3].numbers == ["5 business days"]
    assert claims[1].numbers == [] and claims[2].dates == []


def test_negation_is_detected_even_if_the_llm_misses_it():
    llm = ScriptedLLM([_result("Gift cards are not refundable.")])
    claim = claim_extraction.run(
        {"draft_answer": "Gift cards are not refundable."}, llm=llm
    )["claims"][0]
    assert claim.negated is True


def test_duplicates_and_blank_claims_are_removed():
    llm = ScriptedLLM([_result("Items must be unused.", "items must be unused", "  ")])
    claims = claim_extraction.run({"draft_answer": "Items must be unused."}, llm=llm)[
        "claims"
    ]
    assert [c.text for c in claims] == ["Items must be unused."]


def test_empty_draft_returns_no_claims_without_calling_the_llm():
    llm = ScriptedLLM([FOUR])
    assert claim_extraction.run({"draft_answer": "   "}, llm=llm) == {"claims": []}
    assert llm.calls == []


def test_retry_when_a_number_is_missing_from_all_claims():
    incomplete = _result(
        "Customers can return online orders within 30 days of delivery.",
        "Shipping fees are refunded in full.",
        "Items must be unused.",
    )
    llm = ScriptedLLM([incomplete, FOUR])
    claims = claim_extraction.run({"draft_answer": DRAFT}, llm=llm)["claims"]
    assert len(llm.calls) == 2 and len(claims) == 4
    assert "5" in llm.calls[1]["user"]  # the feedback names the missing number


def test_retry_after_invalid_output_then_success():
    bad = ValidationError.from_exception_data("ExtractionResult", [])
    llm = ScriptedLLM([bad, FOUR])
    claims = claim_extraction.run({"draft_answer": DRAFT}, llm=llm)["claims"]
    assert len(claims) == 4 and len(llm.calls) == 2


def test_error_is_raised_when_every_attempt_is_invalid():
    llm = ScriptedLLM([ValueError("no tool output")])
    with pytest.raises(ClaimExtractionError):
        claim_extraction.run({"draft_answer": DRAFT}, llm=llm)


def test_prompt_wraps_the_untrusted_draft_in_tags():
    llm = ScriptedLLM([FOUR])
    claim_extraction.run(
        {"question": "What is the window?", "draft_answer": DRAFT}, llm=llm
    )
    user = llm.calls[0]["user"]
    assert "<answer>" in user and "</answer>" in user and "<question>" in user


@pytest.mark.parametrize(
    "text, numbers, dates",
    [
        ("Returns Policy v3.2 was updated in September 2026.", [], ["September 2026"]),
        (
            "Refunds above LKR 50,000 need approval within 3 working days.",
            ["LKR 50,000", "3 working days"],
            [],
        ),
        ("The 2024 FAQ says 30 days.", ["30 days"], ["2024"]),
        ("Effective 2026-09-01, a 5% fee applies.", ["5%"], ["2026-09-01"]),
    ],
)
def test_regex_tagging(text, numbers, dates):
    assert tag_numbers(text) == numbers
    assert tag_dates(text) == dates


def test_numbers_in_ignores_list_markers():
    assert numbers_in("1. First point\n2. Second point costs 1,000 rupees") == {"1000"}
