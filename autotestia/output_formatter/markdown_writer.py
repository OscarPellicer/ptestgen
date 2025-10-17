import os
import random # For shuffling options in markdown output - NOW UNUSED
from typing import List
from ..schemas import Question, EvaluationData
import logging
import re # Import re

def write_questions_to_markdown(questions: List[Question], output_file: str):
    """Writes a list of questions to a Markdown file for manual review, matching the specified format."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8-sig') as f:
        # Write Header
        f.write("# AutoTestIA Generated Questions for Review\n\n")
        f.write("""Please review the following questions.
You can edit the text directly in this file, and remove any questions that are not interesting.
The correct answer is always in the first position, and the others are all false.
Ensure the format remains consistent for later processing.\n""")

        # Write Questions
        for i, q in enumerate(questions):
            # Separator before each question (except the first)
            if i > 0:
                f.write("\n---\n\n")
            else:
                # Separator after the header for the first question
                f.write("\n\n---\n\n")

            f.write(f"## Question {q.id}\n\n")

            # --- Metadata ---
            f.write(f"**Source:** {q.source_material or 'N/A'}\n")
            if q.image_reference:
                f.write(f"**Image:** {q.image_reference}\n")
            
            f.write("\n")

            # Helper to write evaluation blocks
            def write_eval_block(eval_data, title):
                if not eval_data:
                    return
                f.write(f"### {title}\n\n")
                if eval_data.difficulty_score is not None:
                    f.write(f"**Difficulty Score:** {eval_data.difficulty_score:.2f}\n")
                if eval_data.pedagogical_value is not None:
                    f.write(f"**Pedagogical Value:** {eval_data.pedagogical_value:.2f}\n")
                if eval_data.clarity_score is not None:
                    f.write(f"**Clarity Score:** {eval_data.clarity_score:.2f}\n")
                if eval_data.distractor_plausibility_score is not None:
                    f.write(f"**Distractor Plausibility:** {eval_data.distractor_plausibility_score:.2f}\n")
                if eval_data.evaluator_guessed_correctly is not None:
                    f.write(f"**Evaluator Guessed Correctly:** {'Yes' if eval_data.evaluator_guessed_correctly else 'No'}\n")
                if eval_data.evaluation_comments:
                    comments_str = "\n".join([f"- {c}" for c in eval_data.evaluation_comments])
                    f.write(f"**Evaluation Comments:**\n{comments_str}\n")
                f.write("\n")

            # --- 1. Final (Reviewed) Question Details ---
            f.write(f"**Question Text:**\n{q.text}\n\n")
            options_to_display = [q.correct_answer] + q.distractors
            f.write("**Options:**\n\n")
            for option_text in options_to_display:
                f.write(f"- {option_text}\n")

            if q.explanation:
                 f.write(f"\n**Explanation:**\n{q.explanation}\n")
            
            f.write("\n")

            # --- 2. Reviewed Evaluation ---
            write_eval_block(q.reviewed_evaluation, "Reviewed Evaluation")

            # --- 3. Original Question Details (Optional) ---
            show_original = False
            if q.original_details:
                original_text = q.original_details.get('text')
                original_correct = q.original_details.get('correct_answer')
                original_distractors = q.original_details.get('distractors', [])
                original_distractors_set = set(original_distractors)
                current_distractors_set = set(q.distractors)

                if (original_text != q.text or
                    original_correct != q.correct_answer or
                    original_distractors_set != current_distractors_set):
                    show_original = True
            
            if show_original:
                f.write("### Original Question Details (Before LLM Review)\n\n")
                f.write(f"**Original Question Text:**\n{original_text or 'N/A'}\n\n")

                orig_options = [original_correct] + original_distractors
                f.write("**Original Question Options:**\n\n")
                for opt_text in orig_options:
                    f.write(f"- {opt_text}\n")
                
                f.write("\n")

            # --- 4. Initial Evaluation ---
            write_eval_block(q.initial_evaluation, "Initial Evaluation")

        f.write("\n")

    logging.info(f"Successfully wrote {len(questions)} questions to Markdown: {output_file}")

# --- Function to read the reviewed Markdown ---

def parse_reviewed_markdown(markdown_file: str) -> List[Question]:
    """
    Parses a reviewed Markdown file back into a list of Question objects,
    handling edits and deletions based on the specified format.
    Uses a refined state-based approach for clarity and robustness.
    """
    if not os.path.exists(markdown_file):
        raise FileNotFoundError(f"Reviewed Markdown file not found: {markdown_file}")

    questions = []
    # Use utf-8-sig to handle potential BOM (Byte Order Mark) common on Windows
    try:
        with open(markdown_file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except Exception as e:
        logging.error(f"Error reading Markdown file {markdown_file}: {e}")
        return [] # Return empty list if file cannot be read

    # Split by the --- separator, removing potential empty strings from split
    # Add handling for different line endings (\r\n vs \n) before splitting
    content = content.replace('\r\n', '\n')
    question_blocks = [block.strip() for block in content.split("\n---\n") if block.strip()]

    # Regex for parsing options and comments robustly
    # Matches "- text" ignoring case and whitespace variations
    re_option = re.compile(r"^\s*-\s*(.*)", re.IGNORECASE)
    # Matches "- comment text"
    re_comment = re.compile(r"^\s*-\s*(.*)")

    current_id_fallback = 1

    for block_index, block in enumerate(question_blocks):
        # Skip potential header block or empty blocks
        if not block.startswith("## Question"):
            if block_index == 0 and block.startswith("# AutoTestIA Generated Questions"):
                 logging.info("Skipping header block.")
            elif block: # Log if a non-empty, non-header block is skipped
                 logging.warning(f"Skipping block not starting with '## Question':\n---\n{block[:100]}...\n---")
            continue

        lines = block.split('\n')
        question_data = {
            "id": None,
            "text": None, # Initialize text/explanation as None
            "correct_answer": None,
            "distractors": [],
            "source_material": None,
            "image_reference": None,
            "explanation": None,
            "initial_evaluation": None,
            "reviewed_evaluation": None,
        }
        options_parsed = [] # Temp list: [(text, is_correct_bool)]
        current_multiline_field = None # Tracks 'text', 'explanation'
        multiline_buffer = [] # Accumulates lines for the current field
        parsing_active = True # Flag to stop parsing if original section is hit
        current_evaluation_target = None # To know if we are parsing 'initial' or 'reviewed' eval

        for line_num, line in enumerate(lines):
            stripped_line = line.strip()

            # Stop parsing useful fields if we hit the original details section
            if stripped_line.startswith("### Original Question Details"):
                parsing_active = False
                # Finalize any active multiline buffer before stopping
                if current_multiline_field and multiline_buffer:
                     content = "\n".join(multiline_buffer).strip()
                     if current_multiline_field in question_data:
                        question_data[current_multiline_field] = content if content else None
                     multiline_buffer = []
                     current_multiline_field = None
                continue # Skip to next line

            if not parsing_active:
                continue # Don't process lines after original details section starts

            # --- Determine if a new section is starting, which terminates the previous multiline field ---
            new_section_header = None
            section_headers = {
                "## Question": None, 
                "### Initial Evaluation": "initial_eval",
                "### Reviewed Evaluation": "reviewed_eval",
                "### Original Question Details": None,
                "**Source:**": None,
                "**Image:**": None,
                # These are now inside eval blocks
                "**Question Text:**": "text",
                "**Options:**": "options", 
                "**Explanation:**": "explanation",
            }

            for header, field_key in section_headers.items():
                if stripped_line.startswith(header):
                    new_section_header = header
                    # Finalize previous multiline buffer (text or explanation)
                    if current_multiline_field and multiline_buffer:
                        content = "\n".join(multiline_buffer).strip()
                        if current_multiline_field in question_data:
                            question_data[current_multiline_field] = content if content else None
                    multiline_buffer = [] # Reset buffer regardless
                    current_multiline_field = field_key # Set new field type
                    
                    # Handle new evaluation sections
                    if field_key == "initial_eval":
                        current_evaluation_target = "initial_evaluation"
                        question_data[current_evaluation_target] = {}
                    elif field_key == "reviewed_eval":
                        current_evaluation_target = "reviewed_evaluation"
                        question_data[current_evaluation_target] = {}
                    else: # If it's not an eval header, we are no longer parsing an eval block
                        current_evaluation_target = None

                    break # Found the header for this line

            # If we are inside an evaluation block, parse its fields
            if current_evaluation_target:
                eval_dict = question_data[current_evaluation_target]
                if stripped_line.startswith("**Difficulty Score:**"):
                    try: eval_dict["difficulty_score"] = float(stripped_line.split(":")[1].strip())
                    except (ValueError, IndexError): pass
                elif stripped_line.startswith("**Pedagogical Value:**"):
                    try: eval_dict["pedagogical_value"] = float(stripped_line.split(":")[1].strip())
                    except (ValueError, IndexError): pass
                elif stripped_line.startswith("**Clarity Score:**"):
                    try: eval_dict["clarity_score"] = float(stripped_line.split(":")[1].strip())
                    except (ValueError, IndexError): pass
                elif stripped_line.startswith("**Distractor Plausibility:**"):
                    try: eval_dict["distractor_plausibility_score"] = float(stripped_line.split(":")[1].strip())
                    except (ValueError, IndexError): pass
                elif stripped_line.startswith("**Evaluator Guessed Correctly:**"):
                    guess_str = stripped_line.split(":")[1].strip().lower()
                    if guess_str == 'yes': eval_dict["evaluator_guessed_correctly"] = True
                    elif guess_str == 'no': eval_dict["evaluator_guessed_correctly"] = False
                elif stripped_line.startswith("**Evaluation Comments:**"):
                    current_multiline_field = "evaluation_comments" # Special state for comments
                    multiline_buffer = []
                elif current_multiline_field == "evaluation_comments":
                    match = re_comment.match(stripped_line)
                    if match:
                        if "evaluation_comments" not in eval_dict:
                            eval_dict["evaluation_comments"] = []
                        eval_dict["evaluation_comments"].append(match.group(1).strip())
                continue # Move to next line after processing eval field

            # --- Process based on the identified section or multiline state ---
            # Metadata
            if stripped_line.startswith("**Source:**"):
                question_data["source_material"] = stripped_line.replace("**Source:**", "").strip()
            elif stripped_line.startswith("**Image:**"):
                question_data["image_reference"] = stripped_line.replace("**Image:**", "").strip()

            # Multiline Section Starts & Content Capture
            elif new_section_header == "**Question Text:**":
                initial_text = stripped_line.replace("**Question Text:**", "").strip()
                if initial_text: multiline_buffer.append(initial_text)
            elif new_section_header == "**Options:**":
                pass 
            elif new_section_header == "**Explanation:**":
                initial_text = stripped_line.replace("**Explanation:**", "").strip()
                if initial_text: multiline_buffer.append(initial_text)

            # Content capture for ongoing multiline sections
            elif current_multiline_field == "options":
                 match = re_option.match(stripped_line)
                 if match:
                     option_text = match.group(1).strip()
                     options_parsed.append(option_text)
            elif current_multiline_field in ["text", "explanation"]:
                 if not new_section_header:
                     multiline_buffer.append(line)
        
        # --- Finalize the last multiline field after loop finishes ---
        if current_multiline_field in ["text", "explanation"] and multiline_buffer:
             content = "\n".join(multiline_buffer).strip()
             if current_multiline_field in question_data:
                 question_data[current_multiline_field] = content if content else None

        # Finalize evaluation objects from dicts
        if question_data.get('initial_evaluation'):
            question_data['initial_evaluation'] = EvaluationData(**question_data['initial_evaluation'])
        if question_data.get('reviewed_evaluation'):
            question_data['reviewed_evaluation'] = EvaluationData(**question_data['reviewed_evaluation'])

        # --- Process Parsed Options ---
        if options_parsed:
            question_data["correct_answer"] = options_parsed[0]
            question_data["distractors"] = options_parsed[1:]
        else:
            # Explicitly set to None/empty if no options were found
            question_data["correct_answer"] = None
            question_data["distractors"] = []

        # Assign fallback ID if needed
        if question_data["id"] is None:
            question_data["id"] = current_id_fallback
            current_id_fallback += 1
        else:
            current_id_fallback = max(current_id_fallback, question_data["id"] + 1)

        # --- Validation and Question Object Creation ---
        missing = []
        if not question_data["text"]: missing.append("text")
        if question_data["correct_answer"] is None: missing.append("correct answer")
        # We now allow questions with no distractors if needed by the user review.
        # if not question_data["distractors"] and options_parsed: missing.append("distractors") # Old check

        if not missing:
            try:
                # Filter out keys with None values before creating Question
                final_data = {k: v for k, v in question_data.items() if v is not None}
                if "distractors" not in final_data: final_data["distractors"] = []

                q = Question(**final_data)
                questions.append(q)
            except TypeError as e:
                 logging.error(f"Could not create Question object for ID {question_data['id']} due to field mismatch: {e}. Data: {final_data}", exc_info=True)
            except Exception as e:
                 logging.error(f"Unexpected error creating Question object for ID {question_data['id']}: {e}. Data: {final_data}", exc_info=True)
        elif block: # Only warn if block wasn't just whitespace or header
             # Include block index for easier location in the markdown file
             logging.warning(f"Skipping block (index {block_index}) for Question ID {question_data.get('id', 'unknown')} due to missing essential parts: {', '.join(missing)}.")

    logging.info(f"Parsed {len(questions)} questions from reviewed Markdown: {markdown_file}")
    return questions 