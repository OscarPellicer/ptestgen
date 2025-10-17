import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List
from ..schemas import Question
import html
import random # Needed for shuffling options
import logging
import sys
import re # ADDED for LaTeX escaping

# Placeholder for Wooclap export (e.g., using pandas/openpyxl if Excel)
try:
    import pandas as pd
except ImportError:
    pd = None
    logging.debug("Pandas not found, Wooclap Excel export will be basic text.")


def convert_to_moodle_xml(questions: List[Question], output_file: str):
    """Converts questions to Moodle XML format using new schema."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Converting {len(questions)} questions to Moodle XML: {output_file}")

    quiz = ET.Element("quiz")

    for q_idx, q in enumerate(questions):
        question_elem = ET.SubElement(quiz, "question", type="multichoice")
        name = ET.SubElement(question_elem, "name")
        name_text = ET.SubElement(name, "text")
        name_text.text = f"Q{q.id}_{q.text[:30]}" # Use Q ID

        questiontext = ET.SubElement(question_elem, "questiontext", format="html")
        questiontext_text = ET.SubElement(questiontext, "text")
        # Combine text and image ref if present
        q_text_html = f"<p>{html.escape(q.text)}</p>"
        if q.image_reference:
             q_text_html += f"<p><img src='{html.escape(q.image_reference)}' alt='Question Image'></p>"
        questiontext_text.text = f"<![CDATA[{q_text_html}]]>"

        generalfeedback = ET.SubElement(question_elem, "generalfeedback", format="html")
        generalfeedback_text = ET.SubElement(generalfeedback, "text")
        if q.explanation:
            generalfeedback_text.text = f"<![CDATA[<p>{html.escape(q.explanation)}</p>]]>"
        else:
            generalfeedback_text.text = "<![CDATA[]]>" # Needs to be present

        # Add scores as tags if desired (Moodle XML doesn't have standard fields for this)
        # Example: Using the <tags> element
        tags_elem = ET.SubElement(question_elem, "tags")
        if q.difficulty_score is not None:
            tag_diff = ET.SubElement(tags_elem, "tag")
            ET.SubElement(tag_diff, "text").text = f"difficulty_{q.difficulty_score:.2f}"
        if q.quality_score is not None:
            tag_qual = ET.SubElement(tags_elem, "tag")
            ET.SubElement(tag_qual, "text").text = f"quality_{q.quality_score:.2f}"


        ET.SubElement(question_elem, "defaultgrade").text = "1.0"
        ET.SubElement(question_elem, "penalty").text = "0.3333333" # Default penalty
        ET.SubElement(question_elem, "hidden").text = "0"
        ET.SubElement(question_elem, "idnumber").text = str(q.id) # Use question ID

        ET.SubElement(question_elem, "single").text = "true"
        ET.SubElement(question_elem, "shuffleanswers").text = "true"
        ET.SubElement(question_elem, "answernumbering").text = "abc"

        correctfeedback = ET.SubElement(question_elem, "correctfeedback", format="html")
        ET.SubElement(correctfeedback, "text").text = "<![CDATA[<p>Your answer is correct.</p>]]>"
        partiallycorrectfeedback = ET.SubElement(question_elem, "partiallycorrectfeedback", format="html")
        ET.SubElement(partiallycorrectfeedback, "text").text = "<![CDATA[<p>Your answer is partially correct.</p>]]>"
        incorrectfeedback = ET.SubElement(question_elem, "incorrectfeedback", format="html")
        ET.SubElement(incorrectfeedback, "text").text = "<![CDATA[<p>Your answer is incorrect.</p>]]>"

        # Combine correct answer and distractors
        options = [(q.correct_answer, True)] + [(d, False) for d in q.distractors]
        # Shuffle for the output file presentation within Moodle
        random.shuffle(options)

        for option_text, is_correct in options:
            fraction = "100" if is_correct else "0" # Moodle standard score
            answer = ET.SubElement(question_elem, "answer", fraction=fraction, format="html")
            answer_text = ET.SubElement(answer, "text")
            answer_text.text = f"<![CDATA[<p>{html.escape(option_text)}</p>]]>"
            feedback = ET.SubElement(answer, "feedback", format="html")
            ET.SubElement(feedback, "text").text = "<![CDATA[]]>" # Empty feedback per option

    # Pretty print XML
    try:
        rough_string = ET.tostring(quiz, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')

        with open(output_file, 'wb') as f:
            f.write(pretty_xml)
        logging.info(f"Successfully converted questions to Moodle XML: {output_file}")
    except Exception as e:
         logging.error(f"Failed to write Moodle XML file {output_file}: {e}", exc_info=True)


def convert_to_gift(questions: List[Question], output_file: str):
    """Converts questions to GIFT format using new schema."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Converting {len(questions)} questions to GIFT: {output_file}")

    gift_escape_chars = ['~', '=', '#', '{', '}', ':']
    def escape_gift(text: str) -> str:
        for char in gift_escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    with open(output_file, 'w', encoding='utf-8') as f:
        for q in questions:
            f.write(f"::Q{q.id}:: ") # Question name/ID
            # Question Text + image ref if present
            q_text_escaped = escape_gift(q.text)
            if q.image_reference:
                 # GIFT often needs HTML for images within Moodle
                 q_text_escaped += f"[html]<p><img src='{html.escape(q.image_reference)}' alt=''></p>"

            f.write(f"{q_text_escaped} {{\n")

            # Combine, shuffle, and write options
            options = [(q.correct_answer, True)] + [(d, False) for d in q.distractors]
            random.shuffle(options) # Shuffle order in GIFT file

            for option_text, is_correct in options:
                 option_escaped = escape_gift(option_text)
                 prefix = "=" if is_correct else "~"
                 f.write(f"\t{prefix}{option_escaped}\n")

            # Add explanation as general feedback
            if q.explanation:
                 explanation_escaped = escape_gift(q.explanation)
                 f.write(f"\t#### {explanation_escaped}\n") # General feedback marker

            # Optionally add scores as comments (non-standard)
            # f.write(f"\t// Difficulty: {q.difficulty_score:.2f}\n")
            # f.write(f"\t// Quality: {q.quality_score:.2f}\n")

            f.write("}\n\n")

    logging.info(f"Successfully converted questions to GIFT: {output_file}")


def convert_to_wooclap(questions: List[Question], output_file: str):
    """
    Converts questions to CSV format suitable for Wooclap import,
    with specific columns: Type, Title, Correct, Choice 1, Choice 2, ...
    Backticks in text are replaced with double quotes.
    """
    # Ensure the output file has a .csv extension
    if not output_file.lower().endswith('.csv'):
        base, _ = os.path.splitext(output_file)
        output_file = base + '.csv'
        logging.warning(f"Output filename did not end with .csv, changing to: {output_file}")


    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Attempting to convert {len(questions)} questions to Wooclap CSV: {output_file}")

    if not pd:
         logging.warning("Pandas library not found. Cannot create CSV file for Wooclap. Creating placeholder text file.")
         placeholder_content = "Wooclap CSV export requires the 'pandas' library.\nInstall it with: pip install pandas\n\n"
         for q in questions:
              # Basic text representation for placeholder
              safe_text = q.text.replace('`', '"')
              safe_correct = q.correct_answer.replace('`', '"')
              safe_distractors = [d.replace('`', '"') for d in q.distractors]
              placeholder_content += f"Q{q.id}: {safe_text}\nCorrect: {safe_correct}\nIncorrect: {'; '.join(safe_distractors)}\n\n"
         # Create a .txt placeholder if pandas is missing
         txt_placeholder_file = os.path.splitext(output_file)[0] + ".txt"
         with open(txt_placeholder_file, 'w', encoding='utf-8') as f:
              f.write(placeholder_content)
         logging.info(f"Created placeholder text file: {txt_placeholder_file}")
         return

    # Proceed with Pandas export
    data = []
    max_choices = 0 # Keep track of the maximum number of choices for column definition
    for q in questions:
        # Replace backticks in question text
        title = q.text.replace('`', '"')
        # Base row structure
        row = {'Type': 'MCQ', 'Title': title}
        options = [q.correct_answer] + q.distractors
        current_num_choices = len(options)
        if current_num_choices > max_choices:
            max_choices = current_num_choices

        random.shuffle(options) # Shuffle options for Wooclap display

        correct_index_str = None
        for i, option in enumerate(options):
             # Replace backticks in option text
             safe_option = option.replace('`', '"')
             col_name = f'Choice {i+1}'
             row[col_name] = safe_option
             if option == q.correct_answer:
                 correct_index_str = str(i+1) # Wooclap often uses 1-based index

        # Assert that exactly one correct answer index was found (for MCQ)
        assert correct_index_str is not None, f"Correct answer not found in options for question ID {q.id}"
        row['Correct'] = correct_index_str

        # Remove previously added extra columns implicitly by not adding them here
        # row['Explanation'] = ...
        # row['Difficulty'] = ...
        # row['Quality'] = ...

        data.append(row)

    if data:
        # Define the exact column order dynamically based on max_choices
        choice_cols = [f'Choice {i+1}' for i in range(max_choices)]
        column_order = ['Type', 'Title', 'Correct'] + choice_cols

        # Create DataFrame, Pandas handles missing columns (e.g., if one question has fewer choices)
        df = pd.DataFrame(data)
        # Reindex to ensure the exact column order and include all necessary choice columns
        df = df.reindex(columns=column_order)

        try:
            # Write to CSV file without pandas index, using specified order
            df.to_csv(output_file, index=False, encoding='utf-8', columns=column_order)
            logging.info(f"Successfully converted {len(questions)} questions to Wooclap CSV: {output_file}")
        except Exception as e:
             logging.error(f"Failed to write Wooclap CSV file {output_file}: {e}", exc_info=True)
    else:
        logging.info("No questions to convert to Wooclap format.")


def escape_latex(text: str) -> str:
    """
    Escapes special LaTeX characters in a given string for R/exams.
    Aims to make text suitable for inclusion in Rmd files that become LaTeX.

    This has been DEPRECATED: now the prompt specifies that any special characters
    or code blocks should be enclosed in backticks, which are correctly handled by R/exams.
    """    
    return text

def prepare_for_rexams(questions: List[Question], output_dir: str):
    """Prepares question files (.Rmd) for R/exams using new schema."""
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Preparing {len(questions)} R/exams files in directory: {output_dir}")

    for i, q in enumerate(questions):
        # Create a unique filename
        q_filename = f"question_{q.id}_{i+1}.Rmd"
        q_filepath = os.path.join(output_dir, q_filename)

        try:
            with open(q_filepath, 'w', encoding='utf-8') as f:
                # For q.text
                logging.debug(f"R/exams PRE-ESCAPE TEXT: '{q.text}'")
                escaped_q_text = escape_latex(q.text)
                logging.debug(f"R/exams POST-ESCAPE TEXT: '{escaped_q_text}'")
                f.write(f"Question\n")
                f.write(f"========\n")
                f.write(f"{escaped_q_text}\n\n") # Use the logged variable

                if q.image_reference:
                    image_filename = os.path.basename(q.image_reference)
                    # Note: User needs to ensure the image is accessible relative to Rmd
                    f.write(f"```{'{r}'} include_graphics('{image_filename}')\n```\n\n")

                # Combine options and create solution list
                options_list = [q.correct_answer] + q.distractors
                # Create solution string (1 for correct, 0 for incorrect)
                # The order MUST match the options_list before shuffling for R/exams
                solution_bitstring = "1" + ("0" * len(q.distractors))

                f.write(f"Questionlist\n")
                f.write(f"------------\n")
                # Write options (R/exams handles shuffling based on exshuffle)
                for option_text_original in options_list:
                    logging.debug(f"R/exams PRE-ESCAPE OPTION: '{option_text_original}'")
                    option_text_escaped = escape_latex(option_text_original)
                    logging.debug(f"R/exams POST-ESCAPE OPTION: '{option_text_escaped}'")
                    f.write(f"* {option_text_escaped}\n") # Use the logged variable
                f.write("\n")

                # R/exams doesn't typically show the solution list directly in basic Rmd
                # It uses the meta-information section.

                f.write(f"Solution\n")
                f.write(f"========\n")
                # Provide explanation here
                if q.explanation:
                    logging.debug(f"R/exams PRE-ESCAPE EXPLANATION: '{q.explanation}'")
                    escaped_explanation = escape_latex(q.explanation)
                    logging.debug(f"R/exams POST-ESCAPE EXPLANATION: '{escaped_explanation}'")
                    f.write(f"{escaped_explanation}\n\n") # Use the logged variable
                else:
                    # Add correct answer text if no explanation provided
                    logging.debug(f"R/exams PRE-ESCAPE CORRECT_ANSWER_FOR_SOLUTION: '{q.correct_answer}'")
                    escaped_correct_answer = escape_latex(q.correct_answer)
                    logging.debug(f"R/exams POST-ESCAPE CORRECT_ANSWER_FOR_SOLUTION: '{escaped_correct_answer}'")
                    f.write(f"The correct answer is: {escaped_correct_answer}\n\n") # Use the logged variable


                f.write(f"Meta-information\n")
                f.write(f"================\n")
                f.write(f"exname: Question {q.id}\n")
                f.write(f"extype: mchoice\n") # Multiple choice
                f.write(f"exsolution: {solution_bitstring}\n") # Solution bitstring
                f.write(f"exshuffle: TRUE\n") # Allow shuffling (TRUE or integer > 1 for sample size)
                
                # Use the latest evaluation data available
                latest_eval = q.reviewed_evaluation or q.initial_evaluation
                if latest_eval:
                    if latest_eval.difficulty_score is not None:
                        f.write(f"exextra[difficulty]: {latest_eval.difficulty_score:.2f}\n")
                    if latest_eval.pedagogical_value is not None: # Example of another metric
                        f.write(f"exextra[pedagogy]: {latest_eval.pedagogical_value:.2f}\n")


            logging.debug(f"  - Created R/exams file: {q_filepath}")

        except Exception as e:
            logging.error(f"Failed to create R/exams file {q_filepath}: {e}", exc_info=True)

    logging.info(f"Finished preparing R/exams files.") 