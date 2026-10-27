"""Structured output in pexams.llm.LLMClient and ptestgen's adapter over it (no network)."""
import json
import time
from types import SimpleNamespace

import pytest

from pexams import llm as shared_llm
from pexams.llm import LLMClient, strict_json_schema
from ptestgen import config
from ptestgen.llm_providers import LLMProvider, get_provider, questions_schema
from ptestgen.schemas import LLMEvaluation, LLMQuestionList

QUESTIONS = {"questions": [{"text": "¿Qué devuelve len([1, 2])?", "correct_answer": "2", "distractors": ["1", "3", "0"]}]}


class _FakeAnthropicStream:
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, iterations=[])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)], usage=usage,
                               model="claude-haiku-5-5", stop_reason="end_turn", _request_id="req_1")


class _FakeAnthropic:
    def __init__(self, text):
        self.calls = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.text = text

    def _stream(self, **params):
        self.calls.append(params)
        return _FakeAnthropicStream(self.text)


class _FakeOpenRouter:
    def __init__(self, text=None, error=None):
        self.calls = []
        self.text, self.error = text, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.calls.append(params)
        if self.error:
            return SimpleNamespace(error=self.error, choices=None)
        choice = SimpleNamespace(message=SimpleNamespace(content=self.text), finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5), model="google/gemini-3.8-flash", id="gen-1")


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 20)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "y" * 20)


# --- pexams.llm ----------------------------------------------------------------------------

def test_strict_json_schema_is_recursive_and_does_not_mutate_input():
    original = LLMQuestionList.model_json_schema()
    snapshot = json.dumps(original, sort_keys=True)
    strict = strict_json_schema(original)
    assert json.dumps(original, sort_keys=True) == snapshot
    assert strict["additionalProperties"] is False and strict["required"] == ["questions"]
    item = strict["$defs"]["LLMQuestionItem"]
    assert item["additionalProperties"] is False
    assert item["required"] == list(item["properties"])


def test_anthropic_json_schema_uses_native_structured_output(keys, tmp_path):
    client = LLMClient("claude-haiku-5-5", effort="low", log_path=str(tmp_path / "llm_calls.jsonl"), tool="ptestgen")
    fake = _FakeAnthropic(json.dumps(QUESTIONS))
    client._client = fake
    text, meta = client.complete("prompt", system="sys", json_schema=questions_schema(3), purpose="generate")
    assert json.loads(text) == QUESTIONS
    params = fake.calls[0]
    assert params["output_config"]["effort"] == "low"
    fmt = params["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert params["messages"][0]["content"][-1]["text"] == "prompt"  # no schema text appended
    assert meta["output_format"] == "json_schema"
    logged = json.loads((tmp_path / "llm_calls.jsonl").read_text().splitlines()[0])
    assert logged["purpose"] == "generate" and logged["model_served"] == "claude-haiku-5-5"


def test_anthropic_without_sdk_support_falls_back_to_instruction(keys, monkeypatch):
    monkeypatch.setattr(shared_llm, "_anthropic_structured_output_supported", lambda: False)
    client = LLMClient("claude-haiku-5-5")
    fake = _FakeAnthropic("Here it is:\n```json\n" + json.dumps(QUESTIONS) + "\n```")
    client._client = fake
    text, meta = client.complete("prompt", json_schema=LLMQuestionList.model_json_schema())
    assert json.loads(text) == QUESTIONS
    assert "format" not in fake.calls[0].get("output_config", {})
    assert "JSON Schema" in fake.calls[0]["messages"][0]["content"][-1]["text"]
    assert meta["output_format"] == "json_instruction"


def test_json_schema_rejects_non_json_answers(keys):
    client = LLMClient("claude-haiku-5-5")
    client._client = _FakeAnthropic("Sorry, no JSON today")
    with pytest.raises(ValueError):
        client.complete("prompt", json_schema=LLMEvaluation.model_json_schema())


def test_openrouter_json_schema_is_strict(keys):
    client = LLMClient("google/gemini-3.8-flash")
    fake = _FakeOpenRouter(json.dumps(QUESTIONS))
    client._client = fake
    text, meta = client.complete("prompt", json_schema=questions_schema(3))
    fmt = fake.calls[0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "LLMQuestionList"
    assert fmt["json_schema"]["schema"]["$defs"]["LLMQuestionItem"]["additionalProperties"] is False
    assert fake.calls[0]["extra_body"] == {"reasoning": {"effort": "minimal"}}
    assert meta["output_format"] == "json_schema"


def test_openrouter_plain_and_json_object_calls_are_unchanged(keys):
    client = LLMClient("google/gemini-3.8-flash")
    fake = _FakeOpenRouter("{}")
    client._client = fake
    client.complete("prompt")
    client.complete("prompt", json_output=True)
    assert "response_format" not in fake.calls[0]
    assert fake.calls[1]["response_format"] == {"type": "json_object"}


def test_openrouter_embedded_error_raises(keys):
    client = LLMClient("google/gemini-3.8-flash")
    client._client = _FakeOpenRouter(error={"message": "Provider returned error", "code": 429})
    with pytest.raises(RuntimeError, match="Provider returned error"):
        client.complete("prompt")


# --- ptestgen adapter ------------------------------------------------------------------------

def test_get_provider_routes_by_model_id_and_key_env(monkeypatch):
    monkeypatch.setitem(config.PROVIDER_API_KEY_MAP, "anthropic", "ANTHROPIC_API_KEY")
    claude = get_provider("anthropic", "claude-haiku-5-5", api_key_env="CLAUDE_KEY", effort="high")
    assert (claude.provider_name, claude.api_key_env, claude.effort) == ("anthropic", "CLAUDE_KEY", "high")
    # A non-Claude model with --provider anthropic goes to OpenRouter with its own key variable.
    gemini = get_provider("anthropic", "google/gemini-3.8-flash", api_key_env="CLAUDE_KEY")
    assert (gemini.provider_name, gemini.api_key_env) == ("openrouter", config.PROVIDER_API_KEY_MAP["openrouter"])
    with pytest.raises(ValueError):
        get_provider("google", "gemini-3.1-pro-preview")


def test_missing_key_fails_once_without_retries(monkeypatch):
    monkeypatch.delenv("PTESTGEN_TEST_MISSING_KEY", raising=False)
    provider = get_provider("anthropic", "claude-haiku-5-5", api_key_env="PTESTGEN_TEST_MISSING_KEY", role="reviewer")
    start = time.time()
    with pytest.raises(RuntimeError, match="PTESTGEN_TEST_MISSING_KEY is not set"):
        provider.review_question("Review {question_json}", "{}")
    assert time.time() - start < 1


def test_hard_timeout_retries_hung_calls(monkeypatch):
    monkeypatch.setattr(config, "LLM_HARD_TIMEOUT", 0.2)
    monkeypatch.setattr(config, "RETRY_DELAY_BASE", 0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            time.sleep(5)  # simulates a response that never finishes
        return "ok"

    provider = LLMProvider("google/gemini-3.8-flash")
    start = time.time()
    assert provider._call_with_retry(flaky) == "ok"
    assert len(calls) == 2
    assert time.time() - start < 3


def test_pipeline_logs_calls_and_writes_manifest(keys, monkeypatch, tmp_path):
    from ptestgen.pipeline import PTestGenPipeline

    review = {"reviewed_question": QUESTIONS["questions"][0]}
    sent = []

    def fake_openrouter(self, prompt, images, system, max_tokens, json_output, json_schema=None, schema_name=""):
        sent.append(json_schema.get("title"))
        text = json.dumps(QUESTIONS if json_schema.get("title") == "LLMQuestionList" else review)
        return text, self.model, "gen-1", "stop", {"input_tokens": 1, "output_tokens": 1}, False

    monkeypatch.setattr(LLMClient, "_openrouter", fake_openrouter)
    pipeline = PTestGenPipeline({"llm_provider": "openrouter", "generator_model": "google/gemini-3.1-pro-preview",
                                 "reviewer_model": "google/gemini-3.8-flash", "evaluator_model": "google/gemini-3.8-flash"})
    out = tmp_path / "out" / "q.md"
    pipeline.generate(None, output_md_path=str(out), output_tsv_path=str(out.with_suffix(".tsv")),
                      num_questions=1, generator_instructions="Python lists")
    assert sent == ["LLMQuestionList", "LLMReview"]
    calls = [json.loads(line) for line in (out.parent / "llm_calls.jsonl").read_text().splitlines()]
    assert [c["purpose"] for c in calls] == ["generate_questions", "review_question"]
    assert all(c["tool"] == "ptestgen" and c["output_format"] == "json_schema" for c in calls)
    manifest = json.loads((out.parent / "run_manifest.json").read_text())
    assert manifest["subcommand"] == "generate"
    assert manifest["llm"]["generator"]["model"] == "google/gemini-3.1-pro-preview"
    assert "len([1, 2])" in out.read_text(encoding="utf-8")
