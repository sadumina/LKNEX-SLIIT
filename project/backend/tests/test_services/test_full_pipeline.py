"""Offline end-to-end test for the complete multi-agent verification pipeline."""

from app.agents.fact_verification import FactVerificationAgent
from app.core.fakes import ScriptedLLM
from app.database import db
from app.orchestration.workflow import build_post_retrieval_graph
from app.schemas.decision import FinalAction
from app.schemas.verification import (
    ExtractedClaim,
    ExtractionResult,
    FactVerificationDecision,
    Verdict,
)
from app.services.verification_service import VerificationService


class _SupportedVerifier:
    def __call__(self, system, user, schema, **kwargs):
        return FactVerificationDecision(
            verdict=Verdict.SUPPORTED,
            explanation="The retrieved active policy supports the claim.",
        )


def test_complete_pipeline_extracts_retrieves_verifies_and_persists(retriever):
    connection = db.connect(":memory:")
    graph = build_post_retrieval_graph(
        fact_agent=FactVerificationAgent(llm_client=_SupportedVerifier())
    )
    service = VerificationService(connection, graph=graph)
    extraction_llm = ScriptedLLM(
        [
            ExtractionResult(
                claims=[ExtractedClaim(text="Gift cards are non-refundable.")]
            )
        ]
    )

    try:
        response = service.verify_complete(
            question="Can gift cards be refunded?",
            draft_answer="Gift cards are non-refundable.",
            user_role="customer_service",
            claim_llm=extraction_llm,
            retriever=retriever,
        )

        assert response.action == FinalAction.APPROVE
        assert response.verification.total_claims == 1
        assert response.verification.supported_count == 1
        assert response.verification.claims[0].citations
        assert response.security.overall_risk.value == "low"

        saved = db.get_run(connection, response.run_id)
        assert saved["status"] == "completed"
        assert db.get_claim_results(connection, response.run_id)[0]["verdict"] == "supported"
    finally:
        connection.close()
