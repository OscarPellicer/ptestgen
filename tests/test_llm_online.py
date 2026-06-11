import os
from pathlib import Path

import pytest

from ptestgen import artifacts
from ptestgen.pipeline import PTestGenPipeline
from ptestgen.schemas import QuestionStage


def _requires_llm():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("set RUN_LLM_TESTS=1 to run real LLM tests")
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY is required for real LLM tests")


@pytest.mark.llm
def test_generation_review_evaluation_pipeline_with_real_llm(tmp_path):
    _requires_llm()

    model = os.getenv("PTESTGEN_LLM_TEST_MODEL", "google/gemini-3-flash-preview")
    md_path = tmp_path / "questions.md"
    tsv_path = tmp_path / "questions.tsv"
    pipeline = PTestGenPipeline(
        config_override={
            "llm_provider": "openrouter",
            "generator_model": model,
            "reviewer_model": model,
            "evaluator_model": model,
            "use_llm_review": True,
        }
    )

    pipeline.generate(
        input_material_paths=[],
        output_md_path=str(md_path),
        output_tsv_path=str(tsv_path),
        num_questions=2,
        language="English",
        generator_instructions=(
            "Create one multiple-choice question and one open-answer question about "
            "L2 regularization in machine learning."
        ),
        evaluate_initial=True,
        evaluate_reviewed=True,
        question_type="mixed",
    )

    records = artifacts.read_metadata_tsv(str(tsv_path))
    assert len(records) == 2
    assert md_path.exists()
    assert any(record.get_latest_content().is_open_answer for record in records)
    assert any(record.get_latest_content().is_multiple_choice for record in records)
    assert any(record.generated and record.generated.evaluation for record in records)

    pipeline.export(
        records_to_export=records,
        input_md_path=str(md_path),
        output_formats=["none"],
        evaluate_final=True,
    )
    assert all(record.get_latest_content() for record in records)
