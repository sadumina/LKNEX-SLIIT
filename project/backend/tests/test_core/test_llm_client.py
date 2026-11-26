"""Network-free tests for provider selection, failover, and call accounting."""

import pytest
from pydantic import BaseModel

from app.core import llm_client


class _Response(BaseModel):
    value: str


class _RateLimitError(Exception):
    status_code = 429


def _clear_provider_environment(monkeypatch):
    names = {
        "LLM_PIN_PROVIDER",
        "LLM_PROVIDERS",
        "GROQ_API_KEY",
        "LLM_KEY_GROQ",
        "LLM_key_Groq",
        "GROQ_MODEL",
        "GEMINI_API_KEY",
        "LLM_KEY_GEMINI",
        "LLM_Key_OpenAI",
        "LLM_KEY_OPENAI",
        "GEMINI_MODEL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
    }
    for name in names:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _reset_client_state():
    llm_client.reset_call_log()
    llm_client._cooldown_until.clear()
    yield
    llm_client.reset_call_log()
    llm_client._cooldown_until.clear()


def test_chain_skips_misconfigured_provider_and_uses_valid_fallback(monkeypatch):
    _clear_provider_environment(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDERS", "groq,gemini")
    monkeypatch.setenv("LLM_KEY_GROQ", "fictional-groq-key")
    monkeypatch.setenv("LLM_KEY_GEMINI", "fictional-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "fictional-gemini-model")

    chain, pinned = llm_client._chain(None)

    assert [provider.name for provider in chain] == ["gemini"]
    assert pinned is False


def test_pinned_misconfigured_provider_fails_clearly(monkeypatch):
    _clear_provider_environment(monkeypatch)
    monkeypatch.setenv("LLM_PIN_PROVIDER", "groq")
    monkeypatch.setenv("LLM_KEY_GROQ", "fictional-groq-key")

    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        llm_client._chain(None)


def test_rate_limit_fails_over_and_records_success(monkeypatch):
    groq = llm_client._Resolved("groq", "openai", "key-1", "model-1", "https://groq.invalid")
    gemini = llm_client._Resolved(
        "gemini", "openai", "key-2", "model-2", "https://gemini.invalid"
    )
    monkeypatch.setattr(llm_client, "_chain", lambda provider: ([groq, gemini], False))
    monkeypatch.setattr(llm_client, "_order", lambda chain, pinned: chain)

    calls = []

    def fake_call(provider, system, user, schema, max_tokens, temperature):
        calls.append(provider.name)
        if provider.name == "groq":
            raise _RateLimitError("rate limited")
        return _Response(value="ok"), (12, 4)

    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)

    result = llm_client.call_structured("system", "user", _Response)

    assert result.value == "ok"
    assert calls == ["groq", "gemini"]
    log = llm_client.get_call_log()
    assert log[0]["provider"] == "gemini"
    assert log[0]["failed_over_from"] == ["groq"]
    assert llm_client.summarize_calls()["gemini"]["input_tokens"] == 12


def test_invalid_output_does_not_fail_over(monkeypatch):
    groq = llm_client._Resolved("groq", "openai", "key-1", "model-1", "https://groq.invalid")
    gemini = llm_client._Resolved(
        "gemini", "openai", "key-2", "model-2", "https://gemini.invalid"
    )
    monkeypatch.setattr(llm_client, "_chain", lambda provider: ([groq, gemini], False))
    monkeypatch.setattr(llm_client, "_order", lambda chain, pinned: chain)
    calls = []

    def invalid_call(provider, system, user, schema, max_tokens, temperature):
        calls.append(provider.name)
        raise llm_client.LLMOutputError("invalid structured output")

    monkeypatch.setattr(llm_client, "_call_openai_compatible", invalid_call)

    with pytest.raises(llm_client.LLMOutputError):
        llm_client.call_structured("system", "user", _Response)

    assert calls == ["groq"]
    assert llm_client.get_call_log() == []


def test_markdown_fenced_json_is_extracted():
    assert llm_client._extract_json('```json\n{"value": "ok"}\n```') == '{"value": "ok"}'
