from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

@dataclass
class EvaluationData:
    """Stores the results of an evaluation pass."""
    difficulty_score: Optional[float] = None
    pedagogical_value: Optional[float] = None
    clarity_score: Optional[float] = None
    distractor_plausibility_score: Optional[float] = None
    evaluation_comments: List[str] = field(default_factory=list)
    evaluator_guessed_correctly: Optional[bool] = None

@dataclass
class Question:
    """Represents a single multiple-choice question."""
    id: int
    text: str
    correct_answer: str
    distractors: List[str]
    source_material: Optional[str] = None # e.g., filename, page number
    image_reference: Optional[str] = None # Path to an associated image
    explanation: Optional[str] = None # Optional explanation for the correct answer
    original_details: Optional[Dict[str, Any]] = None # Stores original text/answers before LLM review modification
    
    # New evaluation fields
    initial_evaluation: Optional[EvaluationData] = None
    reviewed_evaluation: Optional[EvaluationData] = None

    @property
    def options(self) -> List[str]:
        """Returns a combined list of correct answer and distractors."""
        return [self.correct_answer] + self.distractors

    # Add property to get correct index if needed by some converters, though less ideal
    @property
    def correct_option_index(self) -> int:
        """Returns the index of the correct answer in the combined options list."""
        # Assumes correct answer is always first internally for this property
        return 0

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