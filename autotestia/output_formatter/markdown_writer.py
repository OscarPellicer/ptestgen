import os
import random # For shuffling options in markdown output - NOW UNUSED
from typing import List
from ..schemas import Question
import logging
import re # Import re

def write_questions_to_markdown(questions: List[Question], output_file: str):
    """Writes a list of questions to a Markdown file for manual review, matching the specified format."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Use 'utf-8-sig' to handle potential BOM (Byte Order Mark) issues, common on Windows
    with open(output_file, 'w', encoding='utf-8-sig') as f:
        # Write Header
        f.write("# AutoTestIA Generated Questions for Review\n\n")
        f.write("Please review the following questions. You can edit the text directly in this file.\n")
        f.write("Mark questions for deletion by changing `DELETE=FALSE` to `DELETE=TRUE`.\n") # Updated instruction slightly
        f.write("The option marked with `(Correct: YES)` is the correct answer. Ensure exactly one option has `(Correct: YES)`.\n") # Updated instruction slightly
        f.write("Ensure the format remains consistent for later processing.\n")
        # No trailing newline needed here before the first separator

        # Write Questions
        for i, q in enumerate(questions):
            # Separator before each question (except the first)
            if i > 0:
                f.write("\n---\n\n")
            else:
                # Separator after the header for the first question
                f.write("\n\n---\n\n")

            f.write(f"## Question {q.id}\n\n")
            f.write("DELETE=FALSE\n\n") # Deletion marker

            # --- Metadata ---
            f.write(f"**Source:** {q.source_material or 'N/A'}\n")
            if q.image_reference:
                f.write(f"**Image:** {q.image_reference}\n")
            if q.difficulty_score is not None:
                 f.write(f"**Auto-Review Difficulty:** {q.difficulty_score:.2f}\n")
            if q.quality_score is not None:
                f.write(f"**Auto-Review Quality:** {q.quality_score:.2f}\n")
            # if q.review_comments:
            #     # Join comments into a single block
            #     comments_str = "\n".join([f"- {c}" for c in q.review_comments])
            #     f.write(f"**Auto-Review Comments:**\n{comments_str}\n")
            f.write("\n") # Blank line after metadata

            # --- Reviewed/Current Question Details ---
            f.write(f"**Question Text:**\n{q.text}\n\n")

            # Combine correct answer and distractors
            options_to_display = [(q.correct_answer, True)] + [(d, False) for d in q.distractors]

            f.write("**Options:**\n")
            for option_text, is_correct in options_to_display:
                correct_marker = "YES" if is_correct else "NO"
                f.write(f"- {option_text} (Correct: {correct_marker})\n")

            if q.explanation:
                 f.write(f"\n**Explanation:**\n{q.explanation}\n") # Add blank line before explanation if text/options are present

            # --- Original Question Details (Optional) ---
            show_original = False
            if q.original_details:
                original_text = q.original_details.get('text')
                original_correct = q.original_details.get('correct_answer')
                original_distractors = q.original_details.get('distractors', [])
                # Compare list content, order doesn't matter for difference detection
                original_distractors_set = set(original_distractors)
                current_distractors_set = set(q.distractors)

                if (original_text != q.text or
                    original_correct != q.correct_answer or
                    original_distractors_set != current_distractors_set):
                    show_original = True

            if show_original:
                # Add a newline before this section if explanation wasn't present
                if not q.explanation:
                    f.write("\n")
                f.write("### Original Question Details (Before LLM Review)\n\n")
                f.write(f"**Original Question Text:**\n{original_text or 'N/A'}\n\n")

                # Display original options (correct answer followed by distractors as stored)
                orig_options = [(original_correct, True)] + [(d, False) for d in original_distractors]
                f.write("**Original Question Options:**\n")
                for opt_text, is_correct in orig_options:
                    correct_marker = "YES" if is_correct else "NO"
                    f.write(f"- {opt_text} (Correct: {correct_marker})\n")

        # Add a trailing newline for POSIX compatibility
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
    # Matches "- text (Correct: YES/NO)" ignoring case and whitespace variations
    re_option = re.compile(r"^\s*-\s*(.*?)\s*\(Correct:\s*(YES|NO)\)", re.IGNORECASE)
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
            "difficulty_score": None,
            "quality_score": None,
            "review_comments": []
        }
        options_parsed = [] # Temp list: [(text, is_correct_bool)]
        current_multiline_field = None # Tracks 'text', 'explanation'
        multiline_buffer = [] # Accumulates lines for the current field
        delete_question = False
        parsing_active = True # Flag to stop parsing if original section is hit

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
                "## Question": None, # Special handling below
                "DELETE=": None, # Special handling below
                "**Source:**": None,
                "**Image:**": None,
                "**Auto-Review Difficulty:**": None,
                "**Auto-Review Quality:**": None,
                "**Auto-Review Comments:**": "review_comments", # Mark as special multiline type
                "**Question Text:**": "text",
                "**Options:**": "options", # Mark as special multiline type
                "**Explanation:**": "explanation",
            }

            for header, field_key in section_headers.items():
                if stripped_line.startswith(header):
                    new_section_header = header
                    # Finalize previous multiline buffer (text or explanation)
                    if current_multiline_field and current_multiline_field not in ["options", "review_comments"] and multiline_buffer:
                        content = "\n".join(multiline_buffer).strip()
                        if current_multiline_field in question_data:
                            question_data[current_multiline_field] = content if content else None
                    multiline_buffer = [] # Reset buffer regardless
                    current_multiline_field = field_key # Set new field type (None for non-multiline headers)
                    break # Found the header for this line

            # --- Process based on the identified section or multiline state ---

            # Block Control / ID / Delete
            if stripped_line.startswith("## Question"):
                try:
                    question_data["id"] = int(stripped_line.split(" ")[2])
                except (IndexError, ValueError):
                    logging.warning(f"Could not parse ID from '{stripped_line}', will assign later.")
            elif stripped_line.upper().startswith("DELETE="):
                 flag = stripped_line.split("=")[-1].strip().upper()
                 if flag == "TRUE":
                     delete_question = True
                     break # Stop processing lines for this block

            # Metadata
            elif stripped_line.startswith("**Source:**"):
                question_data["source_material"] = stripped_line.replace("**Source:**", "").strip()
            elif stripped_line.startswith("**Image:**"):
                question_data["image_reference"] = stripped_line.replace("**Image:**", "").strip()
            elif stripped_line.startswith("**Auto-Review Difficulty:**"):
                 try:
                     question_data["difficulty_score"] = float(stripped_line.replace("**Auto-Review Difficulty:**", "").strip())
                 except ValueError: pass
            elif stripped_line.startswith("**Auto-Review Quality:**"):
                 try:
                     question_data["quality_score"] = float(stripped_line.replace("**Auto-Review Quality:**", "").strip())
                 except ValueError: pass

            # Multiline Section Starts & Content Capture
            elif new_section_header == "**Auto-Review Comments:**":
                pass # Handled below by state check
            elif new_section_header == "**Question Text:**":
                initial_text = stripped_line.replace("**Question Text:**", "").strip()
                if initial_text: multiline_buffer.append(initial_text)
            elif new_section_header == "**Options:**":
                pass # Handled below by state check
            elif new_section_header == "**Explanation:**":
                initial_text = stripped_line.replace("**Explanation:**", "").strip()
                if initial_text: multiline_buffer.append(initial_text)

            # Content capture for ongoing multiline sections or special sections
            elif current_multiline_field == "review_comments":
                 match = re_comment.match(stripped_line)
                 if match:
                     question_data["review_comments"].append(match.group(1).strip())
            elif current_multiline_field == "options":
                 match = re_option.match(stripped_line)
                 if match:
                     option_text = match.group(1).strip()
                     is_correct = match.group(2).upper() == "YES"
                     options_parsed.append((option_text, is_correct))
                 elif stripped_line: # Log unexpected non-empty lines in options section
                      logging.warning(f"Ignoring unexpected line in Options section for Q {question_data.get('id', 'unknown')}: '{stripped_line}'")
            elif current_multiline_field in ["text", "explanation"]:
                 # Only append if it wasn't a header line we just processed
                 if not new_section_header:
                     multiline_buffer.append(line) # Append raw line to preserve internal newlines if needed, strip later

        # --- Finalize the last multiline field after loop finishes ---
        if current_multiline_field and current_multiline_field not in ["options", "review_comments"] and multiline_buffer:
             content = "\n".join(multiline_buffer).strip()
             if current_multiline_field in question_data:
                 question_data[current_multiline_field] = content if content else None

        # --- Post-processing the block ---
        if delete_question:
            logging.info(f"Skipping Question ID {question_data.get('id', 'unknown')} (marked for deletion).")
            continue

        # Assign fallback ID if needed
        if question_data["id"] is None:
            question_data["id"] = current_id_fallback
            current_id_fallback += 1
        else:
            current_id_fallback = max(current_id_fallback, question_data["id"] + 1)

        # Process parsed options
        correct_found = None
        temp_distractors = []
        correct_count = 0
        for opt_text, is_correct_flag in options_parsed:
            if is_correct_flag:
                if correct_count == 0:
                     correct_found = opt_text
                else: # Handle multiple correct answers gracefully
                     logging.warning(f"Multiple options marked as correct for Question ID {question_data['id']}. Using first ('{correct_found}') as correct, others as distractors.")
                     temp_distractors.append(opt_text)
                correct_count += 1
            else:
                temp_distractors.append(opt_text)

        if correct_count == 0 and options_parsed: # Only error if options existed but none were marked correct
             logging.error(f"No correct answer marked for Question ID {question_data['id']}. Skipping question.")
             continue
        elif correct_count >= 1:
             question_data["correct_answer"] = correct_found
             question_data["distractors"] = temp_distractors
        # If options_parsed is empty, correct_answer remains None, handled by validation below


        # --- Validation and Question Object Creation ---
        missing = []
        if not question_data["text"]: missing.append("text")
        if question_data["correct_answer"] is None: missing.append("correct answer")
        # Allow questions with no distractors, but require text and correct answer
        # if not question_data["distractors"] and options_parsed: missing.append("distractors")

        if not missing:
            try:
                # Filter out keys with None values before creating Question
                final_data = {k: v for k, v in question_data.items() if v is not None}
                # Ensure essential lists exist even if empty
                if "review_comments" not in final_data: final_data["review_comments"] = []
                if "distractors" not in final_data: final_data["distractors"] = []

                q = Question(**final_data)
                questions.append(q)
            except TypeError as e:
                 logging.error(f"Could not create Question object for ID {question_data['id']} due to field mismatch: {e}. Data: {final_data}", exc_info=True)
            except Exception as e:
                 logging.error(f"Unexpected error creating Question object for ID {question_data['id']}: {e}. Data: {final_data}", exc_info=True)
        elif block: # Only warn if block wasn't just whitespace or header
             logging.warning(f"Skipping block for Question ID {question_data.get('id', 'unknown')} due to missing essential parts: {', '.join(missing)}.")

    logging.info(f"Parsed {len(questions)} questions from reviewed Markdown: {markdown_file}")
    return questions 