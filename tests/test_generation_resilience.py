import json
from types import SimpleNamespace
from typing import Any, cast

from ptestgen.agents.generator import QuestionGenerator


def test_generator_trims_extra_distractors():
    generator = QuestionGenerator(llm_provider="stub")

    response_payload = {
        "questions": [
            {
                "text": "Pregunta de prueba",
                "correct_answer": "Correcta",
                "distractors": ["A", "B", "C", "D"],
            }
        ]
    }

    generator.llm_provider_name = "openrouter"
    generator.provider = cast(
        Any,
        SimpleNamespace(
            model_name="test-model",
            generate_questions_from_text=lambda **kwargs: json.dumps(response_payload),
        ),
    )

    records = generator.generate_questions_from_text(
        text_content="texto",
        num_questions=1,
        num_options=4,
        source_material_path="source.md",
    )

    assert len(records) == 1
    assert records[0].generated is not None
    assert records[0].generated.content.distractors == ["A", "B", "C"]


def test_generator_forwards_context_images_to_text_provider():
    generator = QuestionGenerator(llm_provider="stub")
    response_payload = {
        "questions": [
            {
                "text": "Pregunta con contexto visual",
                "correct_answer": "Correcta",
                "distractors": ["A", "B", "C"],
            }
        ]
    }
    calls = []

    def fake_generate_questions_from_text(**kwargs):
        calls.append(kwargs)
        return json.dumps(response_payload)

    generator.llm_provider_name = "openrouter"
    generator.provider = cast(
        Any,
        SimpleNamespace(
            model_name="test-model",
            generate_questions_from_text=fake_generate_questions_from_text,
        ),
    )

    records = generator.generate_questions_from_text(
        text_content="texto",
        num_questions=1,
        num_options=4,
        source_material_path="source.md",
        context_image_paths=["generated/source_assets/figure.png"],
    )

    assert len(records) == 1
    assert calls[0]["image_paths"] == ["generated/source_assets/figure.png"]
