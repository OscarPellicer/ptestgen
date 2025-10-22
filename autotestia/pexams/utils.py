from typing import List
import random

from autotestia.schemas import Question as AutotestiaQuestion
from .schemas import PexamQuestion, PexamOption

def convert_autotestia_to_pexam(autotestia_questions: List[AutotestiaQuestion]) -> List[PexamQuestion]:
    """Converts a list of Autotestia Question objects to PexamQuestion objects."""
    pexam_questions = []
    for q in autotestia_questions:
        
        # Create a list of options with the correct answer marked
        options = [PexamOption(text=q.correct_answer, is_correct=True)]
        for d in q.distractors:
            options.append(PexamOption(text=d, is_correct=False))
            
        # The original schema has correct answer first. We shuffle for the exam.
        random.shuffle(options)
            
        pexam_q = PexamQuestion(
            id=q.id,
            text=q.text,
            options=options,
            image_path=q.image_reference  # Map image_reference to image_path
        )
        pexam_questions.append(pexam_q)
        
    return pexam_questions
