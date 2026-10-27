import pytest

from ptestgen.agents.reviewer import review_corrupts_characters
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


def test_synchronize_follows_markdown_order():
    from ptestgen import artifacts
    from ptestgen.schemas import QuestionRecord, QuestionStageContent

    def content(name):
        return mc(name, "correcta", ["a", "b", "c"])

    records = [QuestionRecord(question_id=q, generated=QuestionStageContent(content=content(q))) for q in ["q1", "q2", "q3"]]
    md_questions = {"q3": content("q3"), "new_b": content("new_b"), "q1": content("q1"), "new_a": content("new_a")}
    synced = artifacts.synchronize_artifacts(records, md_questions)
    assert [record.question_id for record in synced] == ["q3", "new_b", "q1", "new_a", "q2"]
