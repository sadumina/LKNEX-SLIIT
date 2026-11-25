# Purpose of this file is to provide deterministic access control, prompt injection patterns and sensitive data masking

"""Deterministic security rules shared by the security assessment agent."""

import base64
from dataclasses import dataclass
import re
from typing import Callable, Match, Pattern

from app.schemas.verification import RiskLevel, SecurityFindingType


@dataclass(frozen=True)
class SecurityRule:
    rule_id: str
    finding_type: SecurityFindingType
    severity: RiskLevel
    pattern: Pattern[str]
    description: str
    validator: Callable[[Match[str]], bool] | None = None

    def matches(self, text: str) -> bool:
        """Return true when a pattern has at least one validated match."""
        return any(
            self.validator is None or self.validator(match)
            for match in self.pattern.finditer(text)
        )


def _rule(
    rule_id: str,
    finding_type: SecurityFindingType,
    severity: RiskLevel,
    pattern: str,
    description: str,
    validator: Callable[[Match[str]], bool] | None = None,
) -> SecurityRule:
    return SecurityRule(
        rule_id=rule_id,
        finding_type=finding_type,
        severity=severity,
        pattern=re.compile(pattern, re.IGNORECASE),
        description=description,
        validator=validator,
    )


_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_CREDENTIAL_PATTERN = re.compile(
    r"\b(?P<label>api[_ -]?key|access[_ -]?token|secret|password)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;]{6,})",
    re.IGNORECASE,
)
_PRIVATE_KEY_BLOCK_PATTERN = re.compile(
    r"-----BEGIN (?P<kind>(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY)-----"
    r".*?-----END (?P=kind)-----",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_INTERNATIONAL_PHONE_PATTERN = re.compile(r"(?<!\w)\+\d(?:[ ()-]*\d){7,14}(?!\d)")
_NATIONAL_ID_PATTERN = re.compile(
    r"\b(?P<label>nic|national[_ -]?id)(?P<separator>\s*[:=]\s*)"
    r"(?P<value>(?:\d{9}[VX]|\d{12}))\b",
    re.IGNORECASE,
)
_BASE64_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9+/=])(?P<token>[A-Za-z0-9+/]{24,}={0,2})(?![A-Za-z0-9+/=])"
)


def _passes_luhn(match: Match[str]) -> bool:
    digits = [int(char) for char in match.group(0) if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def mask_sensitive_data(text: str) -> str:
    """Redact supported secret types without changing non-sensitive text."""
    masked = _PRIVATE_KEY_BLOCK_PATTERN.sub("[REDACTED_PRIVATE_KEY]", text)
    masked = _CREDENTIAL_PATTERN.sub(
        lambda match: f"{match.group('label')}{match.group('separator')}[REDACTED]",
        masked,
    )
    masked = _CARD_PATTERN.sub(
        lambda match: "[REDACTED_PAYMENT_CARD]" if _passes_luhn(match) else match.group(0),
        masked,
    )
    masked = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", masked)
    masked = _INTERNATIONAL_PHONE_PATTERN.sub("[REDACTED_PHONE]", masked)
    masked = _NATIONAL_ID_PATTERN.sub(
        lambda match: f"{match.group('label')}{match.group('separator')}[REDACTED_NATIONAL_ID]",
        masked,
    )
    return masked


def decoded_base64_segments(text: str, max_decoded_bytes: int = 4096) -> list[str]:
    """Decode small, valid UTF-8 Base64 tokens for scanning; never execute them."""
    decoded_segments: list[str] = []
    for match in _BASE64_TOKEN_PATTERN.finditer(text):
        token = match.group("token")
        if len(token) % 4 != 0:
            continue
        try:
            decoded_bytes = base64.b64decode(token, validate=True)
            if not decoded_bytes or len(decoded_bytes) > max_decoded_bytes:
                continue
            decoded = decoded_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue

        printable_ratio = sum(char.isprintable() or char.isspace() for char in decoded) / len(decoded)
        if printable_ratio >= 0.9:
            decoded_segments.append(decoded)
    return decoded_segments


SECURITY_RULES: tuple[SecurityRule, ...] = (
    _rule(
        "PI_IGNORE_INSTRUCTIONS",
        SecurityFindingType.PROMPT_INJECTION,
        RiskLevel.HIGH,
        r"\b(?:ignore|disregard|forget|override)[\W_]+(?:all[\W_]+)?"
        r"(?:previous|prior|earlier|system|developer)[\W_]+(?:instructions?|directions?|rules?)\b",
        "Content attempts to override trusted instructions.",
    ),
    _rule(
        "PI_REVEAL_PROMPT",
        SecurityFindingType.PROMPT_INJECTION,
        RiskLevel.HIGH,
        r"\b(?:reveal|print|show|repeat|expose)[\W_]+(?:the[\W_]+)?"
        r"(?:system|developer)[\W_]+prompt\b",
        "Content requests disclosure of hidden instructions.",
    ),
    _rule(
        "PI_FOLLOW_EMBEDDED",
        SecurityFindingType.PROMPT_INJECTION,
        RiskLevel.MEDIUM,
        r"\b(?:follow|obey|execute)[\W_]+"
        r"(?:these|the[\W_]+following|my)[\W_]+instructions?\b",
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
        validator=_passes_luhn,
    ),
    _rule(
        "SI_EMAIL",
        SecurityFindingType.SENSITIVE_INFORMATION,
        RiskLevel.MEDIUM,
        _EMAIL_PATTERN.pattern,
        "Content contains an email address that may expose personal information.",
    ),
    _rule(
        "SI_PHONE",
        SecurityFindingType.SENSITIVE_INFORMATION,
        RiskLevel.MEDIUM,
        _INTERNATIONAL_PHONE_PATTERN.pattern,
        "Content contains an international phone number.",
    ),
    _rule(
        "SI_NATIONAL_ID",
        SecurityFindingType.SENSITIVE_INFORMATION,
        RiskLevel.HIGH,
        _NATIONAL_ID_PATTERN.pattern,
        "Content appears to expose a labelled national identity number.",
    ),
)
