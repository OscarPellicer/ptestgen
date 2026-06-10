from ptestgen import artifacts
from ptestgen.agents.generator import QuestionGenerator
from ptestgen.pexams_converter import convert_ptestgen_to_pexam
from ptestgen.schemas import ChangeMetrics, QuestionContent, QuestionRecord, QuestionStageContent


def test_artifacts_parse_open_answer_markdown(tmp_path):
    md_path = tmp_path / "questions.md"
    md_path.write_text(
        """## open_1 {type=open points=4 lines=12}
Explain regularization.

**Expected answer:**
It penalizes overly complex models.

**Rubric:**
Award points for penalty and generalization.
""",
        encoding="utf-8",
    )

    questions = artifacts.read_questions_md(str(md_path))

    assert questions["open_1"].is_open_answer
    assert questions["open_1"].points == 4
    assert questions["open_1"].answer_lines == 12
    assert "penalizes" in questions["open_1"].expected_answer
    assert "Award points" in questions["open_1"].rubric

def test_generator_stub_can_generate_open_answer_questions():
    generator = QuestionGenerator(llm_provider="stub")

    records = generator.generate_questions_from_text(
        text_content=None,
        custom_instructions="Create open answer questions about regularization.",
        num_questions=2,
        question_type="open_answer",
    )

    assert len(records) == 2
    assert all(record.get_latest_content().is_open_answer for record in records)
    assert all(record.get_latest_content().expected_answer for record in records)
    assert all(record.get_latest_content().rubric for record in records)


def test_generator_stub_can_generate_mixed_questions():
    generator = QuestionGenerator(llm_provider="stub")

    records = generator.generate_questions_from_text(
        text_content=None,
        custom_instructions="Create mixed questions.",
        num_questions=4,
        question_type="mixed",
    )

    types = [record.get_latest_content().question_type for record in records]
    assert "multiple_choice" in types
    assert "open_answer" in types


def test_artifacts_round_trip_open_answer_metadata(tmp_path):
    md_path = tmp_path / "questions.md"
    tsv_path = tmp_path / "questions.tsv"
    records = [
        QuestionRecord(
            question_id="open_1",
            final=QuestionStageContent(
                content=QuestionContent(
                    text="Explain regularization.",
                    question_type="open_answer",
                    points=4,
                    expected_answer="It penalizes overly complex models.",
                    rubric="Award points for penalty and generalization.",
                    answer_lines=12,
                )
            ),
        )
    ]

    artifacts.write_artifacts(records, str(md_path), str(tsv_path))
    loaded = artifacts.read_metadata_tsv(str(tsv_path))
    md_questions = artifacts.read_questions_md(str(md_path))

    assert loaded[0].get_latest_content().is_open_answer
    assert loaded[0].get_latest_content().rubric == records[0].get_latest_content().rubric
    assert md_questions["open_1"].is_open_answer


def test_convert_open_answer_to_pexams_question(tmp_path):
    input_md = tmp_path / "questions.md"
    input_md.write_text("", encoding="utf-8")
    records = [
        QuestionRecord(
            question_id="open_1",
            final=QuestionStageContent(
                content=QuestionContent(
                    text="Explain regularization.",
                    question_type="open_answer",
                    points=4,
                    expected_answer="It penalizes overly complex models.",
                    rubric="Award points for penalty and generalization.",
                    answer_lines=12,
                )
            ),
        )
    ]

    questions = convert_ptestgen_to_pexam(records, str(input_md))

    assert len(questions) == 1
    assert questions[0].question_type == "open_answer"
    assert questions[0].points == 4
    assert questions[0].answer_area.lines == 12
    assert questions[0].original_id == "open_1"


def test_convert_multiple_choice_to_pexams_preserves_points(tmp_path):
    input_md = tmp_path / "questions.md"
    input_md.write_text("", encoding="utf-8")
    records = [
        QuestionRecord(
            question_id="mc_1",
            final=QuestionStageContent(
                content=QuestionContent(
                    text="What is 2 + 2?",
                    points=2.5,
                    correct_answer="4",
                    distractors=["3", "5"],
                )
            ),
        )
    ]

    questions = convert_ptestgen_to_pexam(records, str(input_md))

    assert questions[0].points == 2.5


def test_synchronize_artifacts_marks_deleted_manual_addition_as_removed():
    manual_only = QuestionRecord(
        question_id="cm_97098756",
        source_material="manual_addition",
        final=QuestionStageContent(
            content=QuestionContent(
                text="According to the confusion matrix, what is the accuracy?",
                correct_answer="54/61",
                distractors=["23/61", "31/61", "Cannot be determined"],
            )
        ),
        changes_rev_to_man=ChangeMetrics(status="added"),
    )

    synced = artifacts.synchronize_artifacts([manual_only], {})

    assert len(synced) == 1
    assert synced[0].changes_rev_to_man is not None
    assert synced[0].changes_rev_to_man.status == "removed"
    assert artifacts.is_question_removed(synced[0])



