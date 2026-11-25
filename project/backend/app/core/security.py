# Purpose of this file is to provide deterministic access control, prompt injection patterns and sensitive data masking

"""Deterministic security rules shared by the security assessment agent."""

from dataclasses import dataclass
import re
from typing import Pattern

from app.schemas.verification import RiskLevel, SecurityFindingType


@dataclass(frozen=True)
class SecurityRule:
    rule_id: str
    finding_type: SecurityFindingType
    severity: RiskLevel
    pattern: Pattern[str]
    description: str


def _rule(
    rule_id: str,
    finding_type: SecurityFindingType,
    severity: RiskLevel,
    pattern: str,
    description: str,
) -> SecurityRule:
    return SecurityRule(
        rule_id=rule_id,
        finding_type=finding_type,
        severity=severity,
        pattern=re.compile(pattern, re.IGNORECASE),
        description=description,
    )


SECURITY_RULES: tuple[SecurityRule, ...] = (
    _rule(
        "PI_IGNORE_INSTRUCTIONS",
        SecurityFindingType.PROMPT_INJECTION,
        RiskLevel.HIGH,
        r"\bignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions?\b",
        "Content attempts to override trusted instructions.",
    ),
    _rule(
        "PI_REVEAL_PROMPT",
        SecurityFindingType.PROMPT_INJECTION,
        RiskLevel.HIGH,
        r"\b(?:reveal|print|show|repeat|expose)\s+(?:the\s+)?(?:system|developer)\s+prompt\b",
        "Content requests disclosure of hidden instructions.",
    ),
    _rule(
        "PI_FOLLOW_EMBEDDED",
        SecurityFindingType.PROMPT_INJECTION,
        RiskLevel.MEDIUM,
        r"\b(?:follow|obey|execute)\s+(?:these|the following|my)\s+instructions?\b",
        "Content contains a suspicious embedded instruction.",
    ),
    _rule(
        "SI_PRIVATE_KEY",
        SecurityFindingType.SENSITIVE_INFORMATION,
        RiskLevel.HIGH,
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        "Content appears to contain private key material.",
    ),
    _rule(
        "SI_CREDENTIAL",
        SecurityFindingType.SENSITIVE_INFORMATION,
        RiskLevel.HIGH,
        r"\b(?:api[_ -]?key|access[_ -]?token|secret|password)\s*[:=]\s*[^\s,;]{6,}",
        "Content appears to expose a credential or secret.",
    ),
    _rule(
        "SI_PAYMENT_CARD",
        SecurityFindingType.SENSITIVE_INFORMATION,
        RiskLevel.HIGH,
        r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)",
        "Content appears to contain a payment-card number.",
    ),
)
