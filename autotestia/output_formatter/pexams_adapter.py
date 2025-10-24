from typing import List
from ..schemas import Question
from pexams.schemas import PexamQuestion, PexamOption

def convert_autotestia_to_pexam(questions: List[Question]) -> List[PexamQuestion]:
    """Converts a list of AutoTestIA Question objects to PexamQuestion objects."""
    pexam_questions = []
    for q in questions:
        pexam_options = []
        correct_answer_index = None
        
        # The Question dataclass provides options as a list of strings.
        # We need to convert them to PexamOption objects.
        options_texts = q.options

        for i, opt_text in enumerate(options_texts):
            is_correct = (opt_text == q.correct_answer)
            pexam_options.append(PexamOption(text=opt_text, is_correct=is_correct))
            if is_correct:
                correct_answer_index = i
        
        # The new Question schema uses 'image_reference'
        image_source = q.image_reference
        
        pexam_questions.append(
            PexamQuestion(
                id=q.id,
                text=q.text,
                options=pexam_options,
                correct_answer_index=correct_answer_index,
                image_source=image_source,
                metadata={} # The new Question schema does not have a metadata field.
            )
        )
    return pexam_questions
