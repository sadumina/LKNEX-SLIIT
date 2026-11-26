# Purpose of this file is to build the initial state, run the verification workflow and return the final result

"""Application service connecting prepared evidence, workflow, and SQLite."""

import sqlite3
import time

from app.core.llm_client import get_call_log
from app.database import db
from app.orchestration.state import initial_state
from app.orchestration.workflow import build_post_retrieval_graph
from app.schemas.api import (
    CitationResponse,
    ClaimDecisionResponse,
    SecuritySummaryResponse,
    VerificationSummaryResponse,
    WorkflowResultResponse,
)
from app.schemas.decision import FinalAction
from app.schemas.verification import Claim, EvidenceChunk, Verdict


_DB_VERDICT = {
    Verdict.SUPPORTED: "supported",
    Verdict.CONTRADICTED: "contradicted",
    Verdict.INSUFFICIENT_EVIDENCE: "unsupported",
}


class VerificationService:
    """Run the post-retrieval graph and persist its auditable result."""

    def __init__(self, connection: sqlite3.Connection, graph=None):
        self.connection = connection
        self.graph = graph or build_post_retrieval_graph()
        db.init_db(connection)

    def verify_prepared(
        self,
        *,
        question: str,
        draft_answer: str,
        user_role: str,
        claims: list[Claim],
        evidence_chunks: list[EvidenceChunk],
        mode: str = "multi_agent",
    ) -> WorkflowResultResponse:
        """Verify a response after upstream claim extraction and retrieval."""
        started = time.perf_counter()
        llm_calls_before = len(get_call_log())
        run_id = db.start_run(
            self.connection,
            mode=mode,
            user_role=user_role,
            question=question,
            draft_answer=draft_answer,
        )
        db.log_event(
            self.connection,
            run_id,
            "supervisor",
            "workflow_started",
            {"claims": len(claims), "evidence_chunks": len(evidence_chunks)},
        )

        state = initial_state(
            question=question,
            user_role=user_role,
            mode=mode,
            run_id=run_id,
            draft_answer=draft_answer,
        )
        state["claims"] = claims
        state["evidence_chunks"] = evidence_chunks

        try:
            result = self.graph.invoke(state)
            response = self._build_response(
                result,
                run_id=run_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
                llm_calls=max(0, len(get_call_log()) - llm_calls_before),
            )
            self._persist_success(result, response)
            return response
        except Exception as error:
            safe_error = f"{type(error).__name__}: {str(error)[:500]}"
            db.fail_run(self.connection, run_id, safe_error)
            raise

    def _persist_success(self, state: dict, response: WorkflowResultResponse) -> None:
        verification = state["verification_result"]
        claims_by_id = {claim.claim_id: claim for claim in state.get("claims") or []}
        rows = []
        for verdict in verification.claim_verdicts:
            claim = claims_by_id.get(verdict.claim_id)
            rows.append(
                {
                    "claim_id": verdict.claim_id,
                    "claim_text": claim.claim_text if claim else "",
                    "verdict": _DB_VERDICT[verdict.verdict],
                    "evidence_chunk_ids": [
                        source.chunk_id for source in verdict.source_references
                    ],
                }
            )
        db.save_claim_results(self.connection, response.run_id, rows)

        security = state["security_report"]
        db.log_event(
            self.connection,
            response.run_id,
            "fact_verification",
            "verification_completed",
            {
                "supported": verification.supported_count,
                "contradicted": verification.contradicted_count,
                "insufficient": verification.insufficient_count,
            },
        )
        db.log_event(
            self.connection,
            response.run_id,
            "security_assessment",
            "security_completed",
            {"risk": security.overall_risk.value, "findings": len(security.findings)},
        )
        db.log_event(
            self.connection,
            response.run_id,
            "policy_engine",
            "decision_created",
            {
                "action": response.action.value,
                "reason": response.decision_reason,
            },
        )
        if response.action == FinalAction.HUMAN_REVIEW:
            db.create_human_review(self.connection, response.run_id)

        db.finish_run(
            self.connection,
            response.run_id,
            action=response.action.value,
            final_answer=response.final_answer,
            risk_level=response.security.overall_risk.value,
            latency_ms=response.latency_ms,
            llm_calls=response.llm_calls,
        )
        db.log_event(
            self.connection,
            response.run_id,
            "supervisor",
            "workflow_completed",
            {"action": response.action.value},
        )

    @staticmethod
    def _build_response(
        state: dict,
        *,
        run_id: str,
        latency_ms: int,
        llm_calls: int,
    ) -> WorkflowResultResponse:
        decision = state.get("policy_decision")
        verification = state.get("verification_result")
        security = state.get("security_report")
        if decision is None or verification is None or security is None:
            raise RuntimeError("Workflow completed without required typed outputs.")

        claim_results = []
        for verdict in verification.claim_verdicts:
            citations = [
                CitationResponse(
                    chunk_id=source.chunk_id,
                    document_id=source.document_id,
                    section_id=source.section_id,
                    page=source.page,
                    document_version=source.document_version,
                )
                for source in verdict.source_references
            ]
            claim_results.append(
                ClaimDecisionResponse(
                    claim_id=verdict.claim_id,
                    verdict=verdict.verdict,
                    explanation=verdict.explanation,
                    citations=citations,
                )
            )

        return WorkflowResultResponse(
            run_id=run_id,
            action=decision.action,
            decision_reason=decision.reason,
            final_answer=state.get("final_answer"),
            verification=VerificationSummaryResponse(
                overall_status=verification.overall_status,
                total_claims=verification.total_claims,
                supported_count=verification.supported_count,
                contradicted_count=verification.contradicted_count,
                insufficient_count=verification.insufficient_count,
                claims=claim_results,
            ),
            security=SecuritySummaryResponse(
                overall_risk=security.overall_risk,
                recommended_action=security.recommended_action,
                findings=security.findings,
            ),
            latency_ms=latency_ms,
            llm_calls=llm_calls,
        )
