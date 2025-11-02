from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- Core Data Structures ---

class QuestionContent(BaseModel):
    """Represents the core content of a question at any stage."""
    text: str
    correct_answer: str
    distractors: List[str]
    explanation: Optional[str] = None

    @property
    def options(self) -> List[str]:
        """Returns a combined list of correct answer and distractors."""
        return [self.correct_answer] + self.distractors

class EvaluationData(BaseModel):
    """Stores the results of an evaluation pass."""
    difficulty_score: Optional[float] = None
    pedagogical_value: Optional[float] = None
    clarity_score: Optional[float] = None
    distractor_plausibility_score: Optional[float] = None
    evaluation_comments: Optional[str] = None
    evaluator_guessed_correctly: Optional[bool] = None

class ChangeMetrics(BaseModel):
    """Stores metrics about the changes between two stages of a question."""
    status: str = "unchanged"  # e.g., unchanged, modified, removed
    levenshtein_question: int = 0
    levenshtein_answers: int = 0
    rel_levenshtein_question: float = 0.0
    rel_levenshtein_answers: float = 0.0

class QuestionStage(BaseModel):
    """Represents a question at a specific stage of the pipeline (e.g., generated, reviewed)."""
    content: QuestionContent
    evaluation: Optional[EvaluationData] = None

class QuestionRecord(BaseModel):
    """
    Represents the full history and metadata for a single question.
    This object corresponds to one row in the metadata TSV file.
    """
    question_id: str
    source_material: Optional[str] = None
    image_reference: Optional[str] = None

    generated: Optional[QuestionStage] = None
    reviewed: Optional[QuestionStage] = None
    manual: Optional[QuestionStage] = None # Populated after parsing user-edited markdown

    # Change tracking
    changes_gen_to_rev: Optional[ChangeMetrics] = None
    changes_rev_to_man: Optional[ChangeMetrics] = None

    def get_latest_content(self) -> QuestionContent:
        """Returns the most recent version of the question's content."""
        if self.manual:
            return self.manual.content
        if self.reviewed:
            return self.reviewed.content
        if self.generated:
            return self.generated.content
        raise ValueError(f"QuestionRecord {self.question_id} has no content.")


# --- Pydantic Schemas for LLM Structured Output ---

class LLMQuestionItem(BaseModel):
    text: str
    correct_answer: str
    distractors: List[str]
    explanation: Optional[str] = None

class LLMQuestionList(BaseModel):
    questions: List[LLMQuestionItem]

class LLMReviewedQuestion(BaseModel):
    text: str
    correct_answer: str
    distractors: List[str]

class LLMReview(BaseModel):
    reviewed_question: LLMReviewedQuestion

class LLMEvaluation(BaseModel):
    difficulty_score: float = Field(..., description="Score from 0.0 (very easy) to 1.0 (very difficult)")
    pedagogical_value: float = Field(..., description="Score from 0.0 (very low value) to 1.0 (very high value)")
    clarity: float = Field(..., description="Score from 0.0 (very unclear) to 1.0 (very clear)")
    distractor_plausibility: float = Field(..., description="Score from 0.0 (very unplausible) to 1.0 (very plausible)")
    guessed_correct_answer: int = Field(..., description="The 1-based index of the answer the model believes is correct.")
    evaluation_comment: str = Field(..., description="A brief, one-sentence comment explaining the scores.") 