import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List
from ..schemas import Question
import html
import random # Needed for shuffling options
import logging
import sys

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
    Converts questions to Excel format suitable for Wooclap import.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Attempting to convert {len(questions)} questions to Wooclap Excel: {output_file}")

    if not pd:
         logging.warning("Pandas library not found. Cannot create Excel file for Wooclap. Creating placeholder text file.")
         placeholder_content = "Wooclap Excel export requires the 'pandas' and 'openpyxl' libraries.\nInstall them with: pip install pandas openpyxl\n\n"
         for q in questions:
              placeholder_content += f"Q{q.id}: {q.text}\nCorrect: {q.correct_answer}\nIncorrect: {'; '.join(q.distractors)}\n\n"
         with open(output_file.replace(".xlsx", ".txt"), 'w', encoding='utf-8') as f:
              f.write(placeholder_content)
         return

    # Proceed with Pandas export
    data = []
    for q in questions:
        # Wooclap format often requires specific columns. This is a guess.
        # Check Wooclap's import template for exact requirements.
        # Common format: Question | Option 1 | Option 2 | ... | Correct Answer(s) Index/Text
        row = {'Type': 'MCQ', 'Question': q.text} # Add Type column
        options = [q.correct_answer] + q.distractors
        random.shuffle(options) # Shuffle options for Wooclap display

        correct_indices = []
        for i, option in enumerate(options):
             row[f'Choice {i+1}'] = option
             if option == q.correct_answer:
                 correct_indices.append(str(i+1)) # Wooclap often uses 1-based index

        row['Correct Answer(s)'] = ", ".join(correct_indices) # Comma-separated indices
        row['Explanation'] = q.explanation if q.explanation else "" # Add explanation if present
        # Add scores if needed/supported by Wooclap import
        row['Difficulty'] = f"{q.difficulty_score:.2f}" if q.difficulty_score is not None else ""
        row['Quality'] = f"{q.quality_score:.2f}" if q.quality_score is not None else ""

        data.append(row)

    if data:
        df = pd.DataFrame(data)
        try:
            # Ensure openpyxl is installed for .xlsx writing
            df.to_excel(output_file, index=False, engine='openpyxl')
            logging.info(f"Successfully converted {len(questions)} questions to Wooclap Excel: {output_file}")
        except ImportError:
             logging.error("`openpyxl` library is required for Excel export but not found. Install with `pip install openpyxl`")
             print("Error: openpyxl needed for Excel export. Install it: pip install openpyxl", file=sys.stderr)
        except Exception as e:
             logging.error(f"Failed to write Wooclap Excel file {output_file}: {e}", exc_info=True)
    else:
        logging.info("No questions to convert to Wooclap format.")


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
                f.write(f"Question\n")
                f.write(f"========\n")
                f.write(f"{q.text}\n\n")

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
                for option_text in options_list:
                    f.write(f"* {option_text}\n")
                f.write("\n")

                # R/exams doesn't typically show the solution list directly in basic Rmd
                # It uses the meta-information section.

                f.write(f"Solution\n")
                f.write(f"========\n")
                # Provide explanation here
                if q.explanation:
                    f.write(f"{q.explanation}\n\n")
                else:
                    # Add correct answer text if no explanation provided
                     f.write(f"The correct answer is: {q.correct_answer}\n\n")


                f.write(f"Meta-information\n")
                f.write(f"================\n")
                f.write(f"exname: Question {q.id}\n")
                f.write(f"extype: mchoice\n") # Multiple choice
                f.write(f"exsolution: {solution_bitstring}\n") # Solution bitstring
                f.write(f"exshuffle: TRUE\n") # Allow shuffling (TRUE or integer > 1 for sample size)
                # Add scores as extras? (non-standard R/exams, might be used by custom templates)
                if q.difficulty_score is not None:
                    f.write(f"exextra[difficulty]: {q.difficulty_score:.2f}\n")
                if q.quality_score is not None:
                     f.write(f"exextra[quality]: {q.quality_score:.2f}\n")

            logging.debug(f"  - Created R/exams file: {q_filepath}")

        except Exception as e:
            logging.error(f"Failed to create R/exams file {q_filepath}: {e}", exc_info=True)

    logging.info(f"Finished preparing R/exams files.") 