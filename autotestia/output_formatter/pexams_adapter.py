from typing import List
from ..schemas import QuestionRecord
from pexams.schemas import PexamQuestion, PexamOption

def convert_autotestia_to_pexam(records: List[QuestionRecord]) -> List[PexamQuestion]:
    """Converts a list of AutoTestIA QuestionRecord objects to PexamQuestion objects."""
    pexam_questions = []
    for i, record in enumerate(records):
        content = record.get_latest_content()
        pexam_options = []
        correct_answer_index = None
        
        options_texts = content.options

        for j, opt_text in enumerate(options_texts):
            is_correct = (opt_text == content.correct_answer)
            pexam_options.append(PexamOption(text=opt_text, is_correct=is_correct))
            if is_correct:
                correct_answer_index = j
        
        pexam_questions.append(
            PexamQuestion(
                id=i + 1,  # Use sequential ID for pexams
                text=content.text,
                options=pexam_options,
                correct_answer_index=correct_answer_index,
                image_source=record.image_reference,
                metadata={"original_id": record.question_id}
            )
        )
    return pexam_questions
