import json
from types import SimpleNamespace
from typing import Any, cast

from ptestgen.agents.generator import QuestionGenerator
from ptestgen.llm_providers.openai_compatible import OpenAICompatibleProvider, _prepare_strict_json_schema
from ptestgen.schemas import LLMQuestionList


STRICT_LLM_QUESTION_ITEM_FIELDS = [
    "text",
    "question_type",
    "points",
    "correct_answer",
    "distractors",
    "explanation",
    "expected_answer",
    "rubric",
    "answer_lines",
]


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

    def fake_retry(api_call_func, *args, **kwargs):
        attempts.append(1)
        return api_call_func(*args, **kwargs)

    provider._call_llm_with_retry = fake_retry

    content = provider.generate_questions_from_text(
        system_prompt="system",
        user_prompt="user",
        num_distractors=3,
    )

    assert content is None
    assert len(attempts) == 1


def test_prepare_strict_json_schema_disallows_extra_properties_recursively():
    schema = _prepare_strict_json_schema(LLMQuestionList.model_json_schema())

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["questions"]
    assert schema["$defs"]["LLMQuestionItem"]["additionalProperties"] is False
    assert schema["$defs"]["LLMQuestionItem"]["required"] == STRICT_LLM_QUESTION_ITEM_FIELDS


def test_openai_compatible_provider_uses_strict_schema_for_openrouter():
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.provider = "openrouter"
    provider.model_name = "test-model"

    params = provider._construct_base_params(LLMQuestionList.model_json_schema())

    schema = params["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["questions"]
    assert schema["$defs"]["LLMQuestionItem"]["additionalProperties"] is False
    assert schema["$defs"]["LLMQuestionItem"]["required"] == STRICT_LLM_QUESTION_ITEM_FIELDS

