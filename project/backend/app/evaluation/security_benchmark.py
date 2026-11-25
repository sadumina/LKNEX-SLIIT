"""Labelled benchmark evaluation for the Security Assessment Agent."""

import json
from pathlib import Path
from typing import Any

from app.agents.security_assessment import SecurityAssessmentAgent
from app.schemas.verification import EvidenceChunk, RiskLevel


def load_security_cases(path: Path) -> list[dict[str, Any]]:
    """Load non-empty JSONL records from ``path``."""
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as benchmark_file:
        for line_number, line in enumerate(benchmark_file, start=1):
            if not line.strip():
                continue
            case = json.loads(line)
            case.setdefault("evidence", [])
            case.setdefault("expected_rule_ids", [])
            if not case.get("case_id") or not case.get("expected_risk"):
                raise ValueError(f"Invalid benchmark case on line {line_number}")
            cases.append(case)
    return cases


def _evidence(case_id: str, values: list[str]) -> list[EvidenceChunk]:
    return [
        EvidenceChunk(
            chunk_id=f"{case_id}-E{index}",
            text=text,
            document_id=f"{case_id}-DOC",
            section_id=f"{case_id}-S{index}",
            page=1,
            document_version="1.0",
            document_status="ACTIVE",
            effective_date="2026-01-01",
            policy_topic="security_benchmark",
        )
        for index, text in enumerate(values, start=1)
    ]


def evaluate_security_cases(
    cases: list[dict[str, Any]],
    agent: SecurityAssessmentAgent | None = None,
) -> dict[str, Any]:
    """Evaluate labelled cases and return report-friendly aggregate metrics."""
    assessor = agent or SecurityAssessmentAgent()
    correct_risk = 0
    attack_cases = 0
    detected_attacks = 0
    safe_cases = 0
    false_positives = 0
    failed_cases: list[dict[str, Any]] = []

    for case in cases:
        expected_risk = RiskLevel(case["expected_risk"])
        report = assessor.assess(
            case.get("draft_answer", ""),
            _evidence(case["case_id"], case["evidence"]),
        )
        actual_rule_ids = {finding.rule_id for finding in report.findings}
        expected_rule_ids = set(case["expected_rule_ids"])
        risk_correct = report.overall_risk == expected_risk
        rules_correct = expected_rule_ids.issubset(actual_rule_ids)

        if risk_correct:
            correct_risk += 1
        if expected_risk == RiskLevel.LOW:
            safe_cases += 1
            if report.overall_risk != RiskLevel.LOW:
                false_positives += 1
        else:
            attack_cases += 1
            if report.overall_risk != RiskLevel.LOW:
                detected_attacks += 1

        if not risk_correct or not rules_correct:
            failed_cases.append(
                {
                    "case_id": case["case_id"],
                    "expected_risk": expected_risk.value,
                    "actual_risk": report.overall_risk.value,
                    "missing_rule_ids": sorted(expected_rule_ids - actual_rule_ids),
                    "unexpected_rule_ids": sorted(actual_rule_ids - expected_rule_ids),
                }
            )

    total = len(cases)
    return {
        "total_cases": total,
        "safe_cases": safe_cases,
        "attack_cases": attack_cases,
        "classification_accuracy": correct_risk / total if total else 0.0,
        "detection_rate": detected_attacks / attack_cases if attack_cases else 0.0,
        "false_positive_rate": false_positives / safe_cases if safe_cases else 0.0,
        "failed_cases": failed_cases,
    }
