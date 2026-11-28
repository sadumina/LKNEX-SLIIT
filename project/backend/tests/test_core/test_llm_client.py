# Purpose of this file is to test provider failover, cooldown, pinning, key aliases, configuration handling and call logging of the LLM client without any real API
import json
from types import SimpleNamespace

import pytest

from app.core import llm_client
from app.schemas.verification import ExtractionResult

GOOD = '{"claims": [{"text": "Items must be unused."}]}'

ALL_ENV = [
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
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_PROVIDERS",
    "LLM_PIN_PROVIDER",
    "LLM_COOLDOWN_SECONDS",
    "LLM_JSON_MODE",
    "LLM_CALL_LOG",
]


class HttpError(Exception):
    """Looks like an SDK error: has a status_code."""

    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


class FakeOpenAI:
    """Stands in for the OpenAI SDK client. ``script`` items are answer texts or exceptions."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_MODEL", "groq-model")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-model")
    llm_client._clients.clear()
    llm_client._cooldown_until.clear()
    llm_client.reset_call_log()
    yield
    llm_client._clients.clear()
    llm_client._cooldown_until.clear()
    llm_client.reset_call_log()


def _install(groq=None, gemini=None):
    if groq is not None:
        llm_client._clients["groq"] = groq
    if gemini is not None:
        llm_client._clients["gemini"] = gemini


def _call(**kwargs):
    return llm_client.call_structured("system", "user", ExtractionResult, **kwargs)


# ----------------------------- normal use ----------------------------- #
def test_first_provider_answers_and_the_call_is_logged():
    groq, gemini = FakeOpenAI([GOOD]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    assert _call().claims[0].text == "Items must be unused."
    assert len(groq.calls) == 1 and gemini.calls == []
    entry = llm_client.get_call_log()[0]
    assert entry["provider"] == "groq" and entry["model"] == "groq-model"
    assert (
        entry["input_tokens"] == 100
        and entry["output_tokens"] == 20
        and entry["failed_over_from"] == []
    )
    assert groq.calls[0]["model"] == "groq-model"
    assert groq.calls[0]["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in groq.calls[0]["messages"][0]["content"]


def test_fenced_json_is_accepted_and_json_mode_can_be_switched_off(monkeypatch):
    groq = FakeOpenAI(["Sure:\n```json\n" + GOOD + "\n```"])
    _install(groq, FakeOpenAI([GOOD]))
    monkeypatch.setenv("LLM_JSON_MODE", "off")
    assert _call().claims[0].text == "Items must be unused."
    assert "response_format" not in groq.calls[0]


def test_extract_json_strips_markdown_fences_and_leaves_plain_json_alone():
    assert (
        llm_client._extract_json('```json\n{"value": "ok"}\n```') == '{"value": "ok"}'
    )
    assert llm_client._extract_json('  {"value": "ok"}  ') == '{"value": "ok"}'


# ------------------------------ failover ------------------------------ #
def test_rate_limit_fails_over_to_the_next_provider_and_logs_it():
    groq, gemini = FakeOpenAI([HttpError(429)]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    assert _call().claims[0].text == "Items must be unused."
    entry = llm_client.get_call_log()[0]
    assert entry["provider"] == "gemini" and entry["failed_over_from"] == ["groq"]


@pytest.mark.parametrize(
    "error",
    [HttpError(401), HttpError(503), TimeoutError("slow"), ConnectionError("down")],
)
def test_outages_timeouts_and_bad_keys_fail_over(error):
    _install(FakeOpenAI([error]), FakeOpenAI([GOOD]))
    assert _call().claims
    assert llm_client.get_call_log()[0]["provider"] == "gemini"


def test_sdk_network_error_by_class_name_fails_over():
    class APIConnectionError(Exception):
        pass

    _install(FakeOpenAI([APIConnectionError("no route")]), FakeOpenAI([GOOD]))
    assert _call().claims


def test_bad_request_is_not_hidden_by_failover():
    groq, gemini = FakeOpenAI([HttpError(400)]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    with pytest.raises(HttpError):
        _call()
    assert gemini.calls == []


def test_invalid_output_raises_value_error_and_does_not_fail_over():
    groq, gemini = FakeOpenAI(["not json"]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    with pytest.raises(ValueError):
        _call()
    assert gemini.calls == []
    _install(FakeOpenAI(["   "]))
    with pytest.raises(ValueError):
        _call()
    assert llm_client.get_call_log() == []  # failed calls are not recorded as successes


def test_all_providers_failing_raises_a_clear_error():
    _install(FakeOpenAI([HttpError(429)]), FakeOpenAI([HttpError(503)]))
    with pytest.raises(llm_client.AllProvidersFailedError) as info:
        _call()
    assert [name for name, _ in info.value.errors] == ["groq", "gemini"]
    assert not isinstance(info.value, ValueError)  # agents must not retry this one


# ------------------------------ cooldown ------------------------------ #
def test_rate_limited_provider_is_skipped_until_the_cooldown_ends(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(llm_client, "_now", lambda: clock["t"])
    groq, gemini = FakeOpenAI([HttpError(429), GOOD]), FakeOpenAI([GOOD])
    _install(groq, gemini)

    _call()  # groq 429 -> gemini
    assert len(groq.calls) == 1 and len(gemini.calls) == 1
    _call()  # groq is cooling down: straight to gemini
    assert len(groq.calls) == 1 and len(gemini.calls) == 2
    clock["t"] += 61  # cooldown over
    _call()
    assert len(groq.calls) == 2 and len(gemini.calls) == 2
    assert llm_client.get_call_log()[-1]["provider"] == "groq"


def test_a_cooling_provider_is_still_tried_as_a_last_resort(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(llm_client, "_now", lambda: clock["t"])
    groq, gemini = FakeOpenAI([HttpError(429), GOOD]), FakeOpenAI([HttpError(503)])
    _install(groq, gemini)
    with pytest.raises(llm_client.AllProvidersFailedError):
        _call()
    assert _call().claims  # both cooling, groq tried again and now works
    assert llm_client.get_call_log()[-1]["provider"] == "groq"


# ------------------------------- pinning ------------------------------- #
def test_pinned_provider_never_fails_over(monkeypatch):
    monkeypatch.setenv("LLM_PIN_PROVIDER", "groq")
    groq, gemini = FakeOpenAI([HttpError(429)]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    with pytest.raises(llm_client.AllProvidersFailedError):
        _call()
    assert gemini.calls == []


def test_provider_argument_pins_one_call():
    groq, gemini = FakeOpenAI([GOOD]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    _call(provider="gemini")
    assert groq.calls == [] and llm_client.get_call_log()[0]["provider"] == "gemini"


def test_pinning_a_provider_without_a_key_is_an_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _call(provider="gemini")


def test_pinned_misconfigured_provider_fails_clearly(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL")  # key present, model missing
    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        _call(provider="groq")


# --------------------------- configuration --------------------------- #
def test_the_team_key_names_work_as_aliases(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("LLM_key_Groq", "g1")
    monkeypatch.setenv("LLM_Key_OpenAI", "g2")
    chain, pinned = llm_client._chain(None)
    assert [p.name for p in chain] == ["groq", "gemini"] and not pinned
    assert chain[0].api_key == "g1" and chain[1].api_key == "g2"


def test_provider_without_a_key_is_skipped_and_order_can_be_changed(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    assert [p.name for p in llm_client._chain(None)[0]] == ["gemini"]
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDERS", "gemini,groq")
    assert [p.name for p in llm_client._chain(None)[0]] == ["gemini", "groq"]


def test_no_keys_at_all_gives_a_helpful_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        _call()


def test_misconfigured_provider_is_skipped_and_fallback_is_used(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL")  # key present, model missing -> groq is skipped
    groq, gemini = FakeOpenAI([GOOD]), FakeOpenAI([GOOD])
    _install(groq, gemini)
    chain, pinned = llm_client._chain(None)
    assert [p.name for p in chain] == ["gemini"] and not pinned
    assert _call().claims
    assert groq.calls == [] and len(gemini.calls) == 1


def test_unknown_provider_name_is_rejected_even_if_a_valid_one_remains(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "groq,nonsense")
    groq = FakeOpenAI([GOOD])
    _install(groq, FakeOpenAI([GOOD]))
    with pytest.raises(RuntimeError, match="nonsense"):
        _call()
    assert groq.calls == []


def test_only_unknown_provider_names_gives_a_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "nonsense")
    with pytest.raises(RuntimeError, match="nonsense"):
        _call()


# ------------------------------ logging ------------------------------ #
def test_summary_and_jsonl_call_log(monkeypatch, tmp_path):
    log_file = tmp_path / "logs" / "llm_calls.jsonl"
    monkeypatch.setenv("LLM_CALL_LOG", str(log_file))
    _install(FakeOpenAI([GOOD]), FakeOpenAI([GOOD]))
    _call()
    _call()
    summary = llm_client.summarize_calls()
    assert (
        summary["groq"]["calls"] == 2
        and summary["groq"]["input_tokens"] == 200
        and summary["groq"]["output_tokens"] == 40
    )
    lines = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert len(lines) == 2 and lines[0]["provider"] == "groq" and "time" in lines[0]
