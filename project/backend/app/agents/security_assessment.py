# Purpose of this file is to:
# Detects potential prompt injection and sensitive information exposure.

"""Agent 04: deterministic security and risk assessment."""

from dataclasses import dataclass
from typing import Iterable

from app.core.security import SECURITY_RULES
from app.schemas.verification import (
    EvidenceChunk,
    RiskLevel,
    SecurityFinding,
    SecurityReport,
    SecuritySource,
)


@dataclass(frozen=True)
class _ScanTarget:
    text: str
    source: SecuritySource
    source_id: str


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}


class SecurityAssessmentAgent:
    """Scan generated and retrieved text using deterministic security rules."""

    def assess(
        self,
        draft_answer: str,
        evidence_chunks: Iterable[EvidenceChunk],
    ) -> SecurityReport:
        targets = [
            _ScanTarget(
                text=draft_answer or "",
                source=SecuritySource.DRAFT_ANSWER,
                source_id="draft_answer",
            )
        ]
        targets.extend(
            _ScanTarget(
                text=chunk.text,
                source=SecuritySource.EVIDENCE,
                source_id=chunk.chunk_id,
            )
            for chunk in evidence_chunks
        )

        findings: list[SecurityFinding] = []
        seen: set[tuple[str, SecuritySource, str]] = set()

        for target in targets:
            for rule in SECURITY_RULES:
                key = (rule.rule_id, target.source, target.source_id)
                if key in seen or not rule.pattern.search(target.text):
                    continue
                seen.add(key)
                findings.append(
                    SecurityFinding(
                        finding_type=rule.finding_type,
                        severity=rule.severity,
                        source=target.source,
                        source_id=target.source_id,
                        rule_id=rule.rule_id,
                        description=rule.description,
                    )
                )

        overall_risk = max(
            (finding.severity for finding in findings),
            key=lambda level: _RISK_ORDER[level],
            default=RiskLevel.LOW,
        )
        action = {
            RiskLevel.LOW: "approve",
            RiskLevel.MEDIUM: "human_review",
            RiskLevel.HIGH: "block",
        }[overall_risk]

        return SecurityReport(
            findings=findings,
            overall_risk=overall_risk,
            scanned_sources=len(targets),
            recommended_action=action,
        )


def run(state: dict, agent: SecurityAssessmentAgent | None = None) -> dict:
    """Run security assessment as a workflow node and return a state update."""
    assessor = agent or SecurityAssessmentAgent()
    report = assessor.assess(
        draft_answer=state.get("draft_answer") or "",
        evidence_chunks=state.get("evidence_chunks") or [],
    )
    return {"security_report": report}
