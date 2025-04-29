import os
import random # For shuffling options in markdown output
from typing import List
from ..schemas import Question
import logging

def write_questions_to_markdown(questions: List[Question], output_file: str):
    """Writes a list of questions to a Markdown file for manual review (OE3)."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# AutoTestIA Generated Questions for Review\n\n")
        f.write("Please review the following questions. You can edit the text directly in this file.\n")
        f.write("Mark questions for deletion by adding `DELETE=TRUE` at the start of the question block (before `## Question`).\n")
        f.write("The option marked with `Correct: YES` is the correct answer. Ensure exactly one option has `Correct: YES`.\n")
        f.write("Ensure the format remains consistent for later processing.\n\n")
        f.write("---\n\n")

        for q in questions:
            f.write(f"## Question {q.id}\n\n")
            f.write("DELETE=FALSE\n\n") # Deletion marker
            f.write(f"**Source:** {q.source_material or 'N/A'}\n")
            if q.image_reference:
                f.write(f"**Image:** {q.image_reference}\n")
            if q.difficulty_score is not None:
                 f.write(f"**Auto-Review Difficulty:** {q.difficulty_score:.2f}\n") # Add difficulty
            if q.quality_score is not None:
                f.write(f"**Auto-Review Quality:** {q.quality_score:.2f}\n") # Rename score label
            if q.review_comments:
                # Join comments into a single block for easier reading if needed
                comments_str = "\n".join([f"- {c}" for c in q.review_comments])
                f.write(f"**Auto-Review Comments:**\n{comments_str}\n")
            f.write("\n")

            # --- Add Original Question Details if they exist AND are different ---
            show_original = False
            if q.original_details:
                original_text = q.original_details.get('text')
                original_correct = q.original_details.get('correct_answer')
                # Compare list content, order doesn't matter for difference detection
                original_distractors_set = set(q.original_details.get('distractors', []))
                current_distractors_set = set(q.distractors)

                if (original_text != q.text or
                    original_correct != q.correct_answer or
                    original_distractors_set != current_distractors_set):
                    show_original = True

            if show_original:
                f.write("### Original Question Details (Before LLM Review)\n\n")
                f.write(f"**Original Text:**\n{original_text or 'N/A'}\n\n")
                # Display original options in their stored order (correct first assumed)
                orig_options = [(original_correct, True)] + \
                               [(d, False) for d in q.original_details.get('distractors', [])]
                f.write("**Original Options:**\n")
                for opt_text, is_correct in orig_options:
                    correct_marker = "YES" if is_correct else "NO"
                    f.write(f"- {opt_text} (Correct: {correct_marker})\n")
                f.write("\n---\n\n") # Separator for original vs reviewed

            # --- Reviewed/Current Question Details ---
            f.write(f"### Reviewed Question Details\n\n") # Add header for clarity
            f.write(f"**Question Text:**\n{q.text}\n\n")

            # Combine correct answer and distractors - CORRECT ANSWER FIRST
            # options_to_display = [(q.correct_answer, True)] + [(d, False) for d in q.distractors]
            # random.shuffle(options_to_display) # Shuffle for unbiased review -> REMOVED SHUFFLE
            options_to_display = [(q.correct_answer, True)] + [(d, False) for d in q.distractors]

            f.write("**Options:**\n")
            for option_text, is_correct in options_to_display:
                correct_marker = "YES" if is_correct else "NO"
                # Simple bullet point format, relying on Correct: YES/NO marker
                f.write(f"- {option_text} (Correct: {correct_marker})\n")

            if q.explanation:
                 f.write(f"\n**Explanation:**\n{q.explanation}\n")

            f.write("\n---\n\n")

    logging.info(f"Successfully wrote {len(questions)} questions to Markdown: {output_file}")

# --- Function to read the reviewed Markdown ---

def parse_reviewed_markdown(markdown_file: str) -> List[Question]:
    """
    Parses a reviewed Markdown file back into a list of Question objects,
    handling edits and deletions based on the new schema.
    """
    if not os.path.exists(markdown_file):
        raise FileNotFoundError(f"Reviewed Markdown file not found: {markdown_file}")

    questions = []
    with open(markdown_file, 'r', encoding='utf-8') as f:
        content = f.read()

    question_blocks = content.split("\n---\n")
    current_id_fallback = 1

    for block in question_blocks:
        block = block.strip()
        if not block.startswith("## Question"):
            continue

        lines = block.split('\n')
        # Initialize with defaults or empty values
        question_data = {
            "id": None,
            "text": "",
            "correct_answer": None,
            "distractors": [],
            "source_material": None,
            "image_reference": None,
            "explanation": None,
            "difficulty_score": None,
            "quality_score": None,
            "review_comments": [] # Collect comments from the file if needed
        }
        options_parsed = [] # Temp list to store parsed options [(text, is_correct_marker)]
        parsing_state = None
        delete_question = False

        for line in lines:
            line = line.strip()
            if not line:
                parsing_state = None
                continue

            if line.startswith("## Question"):
                try:
                    question_data["id"] = int(line.split(" ")[2])
                except (IndexError, ValueError):
                    logging.warning(f"Could not parse ID from '{line}', will assign later.")
                parsing_state = None
            elif line.upper() == "DELETE=TRUE":
                delete_question = True
                break
            elif line.upper() == "DELETE=FALSE":
                parsing_state = None
            elif line.startswith("**Source:**"):
                question_data["source_material"] = line.replace("**Source:**", "").strip()
                parsing_state = None
            elif line.startswith("**Image:**"):
                question_data["image_reference"] = line.replace("**Image:**", "").strip()
                parsing_state = None
            elif line.startswith("**Auto-Review Difficulty:**"):
                 try:
                     question_data["difficulty_score"] = float(line.replace("**Auto-Review Difficulty:**", "").strip())
                 except ValueError: pass
                 parsing_state = None
            elif line.startswith("**Auto-Review Quality:**"):
                 try:
                     question_data["quality_score"] = float(line.replace("**Auto-Review Quality:**", "").strip())
                 except ValueError: pass
                 parsing_state = None
            elif line.startswith("**Auto-Review Comments:**"):
                parsing_state = "comments" # Start capturing comments
            elif line.startswith("**Question Text:**"):
                question_data["text"] = "" # Reset text
                rest_of_line = line.replace("**Question Text:**", "").strip()
                if rest_of_line: question_data["text"] += rest_of_line + "\n"
                parsing_state = "text"
            elif line.startswith("**Options:**"):
                 parsing_state = "options"
                 options_parsed = [] # Reset options for this block
            elif line.startswith("**Explanation:**"):
                 question_data["explanation"] = "" # Reset explanation
                 rest_of_line = line.replace("**Explanation:**", "").strip()
                 if rest_of_line: question_data["explanation"] += rest_of_line + "\n"
                 parsing_state = "explanation"
            # --- Parsing multiline fields ---
            elif parsing_state == "text":
                question_data["text"] += line + "\n"
            elif parsing_state == "explanation":
                 question_data["explanation"] += line + "\n"
            elif parsing_state == "comments" and line.startswith("- "):
                 question_data["review_comments"].append(line[2:].strip())
             # --- Parsing options based on marker ---
            elif parsing_state == "options" and line.startswith("- "):
                 # Find the marker (Correct: YES) or (Correct: NO) - case insensitive
                 marker_yes = "(Correct: YES)"
                 marker_no = "(Correct: NO)"
                 is_correct = False
                 option_text = line[2:].strip() # Start with text after "- "

                 # Use uppercase for case-insensitive checks and find
                 option_text_upper = option_text.upper()
                 marker_yes_upper = marker_yes.upper()
                 marker_no_upper = marker_no.upper()

                 if marker_yes_upper in option_text_upper:
                     is_correct = True
                     # Find the position of the uppercase marker in the uppercase string
                     marker_pos = option_text_upper.find(marker_yes_upper)
                     # Extract text *before* the marker position from the *original* string
                     option_text = option_text[:marker_pos].strip()
                 elif marker_no_upper in option_text_upper:
                      is_correct = False
                      # Find the position of the uppercase marker in the uppercase string
                      marker_pos = option_text_upper.find(marker_no_upper)
                      # Extract text *before* the marker position from the *original* string
                      option_text = option_text[:marker_pos].strip()
                 else:
                      # If no marker found, assume it's incorrect and maybe log a warning
                      logging.warning(f"Option in Question ID {question_data.get('id', 'unknown')} missing correctness marker: '{line}'. Assuming incorrect.")
                      is_correct = False

                 options_parsed.append((option_text, is_correct))

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

        # Process parsed options into correct_answer and distractors
        correct_found = None
        temp_distractors = []
        correct_count = 0
        for opt_text, is_correct_flag in options_parsed:
            if is_correct_flag:
                correct_found = opt_text
                correct_count += 1
            else:
                temp_distractors.append(opt_text)

        if correct_count == 1 and correct_found is not None:
             question_data["correct_answer"] = correct_found
             question_data["distractors"] = temp_distractors
        else:
            logging.error(f"Error parsing options for Question ID {question_data['id']}: Found {correct_count} options marked as correct. Skipping question.")
            continue # Skip question if zero or multiple correct answers found

        # Clean up multiline text fields
        question_data["text"] = question_data["text"].strip()
        if question_data["explanation"]:
            question_data["explanation"] = question_data["explanation"].strip()
        else:
             question_data["explanation"] = None # Ensure it's None if empty


        # Basic validation (check essential fields)
        if question_data["text"] and question_data["correct_answer"] is not None and question_data["distractors"]:
            try:
                # Create Question object using keyword arguments
                q = Question(
                    id=question_data["id"],
                    text=question_data["text"],
                    correct_answer=question_data["correct_answer"],
                    distractors=question_data["distractors"],
                    source_material=question_data["source_material"],
                    image_reference=question_data["image_reference"],
                    explanation=question_data["explanation"],
                    difficulty_score=question_data["difficulty_score"],
                    quality_score=question_data["quality_score"],
                    review_comments=question_data["review_comments"] # Pass comments read from file
                )
                questions.append(q)
            except TypeError as e:
                 logging.error(f"Could not create Question object for ID {question_data['id']} due to field mismatch: {e}. Data: {question_data}", exc_info=True)
        elif block: # Only warn if block wasn't empty
             logging.warning(f"Skipping block for Question ID {question_data.get('id', 'unknown')} due to missing essential parts (text, correct answer, or distractors).")

    logging.info(f"Parsed {len(questions)} questions from reviewed Markdown: {markdown_file}")
    return questions 