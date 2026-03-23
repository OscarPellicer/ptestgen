import json
from types import SimpleNamespace

from autotestia.agents.generator import QuestionGenerator
from autotestia.llm_providers.openai_compatible import OpenAICompatibleProvider


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
    generator.provider = SimpleNamespace(
        model_name="test-model",
        generate_questions_from_text=lambda **kwargs: json.dumps(response_payload),
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


def test_openai_compatible_provider_returns_none_for_embedded_error():
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.provider = "openrouter"
    provider.model_name = "test-model"
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(error={"message": "Provider returned error", "code": 429})
            )
        )
    )

    attempts = []

    def fake_retry(func, *args, **kwargs):
        attempts.append(1)
        return func(*args, **kwargs)

    provider._call_llm_with_retry = fake_retry

    content = provider.generate_questions_from_text(
        system_prompt="system",
        user_prompt="user",
        num_distractors=3,
    )

    assert content is None
    assert len(attempts) == 1