import importlib
import time

import pytest

from ptestgen import config
from ptestgen.agents.reviewer import review_corrupts_characters
from ptestgen.llm_providers.base import LLMProvider
from ptestgen.schemas import QuestionContent


def mc(text, correct, distractors):
    return QuestionContent(text=text, correct_answer=correct, distractors=distractors)


ORIGINAL = mc(
    "En el cálculo de la distancia mínima de edición, ¿por qué la sustitución cuesta 2?",
    "Porque equivale a un borrado más una inserción",
    ["Porque altera la morfología", "Porque penaliza errores tipográficos", "Porque evalúa dos celdas"],
)


@pytest.mark.parametrize(
    "text",
    [
        "En el clculo de la distancia mnima de edicin, por qu la sustitucin cuesta 2?",
        "En el c#lculo de la distancia m&nima de edici#n, ¿por qu# la sustituci#n cuesta 2?",
        "·¡En el cálculo de la distancia mínima de edición, ¿por qué la sustitución cuesta 2?",
    ],
)
def test_detects_corrupted_review(text):
    reviewed = ORIGINAL.model_copy(update={"text": text})
    assert review_corrupts_characters(ORIGINAL, reviewed)


def test_detects_wrong_diacritic():
    original = mc("¿Qué método se usa?", "Se emplea el último estado oculto", ["a", "b", "c"])
    reviewed = mc("¿Qué método se usa?", "Se emplea el ùltimo estado oculto", ["a", "b", "c"])
    assert review_corrupts_characters(original, reviewed)


def test_accepts_legitimate_edits():
    reviewed = ORIGINAL.model_copy(update={
        "text": "Al calcular la distancia mínima de edición, ¿por qué la sustitución tiene un coste de 2?",
        "distractors": ["Porque altera la morfología léxica", "Porque penaliza errores", "Porque evalúa dos celdas contiguas"],
    })
    assert not review_corrupts_characters(ORIGINAL, reviewed)


def test_api_keys_are_cleaned(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", '"sk-or-v1-abc"\r')
    reloaded = importlib.reload(config)
    try:
        assert reloaded.OPENROUTER_API_KEY == "sk-or-v1-abc"
    finally:
        monkeypatch.delenv("OPENROUTER_API_KEY")
        importlib.reload(config)


class _DummyProvider(LLMProvider):
    def _initialize_client(self):
        return None

    def generate_questions_from_text(self, *args, **kwargs):
        return None

    def generate_question_from_image(self, *args, **kwargs):
        return None

    def review_question(self, *args, **kwargs):
        return None

    def evaluate_question(self, *args, **kwargs):
        return None


def test_hard_timeout_retries_hung_calls(monkeypatch):
    monkeypatch.setattr(config, "LLM_HARD_TIMEOUT", 0.2)
    monkeypatch.setattr(config, "RETRY_DELAY_BASE", 0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            time.sleep(5)  # simulates a response that never finishes
        return "ok"

    provider = _DummyProvider("dummy", {})
    start = time.time()
    assert provider._call_llm_with_retry(flaky) == "ok"
    assert len(calls) == 2
    assert time.time() - start < 3


def test_synchronize_follows_markdown_order():
    from ptestgen import artifacts
    from ptestgen.schemas import QuestionRecord, QuestionStageContent

    def content(name):
        return mc(name, "correcta", ["a", "b", "c"])

    records = [QuestionRecord(question_id=q, generated=QuestionStageContent(content=content(q))) for q in ["q1", "q2", "q3"]]
    md_questions = {"q3": content("q3"), "new_b": content("new_b"), "q1": content("q1"), "new_a": content("new_a")}
    synced = artifacts.synchronize_artifacts(records, md_questions)
    assert [record.question_id for record in synced] == ["q3", "new_b", "q1", "new_a", "q2"]
