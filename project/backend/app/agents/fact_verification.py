# Purpose of this file is to:
# Determines whether claims are supported, contradicted or lack evidence.

import re
from typing import Any, Dict, List, Optional

from app.schemas.verification import (
    Claim,
    ClaimVerdict,
    EvidenceChunk,
    VerificationResult,
    Verdict,
)
from app.core.llm_client import LLMClient
from app.knowledge_base.vector_store import VectorStore


class FactVerificationAgent:
    """
    Evaluates extracted factual claims against retrieved evidence from trusted
    organisational documents and classifies each claim as SUPPORTED,
    CONTRADICTED, or INSUFFICIENT_EVIDENCE.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None, vector_store: Optional[VectorStore] = None):
        self.llm = llm_client or LLMClient()
        self.vector_store = vector_store or VectorStore()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def verify(self, claims: List[Claim], evidence_chunks: List[EvidenceChunk]) -> VerificationResult:
        """
        Verify a list of claims against a list of evidence chunks.

        Args:
            claims: Atomic claims extracted from the AI-generated response.
            evidence_chunks: Evidence passages retrieved from ChromaDB.

        Returns:
            VerificationResult with a verdict per claim and aggregate counts.
        """
        verdicts: List[ClaimVerdict] = []

        # Index evidence by document_id + section_id for quick lookup
        evidence_by_key: Dict[str, EvidenceChunk] = {}
        for chunk in evidence_chunks:
            key = f"{chunk.document_id}:{chunk.section_id}"
            evidence_by_key[key] = chunk

        for claim in claims:
            # 1. Find relevant evidence for this claim
            relevant_evidence = self._find_relevant_evidence(claim, evidence_chunks)

            # 2. Deterministic numeric/date contradiction check
            deterministic_verdict = self._check_deterministic_contradiction(claim, relevant_evidence)
            if deterministic_verdict is not None:
                verdicts.append(
                    ClaimVerdict(
                        claim_id=claim.claim_id,
                        verdict=deterministic_verdict,
                        explanation=(
                            "Deterministic contradiction: claim contains a numeric or date value "
                            "that conflicts with retrieved evidence."
                        ),
                        source_references=relevant_evidence,
                    )
                )
                continue

            # 3. LLM-based semantic verification
            verdict, explanation = self._llm_verify(claim, relevant_evidence)
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim.claim_id,
                    verdict=verdict,
                    explanation=explanation,
                    source_references=relevant_evidence,
                )
            )

        return self._build_result(verdicts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _find_relevant_evidence(
        self, claim: Claim, evidence_chunks: List[EvidenceChunk]
    ) -> List[EvidenceChunk]:
        """
        Return evidence chunks that are relevant to the claim.
        Uses keyword overlap on entities, dates, and numbers as a lightweight filter.
        """
        if not evidence_chunks:
            return []

        claim_terms = set()
        if claim.entities:
            claim_terms.update(e.lower() for e in claim.entities)
        if claim.dates:
            claim_terms.update(d.lower() for d in claim.dates)
        if claim.numbers:
            claim_terms.update(n.lower() for n in claim.numbers)

        # Also extract words from claim text
        claim_terms.update(w.lower() for w in re.findall(r"\w+", claim.claim_text) if len(w) > 3)

        scored: List[tuple[float, EvidenceChunk]] = []
        for chunk in evidence_chunks:
            chunk_text_lower = chunk.text.lower()
            matches = sum(1 for term in claim_terms if term in chunk_text_lower)
            if matches > 0:
                scored.append((matches, chunk))

        # Sort by match count descending, return top 5
        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:5]]

    def _check_deterministic_contradiction(
        self, claim: Claim, evidence: List[EvidenceChunk]
    ) -> Optional[Verdict]:
        """
        If a claim contains a number or date that directly conflicts with evidence,
        return CONTRADICTED without calling the LLM.
        """
        if not evidence:
            return None

        claim_numbers = set(claim.numbers or [])
        claim_dates = set(claim.dates or [])

        for chunk in evidence:
            chunk_numbers = set(re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", chunk.text))
            chunk_dates = set(re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", chunk.text))

            # Direct number conflict: same magnitude context but different value
            if claim_numbers and chunk_numbers:
                if claim_numbers.isdisjoint(chunk_numbers):
                    # Both have numbers but none match — potential contradiction
                    return Verdict.CONTRADICTED

            # Direct date conflict
            if claim_dates and chunk_dates:
                if claim_dates.isdisjoint(chunk_dates):
                    return Verdict.CONTRADICTED

        return None

    def _llm_verify(self, claim: Claim, evidence: List[EvidenceChunk]) -> tuple[Verdict, str]:
        """
        Ask the LLM to compare the claim against the evidence and return a verdict.
        """
        if not evidence:
            return Verdict.INSUFFICIENT_EVIDENCE, "No relevant evidence found in trusted documents."

        evidence_text = "\n\n".join(
            f"[Source: {c.document_id} ({c.section_id}), page {c.page}]\n{c.text}"
            for c in evidence
        )

        prompt = (
            "You are a fact-checking assistant. Compare the CLAIM below against the EVIDENCE "
            "from trusted organisational documents.\n\n"
            f"CLAIM: {claim.claim_text}\n\n"
            f"EVIDENCE:\n{evidence_text}\n\n"
            "Classify the claim as one of:\n"
            "- SUPPORTED: The evidence agrees with the claim.\n"
            "- CONTRADICTED: The evidence conflicts with the claim.\n"
            "- INSUFFICIENT_EVIDENCE: The evidence does not contain enough information to decide.\n\n"
            "Respond with ONLY a JSON object: {\"verdict\": \"SUPPORTED|CONTRADICTED|INSUFFICIENT_EVIDENCE\", \"explanation\": \"your reasoning\"}"
        )

        try:
            response = self.llm.complete(prompt, temperature=0.0)
            import json

            parsed = json.loads(response)
            verdict = Verdict(parsed["verdict"].lower())
            explanation = parsed.get("explanation", "No explanation provided.")
            return verdict, explanation
        except Exception:
            # Fallback: if LLM fails, mark as insufficient evidence
            return Verdict.INSUFFICIENT_EVIDENCE, "LLM verification failed; insufficient evidence to determine."

    def _build_result(self, verdicts: List[ClaimVerdict]) -> VerificationResult:
        total = len(verdicts)
        supported = sum(1 for v in verdicts if v.verdict == Verdict.SUPPORTED)
        contradicted = sum(1 for v in verdicts if v.verdict == Verdict.CONTRADICTED)
        insufficient = sum(1 for v in verdicts if v.verdict == Verdict.INSUFFICIENT_EVIDENCE)

        if total == 0:
            overall = "no_claims"
        elif contradicted == total:
            overall = "all_contradicted"
        elif supported == total:
            overall = "all_supported"
        elif supported > contradicted and supported > insufficient:
            overall = "mostly_supported"
        elif contradicted > supported and contradicted > insufficient:
            overall = "mostly_contradicted"
        else:
            overall = "mixed"

        return VerificationResult(
            claim_verdicts=verdicts,
            overall_status=overall,
            total_claims=total,
            supported_count=supported,
            contradicted_count=contradicted,
            insufficient_count=insufficient,
        )


# Convenience function for workflow integration
def verify_claims(claims: List[Claim], evidence_chunks: List[EvidenceChunk]) -> VerificationResult:
    """
    Standalone function to verify claims. Useful for direct workflow integration.
    """
    agent = FactVerificationAgent()
    return agent.verify(claims, evidence_chunks)