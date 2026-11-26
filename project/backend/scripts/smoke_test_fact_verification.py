"""Run Fact Verification against one section of the synthetic dataset."""

import argparse
import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.fact_verification import FactVerificationAgent
from app.core.llm_client import call_structured, get_call_log, reset_call_log
from app.schemas.verification import Claim, EvidenceChunk


DEFAULT_DATASET = BACKEND_ROOT / "data" / "synthetic" / "organisational_documents.json"
DEFAULT_CLAIM = "Full-time staff receive 21 paid annual leave days per calendar year."


def load_case(
    dataset_path: Path,
    document_id: str,
    section_id: str,
    claim_text: str,
    numbers: list[str],
) -> tuple[Claim, EvidenceChunk]:
    """Build one claim/evidence pair from the selected synthetic section."""
    documents = json.loads(dataset_path.read_text(encoding="utf-8"))
    document = next(
        (
            item
            for item in documents
            if item["document_id"] == document_id
            and item["document_status"].upper() == "ACTIVE"
        ),
        None,
    )
    if document is None:
        raise ValueError(f"Active document {document_id!r} was not found.")

    section = next(
        (item for item in document["sections"] if item["section_id"] == section_id),
        None,
    )
    if section is None:
        raise ValueError(f"Section {section_id!r} was not found in {document_id!r}.")

    claim = Claim(
        claim_id="SMOKE-C1",
        claim_text=claim_text,
        numbers=numbers,
    )
    evidence = EvidenceChunk(
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
    return claim, evidence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one live Fact Verification check using synthetic evidence."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--document-id", default="HR_POL_001")
    parser.add_argument("--section-id", default="HR_POL_001-S02")
    parser.add_argument("--claim", default=DEFAULT_CLAIM)
    parser.add_argument("--number", action="append")
    parser.add_argument(
        "--provider",
        choices=("groq", "gemini", "custom"),
        help="Pin this smoke test to one configured provider.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and display the selected case without calling an LLM.",
    )
    args = parser.parse_args()

    claim, evidence = load_case(
        args.dataset,
        args.document_id,
        args.section_id,
        args.claim,
        args.number or ["21 days"],
    )
    print("CLAIM:", claim.claim_text)
    print("EVIDENCE_SOURCE:", evidence.chunk_id)
    print("EVIDENCE_TEXT:", evidence.text)

    if args.dry_run:
        print("DRY_RUN: no provider request was made")
        return

    def structured_call(system, user, schema, **kwargs):
        return call_structured(
            system,
            user,
            schema,
            provider=args.provider,
            **kwargs,
        )

    reset_call_log()
    result = FactVerificationAgent(llm_client=structured_call).verify(
        [claim],
        [evidence],
    )
    verdict = result.claim_verdicts[0]
    print("VERDICT:", verdict.verdict.value)
    print("EXPLANATION:", verdict.explanation)
    print("CITATIONS:", [source.chunk_id for source in verdict.source_references])
    for entry in get_call_log():
        safe_metadata = {
            key: entry[key]
            for key in (
                "provider",
                "model",
                "latency_ms",
                "input_tokens",
                "output_tokens",
                "failed_over_from",
            )
        }
        print("CALL_METADATA:", safe_metadata)


if __name__ == "__main__":
    main()
