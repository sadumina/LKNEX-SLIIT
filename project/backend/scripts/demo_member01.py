# Purpose of this file is to demonstrate Member 01's two agents end to end on the refund-policy scenario
"""Runs Claim Extraction -> Evidence Retrieval on the blueprint's refund example.

Run from the backend folder:

    python scripts/demo_member01.py                  # real LLM + real embeddings (needs a Groq or Gemini key, internet once)
    python scripts/demo_member01.py --offline        # scripted LLM + fake embedder (needs nothing)
    python scripts/demo_member01.py --role finance   # see how the role changes the evidence
    python scripts/demo_member01.py --provider groq  # no failover, only Groq
"""
import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import claim_extraction, evidence_retrieval  # noqa: E402
from app.core.fakes import HashingEmbedder, ScriptedLLM  # noqa: E402
from app.core.llm_client import summarize_calls  # noqa: E402
from app.knowledge_base.retrieval import MANIFEST_PATH, build_index, get_retriever, load_retriever  # noqa: E402
from app.schemas.verification import ExtractedClaim, ExtractionResult, UserContext  # noqa: E402

QUESTION = "What is the return window for online orders, and do we refund shipping?"
DRAFT = (
    "Customers can return online orders within 30 days of delivery. Shipping fees are refunded in full. "
    "Items must be unused. Refunds are processed within 5 business days."
)
CANNED_CLAIMS = ExtractionResult(
    claims=[
        ExtractedClaim(text="Customers can return online orders within 30 days of delivery."),
        ExtractedClaim(text="Shipping fees are refunded in full."),
        ExtractedClaim(text="Items must be unused."),
        ExtractedClaim(text="Refunds are processed within 5 business days."),
    ]
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="no API key and no model download needed")
    parser.add_argument("--role", default="customer_service", help="role of the user asking (default: customer_service)")
    parser.add_argument("--provider", help="pin one LLM provider (groq, gemini, ...) instead of using failover")
    args = parser.parse_args()
    if args.provider:
        os.environ["LLM_PIN_PROVIDER"] = args.provider
    logging.basicConfig(level=logging.WARNING)

    if args.offline:
        llm = ScriptedLLM([CANNED_CLAIMS])
        embedder = HashingEmbedder()
        tmp = Path(tempfile.mkdtemp())
        build_index(chunks_path=tmp / "chunks.json", store_path=tmp / "chroma", embedder=embedder)
        retriever = load_retriever(chunks_path=tmp / "chunks.json", store_path=tmp / "chroma", embedder=embedder)
    else:
        llm = None                      # real LLM client
        retriever = get_retriever()     # builds the index on first use

    state = {
        "question": QUESTION,
        "draft_answer": DRAFT,
        "user": UserContext(user_id="demo", role=args.role),
    }

    print(f"\nQuestion : {QUESTION}\nDraft    : {DRAFT}\nUser role: {args.role}\n")

    state.update(claim_extraction.run(state, llm=llm))
    print("=== Agent 01: Claim Extraction ===")
    for claim in state["claims"]:
        print(f"{claim.id}: {claim.text}")
        print(f"    numbers={claim.numbers} dates={claim.dates} negated={claim.negated} entities={claim.entities}")

    state.update(evidence_retrieval.run(state, retriever=retriever))
    print("\n=== Agent 02: Evidence Retrieval ===")
    for claim in state["claims"]:
        print(f"\n{claim.id}: {claim.text}")
        chunks = state["evidence"][claim.id]
        if not chunks:
            print("    (no evidence available for this role)")
        for chunk in chunks[:3]:
            print(
                f"    [{chunk.status:10}] {chunk.doc_title} v{chunk.version}, s.{chunk.section}, p.{chunk.page}"
                f"  score={chunk.score:.4f}\n        {chunk.text[:110]}"
            )

    if not args.offline:
        print("\n=== LLM calls ===")
        for provider, row in summarize_calls().items():
            print(f"{provider}: {row}")


if __name__ == "__main__":
    main()
