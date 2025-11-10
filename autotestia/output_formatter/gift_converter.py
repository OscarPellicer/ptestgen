import base64
import html
import logging
import mimetypes
import os
import random
import re
from typing import List, Optional

from ..schemas import QuestionRecord


def escape_gift(text: str) -> str:
    """Escapes special characters for GIFT format."""
    # Process in a single pass to avoid issues with chained replacements
    escaped_text = ""
    for char in text:
        if char in ['~', '=', '#', '{', '}', ':', '\\']:
            escaped_text += '\\' + char
        else:
            escaped_text += char
    return escaped_text


def convert_to_gift(records: List[QuestionRecord], output_file: str, max_image_width: Optional[int] = None, max_image_height: Optional[int] = None):
    """Converts questions to GIFT format using QuestionRecord."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Converting {len(records)} questions to GIFT: {output_file}")

    with open(output_file, 'w', encoding='utf-8') as f:
        for i, record in enumerate(records):
            content = record.get_latest_content()
            
            # Use question ID in title for uniqueness
            question_name = f"Q{i+1}_{record.question_id}"
            f.write(f"::{escape_gift(question_name)}::")

            # --- Prepare Question Text ---
            question_text = content.text
            format_specifier = "[markdown]"  # Always use Markdown as requested

            if record.image_reference:
                # Correctly resolve the image path relative to the project root
                image_path = os.path.join(os.path.dirname(output_file), record.image_reference)
                image_path = os.path.normpath(image_path)
                try:
                    with open(image_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        mime_type, _ = mimetypes.guess_type(image_path)
                        if mime_type:
                            style = ""
                            if max_image_width:
                                style += f"width:{max_image_width}px; "
                            if max_image_height:
                                style += f"max-height:{max_image_height}px;"
                            
                            img_tag = f"<img src='data:{mime_type};base64,{encoded_string}' alt='Image for question' style='{style}' />"
                            question_text += f"<p>{img_tag}</p>"
                            # No need for special logic, as Markdown handles HTML
                        else:
                            logging.warning(f"Could not determine MIME type for {image_path}. Skipping image.")
                except FileNotFoundError:
                    logging.warning(f"Image file not found: {image_path}. Skipping image embedding.")
                except Exception as e:
                    logging.error(f"Error processing image {image_path}: {e}", exc_info=True)

            # Convert single '$' to '$$' for MathJax, but not if already '$$'
            def replace_latex_delimiters(text):
                # This regex finds single '$' not preceded or followed by another '$'
                return re.sub(r'(?<!\$)\$(?!\$)', '$$', text)

            question_text = replace_latex_delimiters(question_text)
            
            # Prepend format tag if needed
            question_text_with_format = f"{format_specifier}{question_text}"

            f.write(f"{escape_gift(question_text_with_format)} {{\n")

            # --- Prepare and Write Options ---
            options = [content.correct_answer] + content.distractors
            random.shuffle(options)  # Shuffle order in GIFT file

            for option_text in options:
                processed_option = replace_latex_delimiters(option_text)
                option_escaped = escape_gift(processed_option)
                prefix = "=" if option_text == content.correct_answer else "~"
                # For now, no per-answer feedback is in the schema
                f.write(f"\t{prefix}{option_escaped}\n")

            # --- Add General Feedback (Explanation) ---
            if content.explanation:
                processed_explanation = replace_latex_delimiters(content.explanation)
                explanation_escaped = escape_gift(processed_explanation)
                f.write(f"\t####{explanation_escaped}\n")  # General feedback marker

            f.write("}\n\n")

    print(f"Successfully converted questions to GIFT: {output_file}")
