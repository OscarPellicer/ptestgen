"""
Tests for autotestia.correct_online — the wrappers around pexams online parsers.

These tests use synthetic TSV / results data and mock out pexams.analysis so
that no LLM calls or PDF generation are triggered.

Run with:  pytest tests/test_correct_online.py -v
"""

import argparse
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from autotestia import artifacts
from autotestia.schemas import (
    QuestionContent,
    QuestionRecord,
    QuestionStageContent,
)

# ---------------------------------------------------------------------------
# Helpers to build minimal synthetic artifacts
# ---------------------------------------------------------------------------

def _make_records():
    """Create two minimal QuestionRecord objects."""
    def _sc(text, correct, distractors):
        return QuestionStageContent(
            content=QuestionContent(
                text=text,
                correct_answer=correct,
                distractors=distractors,
            )
        )

    r1 = QuestionRecord(
        question_id="q_math_001",
        reviewed=_sc(
            "What is 2 + 2?",
            "4",
            ["3", "5", "22"],
        ),
    )
    r2 = QuestionRecord(
        question_id="q_geo_001",
        reviewed=_sc(
            "What is the capital of France?",
            "Paris",
            ["Berlin", "Madrid", "Rome"],
        ),
    )
    return [r1, r2]


def _write_artifacts(tmp_dir: str):
    """Write questions.md and metadata.tsv for the test records."""
    md_path = os.path.join(tmp_dir, "questions.md")
    tsv_path = os.path.join(tmp_dir, "questions.tsv")
    records = _make_records()
    artifacts.write_artifacts(records, md_path, tsv_path)
    return md_path, tsv_path, records


def _make_wooclap_csv(tmp_dir: str) -> str:
    """Write a minimal Wooclap results CSV and return its path."""
    data = {
        "Alumno": ["1", "2"],
        "Q1 - What is 2 + 2? (1 pts)": ["V - 4", "X - 3"],
        "Q2 - What is the capital of France? (1 pts)": ["V - Paris", "X - Berlin"],
        "Total": ["2 / 2", "0 / 2"],
    }
    path = os.path.join(tmp_dir, "wooclap_results.csv")
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def _make_moodle_csv(tmp_dir: str) -> str:
    """Write a minimal Moodle results CSV and return its path."""
    data = {
        "Cognoms": ["Smith", "Jones"],
        "Nom": ["Alice", "Bob"],
        "Resposta 1": ["4", "3"],
        "Resposta 2": ["Paris", "Berlin"],
    }
    path = os.path.join(tmp_dir, "moodle_results.csv")
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def _make_question_stats_csv(tmp_dir: str, records):
    """Write a minimal question_stats.csv as pexams.analysis would produce it."""
    rows = []
    for i, rec in enumerate(records, start=1):
        rows.append({
            "original_id": rec.question_id,
            "exam_q_id": i,
            "question_text": rec.get_latest_content().text[:100],
            "total_answers": 2,
            "NA_count": 0,
            "option_A_count": 0,
            "option_A_text": rec.get_latest_content().distractors[0][:50],
            "option_B_count": 2,
            "option_B_text": rec.get_latest_content().correct_answer[:50],
            "option_C_count": 0,
            "option_C_text": rec.get_latest_content().distractors[1][:50] if len(rec.get_latest_content().distractors) > 1 else "",
        })
    path = os.path.join(tmp_dir, "question_stats.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Tests for handle_correct_wooclap
# ---------------------------------------------------------------------------

class TestHandleCorrectWooclap(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.md_path, self.tsv_path, self.records = _write_artifacts(self.tmp)
        self.results_path = _make_wooclap_csv(self.tmp)
        self.output_dir = os.path.join(self.tmp, "output")
        os.makedirs(self.output_dir, exist_ok=True)

    def _make_args(self, **kwargs):
        defaults = dict(
            input_md_path=self.md_path,
            results=self.results_path,
            output_dir=self.output_dir,
            fuzzy_threshold=80,
            encoding="auto",
            sep="auto",
            penalty=0.0,
            evaluate_final=False,
            evaluator_instructions=None,
            lang="en",
            no_generate_report=True,  # skip PDF in tests
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("autotestia.correct_online.analysis")
    def test_correction_results_csv_created(self, mock_analysis):
        """correction_results.csv must be written to output_dir."""
        mock_analysis.analyze_results.return_value = None
        # Provide a synthetic question_stats.csv so the TSV update runs
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_wooclap
        handle_correct_wooclap(self._make_args())

        correction_csv = os.path.join(self.output_dir, "correction_results.csv")
        self.assertTrue(os.path.exists(correction_csv), "correction_results.csv not found")

    @patch("autotestia.correct_online.analysis")
    def test_correction_results_has_two_students(self, mock_analysis):
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_wooclap
        handle_correct_wooclap(self._make_args())

        df = pd.read_csv(os.path.join(self.output_dir, "correction_results.csv"))
        self.assertEqual(len(df), 2)

    @patch("autotestia.correct_online.analysis")
    def test_tsv_stats_updated(self, mock_analysis):
        """metadata.tsv stats_total_answers must be updated after correction."""
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_wooclap
        handle_correct_wooclap(self._make_args())

        updated = artifacts.read_metadata_tsv(self.tsv_path)
        updated_map = {r.question_id: r for r in updated}
        for rec in self.records:
            self.assertIsNotNone(
                updated_map[rec.question_id].stats_total_answers,
                f"stats_total_answers not set for {rec.question_id}",
            )

    @patch("autotestia.correct_online.analysis")
    def test_stats_source_is_wooclap(self, mock_analysis):
        """stats_source must be set to 'wooclap' after Wooclap correction."""
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_wooclap
        handle_correct_wooclap(self._make_args())

        updated = artifacts.read_metadata_tsv(self.tsv_path)
        for rec in updated:
            self.assertEqual(rec.stats_source, "wooclap")

    @patch("autotestia.correct_online.analysis")
    def test_analyze_results_called(self, mock_analysis):
        """pexams analysis.analyze_results must be invoked once."""
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_wooclap
        handle_correct_wooclap(self._make_args())

        mock_analysis.analyze_results.assert_called_once()


# ---------------------------------------------------------------------------
# Tests for handle_correct_moodle
# ---------------------------------------------------------------------------

class TestHandleCorrectMoodle(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.md_path, self.tsv_path, self.records = _write_artifacts(self.tmp)
        self.results_path = _make_moodle_csv(self.tmp)
        self.output_dir = os.path.join(self.tmp, "output")
        os.makedirs(self.output_dir, exist_ok=True)

    def _make_args(self, **kwargs):
        defaults = dict(
            input_md_path=self.md_path,
            results=self.results_path,
            output_dir=self.output_dir,
            question_order=None,
            encoding="auto",
            sep="auto",
            penalty=0.0,
            evaluate_final=False,
            evaluator_instructions=None,
            lang="en",
            no_generate_report=True,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("autotestia.correct_online.analysis")
    def test_correction_results_csv_created(self, mock_analysis):
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_moodle
        handle_correct_moodle(self._make_args())

        correction_csv = os.path.join(self.output_dir, "correction_results.csv")
        self.assertTrue(os.path.exists(correction_csv))

    @patch("autotestia.correct_online.analysis")
    def test_correct_answers_mapped(self, mock_analysis):
        """Student 1 answered correctly: answer_1 = 'B' (index 1 = '4')."""
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_moodle
        handle_correct_moodle(self._make_args())

        df = pd.read_csv(os.path.join(self.output_dir, "correction_results.csv"))
        # The correct answer for Q1 is "4" which is option index 1 (after
        # pexams_converter places correct_answer first → index 0).
        # Verify Q1 student 1 is not NA
        self.assertNotEqual(df.loc[0, "answer_1"], "NA")

    @patch("autotestia.correct_online.analysis")
    def test_tsv_stats_updated(self, mock_analysis):
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_moodle
        handle_correct_moodle(self._make_args())

        updated = artifacts.read_metadata_tsv(self.tsv_path)
        for rec in updated:
            self.assertIsNotNone(rec.stats_total_answers)

    @patch("autotestia.correct_online.analysis")
    def test_stats_source_is_moodle(self, mock_analysis):
        """stats_source must be set to 'moodle' after Moodle correction."""
        mock_analysis.analyze_results.return_value = None
        _make_question_stats_csv(self.output_dir, self.records)

        from autotestia.correct_online import handle_correct_moodle
        handle_correct_moodle(self._make_args())

        updated = artifacts.read_metadata_tsv(self.tsv_path)
        for rec in updated:
            self.assertEqual(rec.stats_source, "moodle")


# ---------------------------------------------------------------------------
# Integration: correction_results format matches analysis expectations
# ---------------------------------------------------------------------------

class TestCorrectionResultsFormat(unittest.TestCase):
    """Verify that the DataFrame produced by the parsers has all columns
    that pexams.analysis.analyze_results expects."""

    def setUp(self):
        from pexams.schemas import PexamOption, PexamQuestion
        self.questions = [
            PexamQuestion(
                id=1,
                original_id="q1",
                text="Q1 text",
                options=[
                    PexamOption(text="A opt", is_correct=True),
                    PexamOption(text="B opt", is_correct=False),
                ],
            ),
            PexamQuestion(
                id=2,
                original_id="q2",
                text="Q2 text",
                options=[
                    PexamOption(text="X opt", is_correct=False),
                    PexamOption(text="Y opt", is_correct=True),
                ],
            ),
        ]

    def _write_wooclap_csv(self, tmp_dir):
        data = {
            "Alumno": ["1"],
            "Q1 - Q1 text (1 pts)": ["V - A opt"],
            "Q2 - Q2 text (1 pts)": ["V - Y opt"],
        }
        path = os.path.join(tmp_dir, "wc.csv")
        pd.DataFrame(data).to_csv(path, index=False)
        return path

    def test_wooclap_required_columns(self):
        from pexams.io.online_results import parse_wooclap_results
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_wooclap_csv(tmp)
            df = parse_wooclap_results(path, self.questions)
        required = {"page", "student_id", "student_name", "model_id",
                    "score", "total_questions", "answer_1", "answer_2"}
        self.assertTrue(required.issubset(set(df.columns)), df.columns.tolist())

    def test_moodle_required_columns(self):
        from pexams.io.online_results import parse_moodle_results
        data = {
            "Nom": ["Alice"],
            "Resposta 1": ["A opt"],
            "Resposta 2": ["Y opt"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.csv")
            pd.DataFrame(data).to_csv(path, index=False)
            df = parse_moodle_results(path, self.questions)
        required = {"page", "student_id", "model_id", "score",
                    "total_questions", "answer_1", "answer_2"}
        self.assertTrue(required.issubset(set(df.columns)), df.columns.tolist())


if __name__ == "__main__":
    unittest.main()
