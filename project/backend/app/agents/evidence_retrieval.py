# Purpose of this file is to retrieves evidence from trusted organizational documents.# Purpose of this file is to retrieve authorised, version-aware evidence for each claim from the knowledge base
"""Agent 02: Evidence Retrieval.

Input  (reads from state):  ``claims`` (from the Claim Extraction agent) and ``user``
Output (writes to state):   ``evidence``  ->  dict[claim_id, list[EvidenceChunk]]

Why this agent exists
---------------------
A claim can only be judged against evidence. This agent finds, for every claim,
the passages of the company's trusted documents that support or contradict it.

Two guarantees the rest of the system relies on
-----------------------------------------------
1. Every claim ID is present in the result, even when nothing was found (empty
   list). The Fact Verification agent then marks that claim "unsupported"
   instead of crashing on a missing key.
2. Only documents the user's role may read are ever searched, so restricted
   documents can never leak into evidence or citations.
"""
import logging

from app.knowledge_base.retrieval import HybridRetriever, get_retriever
from app.schemas.verification import Claim

logger = logging.getLogger(__name__)


def _as_claim(item) -> Claim:
    """Accept Claim objects or plain dicts (for example after JSON serialisation)."""
    return item if isinstance(item, Claim) else Claim.model_validate(item)


def _role_of(user) -> str | None:
    if user is None:
        return None
    return user.get("role") if isinstance(user, dict) else getattr(user, "role", None)


def run(state: dict, retriever: HybridRetriever | None = None) -> dict:
    """Retrieve evidence for every claim in ``state["claims"]``."""
    claims = [_as_claim(c) for c in state.get("claims") or []]
    if not claims:
        return {"evidence": {}}

    role = _role_of(state.get("user"))
    retriever = retriever or get_retriever()

    # One batched embedding call for all claims, then one hybrid search per claim.
    results = retriever.search_many([c.text for c in claims], role)

    evidence = {claim.id: chunks for claim, chunks in zip(claims, results)}
    for claim_id, chunks in evidence.items():
        logger.info("evidence claim=%s role=%s found=%d", claim_id, role, len(chunks))
    return {"evidence": evidence}
