import logging
import os
from typing import List, Optional
from .schemas import QuestionRecord
from pexams.schemas import PexamQuestion, PexamOption

def convert_autotestia_to_pexam(
    records: List[QuestionRecord],
    input_md_path: str,
    max_image_width: Optional[int] = None,
    max_image_height: Optional[int] = None
) -> List[PexamQuestion]:
    """Converts a list of QuestionRecord objects to a list of PexamQuestion objects."""
    pexam_questions = []
    md_dir = os.path.dirname(input_md_path)

    # Convert integer width/height to string with 'px'
    width_str = f"{max_image_width}px" if max_image_width is not None else None
    height_str = f"{max_image_height}px" if max_image_height is not None else None

    for i, record in enumerate(records):
        latest_content = record.get_latest_content()

        if not latest_content.distractors:
            logging.warning(f"Skipping question '{record.question_id}' for pexams export: no distractors found.")
            continue
        
        image_source = None
        if record.image_reference and record.image_reference.strip():
            # Logic to resolve image path
            # 1. Try treating it as relative to CWD (or absolute)
            path_relative_to_cwd = os.path.abspath(record.image_reference)
            
            # 2. Try treating it as relative to the markdown file
            path_relative_to_md = os.path.abspath(os.path.join(md_dir, record.image_reference))

            if os.path.isfile(path_relative_to_cwd):
                image_source = path_relative_to_cwd.replace("\\", "/")
            elif os.path.isfile(path_relative_to_md):
                image_source = path_relative_to_md.replace("\\", "/")
            else:
                logging.warning(f"Image reference '{record.image_reference}' for question '{record.question_id}' not found at '{path_relative_to_cwd}' or '{path_relative_to_md}', skipping image.")

        options = [
            PexamOption(text=latest_content.correct_answer, is_correct=True)
        ] + [
            PexamOption(text=distractor, is_correct=False) for distractor in latest_content.distractors
        ]
        
        pexam_questions.append(
            PexamQuestion(
                id=i + 1,  # Use sequential ID for pexams
                text=latest_content.text,
                options=options,
                explanation=latest_content.explanation or "",
                image_source=image_source,
                max_image_width=width_str,
                max_image_height=height_str,
            )
        )
    return pexam_questions
