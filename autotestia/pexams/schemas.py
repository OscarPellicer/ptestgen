from typing import List, Optional
from pydantic import BaseModel, Field

class PexamOption(BaseModel):
    """Data model for a single answer option in a question."""
    text: str
    is_correct: bool = Field(False, description="True if this is a correct answer.")

class PexamQuestion(BaseModel):
    """
    Data model for a single exam question.
    This schema is portable and can be used as the base for other systems.
    """
    id: int
    text: str
    options: List[PexamOption]
    image_path: Optional[str] = None
    
    @property
    def correct_answer_index(self) -> Optional[int]:
        """Returns the index of the first correct answer, or None if no correct answer is set."""
        for i, option in enumerate(self.options):
            if option.is_correct:
                return i
        return None
