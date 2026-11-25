# Purpose of this file is to provide the single LLM entry point with provider failover, retries, JSON parsing and per-call token and latency logging

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_PROVIDERS = "groq,gemini"
DEFAULT_COOLDOWN_SECONDS = 60.0
BAD_KEY_COOLDOWN_SECONDS = 600.0
FAILOVER_STATUS = {401, 403, 408, 429}

_now = time.monotonic


class LLMOutputError(ValueError):
    """The model did not return usable structured output."""


class AllProvidersFailedError(RuntimeError):
    """No configured provider could answer. ``errors`` lists (provider, exception) pairs."""

    def __init__(self, errors: list[tuple[str, Exception]]):
        self.errors = errors
        detail = "; ".join(
            f"{name}: {type(exc).__name__}: {exc}" for name, exc in errors
        )
        super().__init__(f"No LLM provider could answer. {detail}")


# Provider configuration
@dataclass(frozen=True)
class ProviderConfig:
    name: str
    kind: str  # protocol: always "openai" (an OpenAI-compatible endpoint)
    key_envs: tuple[str, ...]  # accepted environment variable names for the API key
    model_env: str
    base_url: str | None = None
    base_url_env: str | None = None


PROVIDERS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        name="groq",
        kind="openai",
        key_envs=("GROQ_API_KEY", "LLM_KEY_GROQ", "LLM_key_Groq"),
        model_env="GROQ_MODEL",
        base_url="https://api.groq.com/openai/v1",
    ),
    "gemini": ProviderConfig(
        name="gemini",
        kind="openai",
        # LLM_Key_OpenAI is the name the team first planned for the Gemini key; kept as an alias.
        key_envs=(
            "GEMINI_API_KEY",
            "LLM_KEY_GEMINI",
            "LLM_Key_OpenAI",
            "LLM_KEY_OPENAI",
        ),
        model_env="GEMINI_MODEL",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "custom": ProviderConfig(
        name="custom",
        kind="openai",
        key_envs=("LLM_API_KEY",),
        model_env="LLM_MODEL",
        base_url_env="LLM_BASE_URL",
    ),
}


@dataclass(frozen=True)
class _Resolved:
    name: str
    kind: str
    api_key: str
    model: str
    base_url: str | None


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _config(name: str) -> ProviderConfig:
    config = PROVIDERS.get(name)
    if config is None:
        raise RuntimeError(
            f"Unknown LLM provider {name!r}. Known providers: {', '.join(PROVIDERS)}."
        )
    return config


def credentials(name: str) -> tuple[str | None, str | None]:
    """``(api_key, base_url)`` of a provider. Needs no model, so it can be used to LIST models."""
    config = _config(name)
    base_url = (
        config.base_url
        or (os.getenv(config.base_url_env, "").strip() if config.base_url_env else None)
        or None
    )
    return _first_env(config.key_envs), base_url


def _resolve(name: str) -> _Resolved | None:
    """Return the usable provider, or None if no API key is configured for it."""
    config = _config(name)
    api_key, base_url = credentials(name)
    if not api_key:
        return None
    model = os.getenv(config.model_env, "").strip()
    if not model:
        raise RuntimeError(
            f"{config.name}: an API key is set but {config.model_env} is not. Add it to your .env file."
        )
    if not base_url:
        raise RuntimeError(f"{config.name}: {config.base_url_env} is not set.")
    return _Resolved(config.name, config.kind, api_key, model, base_url)


def _chain(provider: str | None) -> tuple[list[_Resolved], bool]:
    """Providers to try, in order, and whether the choice is pinned (no failover)."""
    pin = (provider or os.getenv("LLM_PIN_PROVIDER") or "").strip().lower()
    if pin:
        resolved = _resolve(pin)
        if resolved is None:
            raise RuntimeError(
                f"Provider {pin!r} is pinned but no API key was found. Set one of: {', '.join(PROVIDERS[pin].key_envs)}."
            )
        return [resolved], True

    names = [
        n.strip().lower()
        for n in os.getenv("LLM_PROVIDERS", DEFAULT_PROVIDERS).split(",")
        if n.strip()
    ]
    chain = [r for r in (_resolve(n) for n in names) if r is not None]
    if not chain:
        expected = "; ".join(
            f"{n}: {', '.join(PROVIDERS[n].key_envs[:2])}"
            for n in names
            if n in PROVIDERS
        )
        raise RuntimeError(
            f"No LLM provider is configured. Set an API key in your .env file ({expected})."
        )
    return chain, False


# Failover, cooldown
_lock = threading.Lock()
_cooldown_until: dict[str, float] = {}


def _is_failover_error(exc: Exception) -> bool:
    """True for errors that another provider could fix: rate limit, outage, timeout, bad key."""
    if isinstance(exc, ValueError):  # bad output: the agent retries, no failover
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in FAILOVER_STATUS or status >= 500
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return type(exc).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }  # SDK network errors


def _start_cooldown(provider: str, exc: Exception) -> None:
    status = getattr(exc, "status_code", None)
    seconds = (
        BAD_KEY_COOLDOWN_SECONDS
        if status in (401, 403)
        else float(os.getenv("LLM_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS))
    )
    with _lock:
        _cooldown_until[provider] = _now() + seconds


def _order(chain: list[_Resolved], pinned: bool) -> list[_Resolved]:
    """Ready providers first (in configured order), cooling-down ones last as a final resort."""
    if pinned:
        return chain
    now = _now()
    with _lock:
        ready = [p for p in chain if _cooldown_until.get(p.name, 0.0) <= now]
        cooling = sorted(
            (p for p in chain if _cooldown_until.get(p.name, 0.0) > now),
            key=lambda p: _cooldown_until[p.name],
        )
    return ready + cooling


# Call log (audit evidence and benchmark cost/token numbers)
_CALL_LOG: deque[dict] = deque(maxlen=5000)


def _record(
    provider: _Resolved, latency_ms: int, usage: tuple, failed_over_from: list[str]
) -> None:
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "model": provider.model,
        "latency_ms": latency_ms,
        "input_tokens": usage[0],
        "output_tokens": usage[1],
        "failed_over_from": failed_over_from,
    }
    with _lock:
        _CALL_LOG.append(entry)
    logger.info(
        "llm_call provider=%s model=%s latency_ms=%d input_tokens=%s output_tokens=%s failed_over_from=%s",
        provider.name,
        provider.model,
        latency_ms,
        usage[0],
        usage[1],
        failed_over_from or "-",
    )
    path = os.getenv("LLM_CALL_LOG")
    if path:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with _lock, open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError as exc:  # logging must never break verification
            logger.warning("Could not write LLM call log: %s", exc)


def get_call_log() -> list[dict]:
    """All recorded calls since start-up (or the last reset)."""
    with _lock:
        return list(_CALL_LOG)


def reset_call_log() -> None:
    with _lock:
        _CALL_LOG.clear()


def summarize_calls() -> dict[str, dict]:
    """Per provider: number of calls, tokens and average latency. Use it in benchmark reports."""
    totals: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0}
    )
    for entry in get_call_log():
        row = totals[entry["provider"]]
        row["calls"] += 1
        row["input_tokens"] += entry["input_tokens"] or 0
        row["output_tokens"] += entry["output_tokens"] or 0
        row["latency_ms"] += entry["latency_ms"]
    return {
        name: {
            "calls": row["calls"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "avg_latency_ms": round(row["latency_ms"] / row["calls"], 1),
        }
        for name, row in totals.items()
    }


# Talking to the providers (OpenAI-compatible endpoints)
_clients: dict[str, object] = {}


def _get_client(provider: _Resolved):
    """Create SDK clients lazily so imports work without keys or the SDK installed."""
    if provider.name not in _clients:
        from openai import OpenAI

        # Free tiers have per-minute limits; the SDK backs off and retries on 429 before we fail over.
        _clients[provider.name] = OpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
            max_retries=2,
            timeout=60.0,
        )
    return _clients[provider.name]


def _extract_json(text: str) -> str:
    """Models without strict JSON mode sometimes wrap the answer in ```json fences."""
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def _call_openai_compatible(
    provider: _Resolved,
    system: str,
    user: str,
    schema: type[T],
    max_tokens: int,
    temperature: float,
):
    extra = {}
    if os.getenv("LLM_JSON_MODE", "on").lower() != "off":
        extra["response_format"] = {"type": "json_object"}
    response = _get_client(provider).chat.completions.create(
        model=provider.model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "system",
                # The word JSON must appear in the prompt for JSON mode on some providers.
                "content": f"{system}\n\nRespond with a single JSON object that follows this JSON Schema:\n{json.dumps(schema.model_json_schema())}",
            },
            {"role": "user", "content": user},
        ],
        **extra,
    )
    usage = getattr(response, "usage", None)
    counts = (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )
    text = response.choices[0].message.content or ""
    if not text.strip():
        raise LLMOutputError("The model returned an empty answer.")
    return (
        schema.model_validate_json(_extract_json(text)),
        counts,
    )  # ValidationError is a ValueError


# Public function
def call_structured(
    system: str,
    user: str,
    schema: type[T],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.0,
    provider: str | None = None,
) -> T:
    """Ask an LLM for output matching ``schema`` and return a validated instance.

    ``provider`` pins this call to one provider (no failover). Raises ``LLMOutputError`` or
    ``pydantic.ValidationError`` (both ValueErrors) for unusable output so agents can retry, and
    ``AllProvidersFailedError`` when no provider is available.
    """
    chain, pinned = _chain(provider)
    errors: list[tuple[str, Exception]] = []

    for candidate in _order(chain, pinned):
        started = _now()
        try:
            result, usage = _call_openai_compatible(
                candidate, system, user, schema, max_tokens, temperature
            )
        except Exception as exc:
            if not _is_failover_error(exc):
                raise
            errors.append((candidate.name, exc))
            if not pinned:
                _start_cooldown(candidate.name, exc)
            logger.warning(
                "llm_failover provider=%s reason=%s: %s",
                candidate.name,
                type(exc).__name__,
                exc,
            )
            continue
        _record(
            candidate,
            int((_now() - started) * 1000),
            usage,
            [name for name, _ in errors],
        )
        return result

    raise AllProvidersFailedError(errors) from errors[-1][1]
