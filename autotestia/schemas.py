from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

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
    difficulty_score: Optional[float] = None # Score assigned by reviewer agent
    quality_score: Optional[float] = None # Score assigned by reviewer agent
    review_comments: List[str] = field(default_factory=list) # Comments from reviewer
    original_details: Optional[Dict[str, Any]] = None # Stores original text/answers before LLM review modification

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
    difficulty_score: float = Field(..., description="Score from 0.0 to 1.0")
    quality_score: float = Field(..., description="Score from 0.0 to 1.0")
    review_comments: Optional[str] = Field(None, description="Comments on the review")
    reviewed_question: Optional[LLMReviewedQuestion] = None 