import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List
from ..schemas import QuestionRecord
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


def convert_to_moodle_xml(records: List[QuestionRecord], output_file: str):
    """Converts questions to Moodle XML format using QuestionRecord."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Converting {len(records)} questions to Moodle XML: {output_file}")

    quiz = ET.Element("quiz")

    for i, record in enumerate(records):
        content = record.get_latest_content()
        question_id = record.question_id
        
        question_elem = ET.SubElement(quiz, "question", type="multichoice")
        name = ET.SubElement(question_elem, "name")
        name_text = ET.SubElement(name, "text")
        name_text.text = f"Q{i+1}_{content.text[:30]}"

        questiontext = ET.SubElement(question_elem, "questiontext", format="html")
        questiontext_text = ET.SubElement(questiontext, "text")
        q_text_html = f"<p>{html.escape(content.text)}</p>"
        if record.image_reference:
             q_text_html += f"<p><img src='{html.escape(record.image_reference)}' alt='Question Image'></p>"
        questiontext_text.text = f"<![CDATA[{q_text_html}]]>"

        generalfeedback = ET.SubElement(question_elem, "generalfeedback", format="html")
        generalfeedback_text = ET.SubElement(generalfeedback, "text")
        if content.explanation:
            generalfeedback_text.text = f"<![CDATA[<p>{html.escape(content.explanation)}</p>]]>"
        else:
            generalfeedback_text.text = "<![CDATA[]]>" # Needs to be present

        # Add scores as tags if desired (Moodle XML doesn't have standard fields for this)
        # Example: Using the <tags> element
        tags_elem = ET.SubElement(question_elem, "tags")
        
        # Get the latest evaluation data from the record
        latest_eval = None
        if record.reviewed and record.reviewed.evaluation:
            latest_eval = record.reviewed.evaluation
        elif record.generated and record.generated.evaluation:
            latest_eval = record.generated.evaluation

        if latest_eval:
            if latest_eval.difficulty_score is not None:
                tag_diff = ET.SubElement(tags_elem, "tag")
                ET.SubElement(tag_diff, "text").text = f"difficulty_{latest_eval.difficulty_score:.2f}"
            if latest_eval.pedagogical_value is not None: # Assuming quality_score was a typo for pedagogical_value
                tag_qual = ET.SubElement(tags_elem, "tag")
                ET.SubElement(tag_qual, "text").text = f"pedagogy_{latest_eval.pedagogical_value:.2f}"


        ET.SubElement(question_elem, "defaultgrade").text = "1.0"
        ET.SubElement(question_elem, "penalty").text = "0.3333333" # Default penalty
        ET.SubElement(question_elem, "hidden").text = "0"
        ET.SubElement(question_elem, "idnumber").text = question_id # Use question ID

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
        options = [content.correct_answer] + content.distractors
        # Shuffle for the output file presentation within Moodle
        random.shuffle(options)

        for option_text in options:
            is_correct = (option_text == content.correct_answer)
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


def convert_to_gift(records: List[QuestionRecord], output_file: str):
    """Converts questions to GIFT format using QuestionRecord."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Converting {len(records)} questions to GIFT: {output_file}")

    gift_escape_chars = ['~', '=', '#', '{', '}', ':']
    def escape_gift(text: str) -> str:
        for char in gift_escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    with open(output_file, 'w', encoding='utf-8') as f:
        for i, record in enumerate(records):
            content = record.get_latest_content()
            f.write(f"::Q{i+1}::{record.question_id}:: ") # Question name/ID
            # Question Text + image ref if present
            q_text_escaped = escape_gift(content.text)
            if record.image_reference:
                 # GIFT often needs HTML for images within Moodle
                 q_text_escaped += f"[html]<p><img src='{html.escape(record.image_reference)}' alt=''></p>"

            f.write(f"{q_text_escaped} {{\n")

            # Combine, shuffle, and write options
            options = [content.correct_answer] + content.distractors
            random.shuffle(options) # Shuffle order in GIFT file

            for option_text in options:
                 option_escaped = escape_gift(option_text)
                 prefix = "=" if option_text == content.correct_answer else "~"
                 f.write(f"\t{prefix}{option_escaped}\n")

            # Add explanation as general feedback
            if content.explanation:
                 explanation_escaped = escape_gift(content.explanation)
                 f.write(f"\t#### {explanation_escaped}\n") # General feedback marker

            # Optionally add scores as comments (non-standard)
            # f.write(f"\t// Difficulty: {q.difficulty_score:.2f}\n")
            # f.write(f"\t// Quality: {q.quality_score:.2f}\n")

            f.write("}\n\n")

    logging.info(f"Successfully converted questions to GIFT: {output_file}")


def convert_to_wooclap(records: List[QuestionRecord], output_file: str):
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
    logging.info(f"Attempting to convert {len(records)} questions to Wooclap CSV: {output_file}")

    if not pd:
         logging.warning("Pandas library not found. Cannot create CSV file for Wooclap. Creating placeholder text file.")
         placeholder_content = "Wooclap CSV export requires the 'pandas' library.\nInstall it with: pip install pandas\n\n"
         for record in records:
              content = record.get_latest_content()
              # Basic text representation for placeholder
              safe_text = content.text.replace('`', '"')
              safe_correct = content.correct_answer.replace('`', '"')
              safe_distractors = [d.replace('`', '"') for d in content.distractors]
              placeholder_content += f"Q{record.question_id}: {safe_text}\nCorrect: {safe_correct}\nIncorrect: {'; '.join(safe_distractors)}\n\n"
         # Create a .txt placeholder if pandas is missing
         txt_placeholder_file = os.path.splitext(output_file)[0] + ".txt"
         with open(txt_placeholder_file, 'w', encoding='utf-8') as f:
              f.write(placeholder_content)
         logging.info(f"Created placeholder text file: {txt_placeholder_file}")
         return

    # Proceed with Pandas export
    data = []
    max_choices = 0 # Keep track of the maximum number of choices for column definition
    for record in records:
        content = record.get_latest_content()
        # Replace backticks in question text
        title = content.text.replace('`', '"')
        # Base row structure
        row = {'Type': 'MCQ', 'Title': title}
        options = [content.correct_answer] + content.distractors
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
             if option == content.correct_answer:
                 correct_index_str = str(i+1) # Wooclap often uses 1-based index

        # Assert that exactly one correct answer index was found (for MCQ)
        assert correct_index_str is not None, f"Correct answer not found in options for question ID {record.question_id}"
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
            logging.info(f"Successfully converted {len(records)} questions to Wooclap CSV: {output_file}")
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

def prepare_for_rexams(records: List[QuestionRecord], output_dir: str):
    """Prepares question files (.Rmd) for R/exams using new schema."""
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Preparing {len(records)} R/exams files in directory: {output_dir}")

    # --- Sanitize quotes before writing ---
    quotes_found_warning = False
    for record in records:
        content = record.get_latest_content()
        if '"' in content.text:
            content.text = content.text.replace('"', "'")
            quotes_found_warning = True
        if '"' in content.correct_answer:
            content.correct_answer = content.correct_answer.replace('"', "'")
            quotes_found_warning = True
        for i, distractor in enumerate(content.distractors):
            if '"' in distractor:
                content.distractors[i] = distractor.replace('"', "'")
                quotes_found_warning = True
    
    if quotes_found_warning:
        logging.warning("Replaced double quotes with single quotes in questions for R/exams preparation.")
    # --- End sanitization ---

    for i, record in enumerate(records):
        content = record.get_latest_content()
        # Create a unique filename
        q_filename = f"question_{record.question_id}_{i+1}.Rmd"
        q_filepath = os.path.join(output_dir, q_filename)

        try:
            # --- Build the file content in memory ---
            rmd_content = []
            
            escaped_q_text = escape_latex(content.text)
            rmd_content.append("Question")
            rmd_content.append("========")
            rmd_content.append(f"{escaped_q_text}\n")

            if record.image_reference:
                image_filename = os.path.basename(record.image_reference)
                rmd_content.append(f"```{'{r}'} include_graphics('{image_filename}')\n```\n")

            options_list = [content.correct_answer] + content.distractors
            solution_bitstring = "1" + ("0" * len(content.distractors))

            rmd_content.append("Questionlist")
            rmd_content.append("------------")
            for option in options_list:
                escaped_option = escape_latex(option)
                rmd_content.append(f"* {escaped_option}")

            rmd_content.append("\nSolution") # Add newline before Solution
            rmd_content.append("========")
            if content.explanation:
                escaped_explanation = escape_latex(content.explanation)
                rmd_content.append(f"{escaped_explanation}\n")
            else:
                escaped_correct_answer = escape_latex(content.correct_answer)
                rmd_content.append(f"The correct answer is: {escaped_correct_answer}\n")
            
            rmd_content.append("") # Add blank line before Meta-information

            rmd_content.append("Meta-information")
            rmd_content.append("================")
            rmd_content.append(f"exname: Question {record.question_id}")
            rmd_content.append(f"extype: mchoice")
            rmd_content.append(f"exsolution: {solution_bitstring}")
            rmd_content.append(f"exshuffle: TRUE")
            
            latest_eval = None
            if record.reviewed and record.reviewed.evaluation:
                latest_eval = record.reviewed.evaluation
            elif record.generated and record.generated.evaluation:
                latest_eval = record.generated.evaluation

            if latest_eval:
                if latest_eval.difficulty_score is not None:
                    rmd_content.append(f"exdifficulty: {int(latest_eval.difficulty_score * 100)}")

            final_rmd_str = "\n".join(rmd_content)
            
            # --- Temporary Debugging ---
            logging.debug(f"--- RMD CONTENT FOR {q_filename} ---\n{final_rmd_str}\n------------------------------------")
            
            with open(q_filepath, 'w', encoding='utf-8') as f:
                f.write(final_rmd_str)

        except Exception as e:
            logging.error(f"Failed to create R/exams file {q_filepath}: {e}", exc_info=True)

    logging.info(f"Finished preparing R/exams files.") 