# Purpose of this file is to test that evidence retrieval returns relevant, role-authorised and latest-version evidence
from app.agents import evidence_retrieval
from app.schemas.verification import Claim, UserContext

CS = UserContext(user_id="u1", role="customer_service")
FIN = UserContext(user_id="u2", role="finance")


def _claim(i, text):
    return Claim(id=f"C{i}", text=text)


def test_return_window_claim_finds_current_policy_first(retriever):
    results = retriever.search(
        "Customers can return online orders within 30 days of delivery.",
        "customer_service",
    )
    assert results[0].doc_id == "returns-policy" and results[0].section == "2.1"
    assert results[0].status == "current" and results[0].page == 1


def test_superseded_faq_is_returned_but_tagged_and_ranked_lower(retriever):
    results = retriever.search(
        "Customers can return online orders within 30 days of delivery.",
        "customer_service",
    )
    faq = [r for r in results if r.doc_id == "returns-faq"]
    assert faq and all(r.status == "superseded" for r in faq)
    assert results[0].status == "current"
    assert max(r.score for r in faq) < results[0].score


def test_customer_service_never_sees_the_finance_manual(retriever):
    for query in [
        "Refunds are processed within 5 business days.",
        "approval limits",
        "business days reconciliation",
    ]:
        assert all(
            r.doc_id != "finance-ops-manual"
            for r in retriever.search(query, "customer_service")
        )


def test_finance_role_can_find_processing_time(retriever):
    results = retriever.search(
        "Refunds are processed within 5 business days.", "finance"
    )
    assert results[0].doc_id == "finance-ops-manual" and results[0].section == "2.1"


def test_unknown_or_missing_role_gets_no_evidence(retriever):
    assert retriever.search("return window", "intern") == []
    assert retriever.search("return window", None) == []


def test_exact_numbers_are_matched_by_keyword_search(retriever):
    results = retriever.search("5 business days", "finance")
    assert results[0].doc_id == "finance-ops-manual"


def test_agent_returns_a_key_for_every_claim_id(retriever):
    claims = [
        _claim(1, "Customers can return online orders within 30 days of delivery."),
        _claim(2, "Shipping fees are refunded in full."),
        _claim(3, "Items must be unused."),
        _claim(4, "Refunds are processed within 5 business days."),
    ]
    evidence = evidence_retrieval.run(
        {"claims": claims, "user": CS}, retriever=retriever
    )["evidence"]
    assert list(evidence) == ["C1", "C2", "C3", "C4"]
    assert evidence["C2"][0].section == "2.4"  # shipping fee clause
    assert all(
        c.doc_id != "finance-ops-manual" for chunks in evidence.values() for c in chunks
    )


def test_agent_gives_empty_lists_when_the_role_has_no_access(retriever):
    evidence = evidence_retrieval.run(
        {
            "claims": [_claim(1, "Items must be unused.")],
            "user": {"user_id": "x", "role": "intern"},
        },
        retriever=retriever,
    )["evidence"]
    assert evidence == {"C1": []}


def test_agent_accepts_claims_as_plain_dicts(retriever):
    evidence = evidence_retrieval.run(
        {
            "claims": [{"id": "C1", "text": "Gift cards are non-refundable."}],
            "user": CS,
        },
        retriever=retriever,
    )["evidence"]
    assert evidence["C1"][0].section == "3.2"


def test_no_claims_gives_empty_evidence(retriever):
    assert evidence_retrieval.run({"claims": [], "user": CS}, retriever=retriever) == {
        "evidence": {}
    }
