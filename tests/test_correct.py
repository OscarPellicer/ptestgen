import argparse
import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from ptestgen import artifacts
from ptestgen.correct import handle_correct
from ptestgen.schemas import QuestionContent, QuestionRecord, QuestionStageContent


def _make_records():
    return [
        QuestionRecord(
            question_id="q1",
            reviewed=QuestionStageContent(
                content=QuestionContent(
                    text="What is 2 + 2?",
                    correct_answer="4",
                    distractors=["3", "5", "6"],
                )
            ),
        )
    ]


class TestHandleCorrect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.md_path = os.path.join(self.tmp, "questions.md")
        self.tsv_path = os.path.join(self.tmp, "questions.tsv")
        self.exam_dir = os.path.join(self.tmp, "exam")
        self.output_dir = os.path.join(self.tmp, "output")
        self.roster_path = os.path.join(self.tmp, "roster.xlsx")

        os.makedirs(self.exam_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        artifacts.write_artifacts(_make_records(), self.md_path, self.tsv_path)
        pd.DataFrame(
            [{"Nom d'usuari": "abc123", "Cognoms": "Smith", "Nota numÃ©rica": None}]
        ).to_excel(self.roster_path, index=False)
        pd.DataFrame(
            [{
                "student_id": "ABC123",
                "student_name": "Smith",
                "score": 1,
                "total_questions": 1,
            }]
        ).to_csv(os.path.join(self.output_dir, "correction_results.csv"), index=False)
        pd.DataFrame(
            [{
                "original_id": "q1",
                "question_text": "What is 2 + 2?",
                "total_answers": 1,
                "option_A_count": 1,
                "option_A_text": "4",
            }]
        ).to_csv(os.path.join(self.output_dir, "question_stats.csv"), index=False)

    def _make_args(self):
        return argparse.Namespace(
            input_md_path=self.md_path,
            input_path=os.path.join(self.tmp, "unused.pdf"),
            exam_dir=self.exam_dir,
            output_dir=self.output_dir,
            evaluate_final=False,
            evaluator_instructions=None,
            lang="en",
            void_questions=None,
            void_questions_nicely=None,
            input_csv=self.roster_path,
            id_column="Nom d'usuari",
            mark_column="Nota numÃ©rica",
            name_column="Cognoms",
            simplify_csv=False,
            fuzzy_id_match=70,
            penalty=0.3333,
            input_encoding="utf-8",
            input_sep="semi",
            output_decimal_sep=",",
            only_analysis=True,
        )

    @patch("ptestgen.correct.correct_online.update_tsv_from_question_stats", return_value=1)
    @patch("ptestgen.correct.grades.fill_marks_in_file")
    @patch("ptestgen.correct.analysis.analyze_results")
    @patch("ptestgen.correct.utils.load_solutions", return_value=({"1": {1: 1}}, {"1": {1: 1}}, 1))
    def test_handle_correct_fills_marks_when_roster_provided(
        self,
        _mock_load_solutions,
        _mock_analyze,
        mock_fill_marks,
        _mock_update_stats,
    ):
        handle_correct(self._make_args())

        mock_fill_marks.assert_called_once_with(
            self.roster_path,
            "Nom d'usuari",
            "Nota numÃ©rica",
            os.path.join(self.output_dir, "correction_results.csv"),
            70,
            "utf-8",
            ";",
            ",",
            name_col="Cognoms",
            simplify_csv=False,
        )


