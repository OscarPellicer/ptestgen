import subprocess
import sys
from pathlib import Path

from ptestgen import artifacts
from ptestgen.schemas import QuestionContent, QuestionRecord, QuestionStageContent

REPO_ROOT = Path(__file__).resolve().parents[1]

OPEN_QUESTION_MD = """## open_1 {type=open_answer points=2 lines=8.5}
Explain regularization.

**Expected answer:**
It penalizes overly complex models.

**Rubric:**
Award points for penalty and generalization.

## mc_1
What is 2 + 2?
 * 4
 * 3
 * 5
 * 22
"""


def test_artifacts_parse_fractional_answer_lines(tmp_path):
    md_path = tmp_path / "questions.md"
    md_path.write_text(OPEN_QUESTION_MD, encoding="utf-8")

    questions = artifacts.read_questions_md(str(md_path))

    assert questions["open_1"].answer_lines == 8.5


def test_artifacts_round_trip_fractional_answer_lines(tmp_path):
    md_path = tmp_path / "questions.md"
    tsv_path = tmp_path / "questions.tsv"
    records = [
        QuestionRecord(
            question_id=question_id,
            final=QuestionStageContent(
                content=QuestionContent(text="Explain regularization.", question_type="open_answer", answer_lines=lines)
            ),
        )
        for question_id, lines in (("half", 8.5), ("whole", 8))
    ]

    artifacts.write_artifacts(records, str(md_path), str(tsv_path))
    md_text = md_path.read_text(encoding="utf-8")
    from_tsv = {rec.question_id: rec.get_latest_content().answer_lines for rec in artifacts.read_metadata_tsv(str(tsv_path))}
    from_md = {qid: content.answer_lines for qid, content in artifacts.read_questions_md(str(md_path)).items()}

    assert "lines=8.5" in md_text
    assert "lines=8}" in md_text or "lines=8 " in md_text  # whole numbers are written without ".0"
    assert from_tsv == {"half": 8.5, "whole": 8}
    assert from_md == {"half": 8.5, "whole": 8}


def test_export_creates_metadata_tsv_from_hand_written_markdown(tmp_path):
    md_path = tmp_path / "exam.md"
    # Whole lines: fractional values need pexams > 0.12.2, the version CI installs from PyPI.
    md_path.write_text(OPEN_QUESTION_MD.replace("lines=8.5", "lines=8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"), "export", "gift", str(md_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    tsv_path = tmp_path / "exam.tsv"
    assert tsv_path.exists()
    records = {rec.question_id: rec for rec in artifacts.read_metadata_tsv(str(tsv_path))}
    assert set(records) == {"open_1", "mc_1"}
    assert records["open_1"].get_latest_content().answer_lines == 8
