import base64
import logging
import mimetypes
import os
import random
import re
from typing import List, Optional
from xml.dom import minidom
import html

from ..schemas import QuestionRecord


def _format_text_for_moodle_xml_html(text: str) -> str:
    """
    Converts markdown-like formatting to HTML for Moodle XML.
    Handles bold, italics, code, and LaTeX math intelligently by
    processing code blocks first to prevent accidental formatting of code.
    """
    if not text:
        return ""

    code_snippets = []
    
    # Temporarily replace code blocks with placeholders
    def protect_code(match):
        code_snippets.append(match.group(1))
        return f"__CODE__{len(code_snippets)-1}__"

    # Protect multiline and inline code blocks
    text = re.sub(r'```(.*?)```', protect_code, text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', protect_code, text)

    # Now, format the non-code text
    # Convert bold, but only if it's not part of a word (e.g., word**word)
    text = re.sub(r'(?<!\w)\*\*(?!\s)(.*?)(?<!\s)\*\*(?!\w)', r'<strong>\1</strong>', text)
    # Convert italics, but only if it's not part of a word
    text = re.sub(r'(?<!\w)\*(?!\s)(.*?)(?<!\s)\*(?!\w)', r'<em>\1</em>', text)
    
    # Convert LaTeX math (Moodle-friendly format)
    text = re.sub(r'\$\$(.*?)\$\$', r'\[\1\]', text, flags=re.DOTALL)
    text = re.sub(r'\$(.*?)\$', r'\\(\1\\)', text)

    # Restore code blocks, wrapping them in appropriate tags
    for i, code in enumerate(code_snippets):
        # Determine if it was multiline (contains newline) for <pre> tag
        if '\n' in code:
            text = text.replace(f"__CODE__{i}__", f'<pre><code>{html.escape(code)}</code></pre>')
        else:
            text = text.replace(f"__CODE__{i}__", f'<code>{html.escape(code)}</code>')
            
    return text


def convert_to_moodle_xml(records: List[QuestionRecord], output_file: str, max_image_width: Optional[int] = None, max_image_height: Optional[int] = None):
    """
    Converts questions to Moodle XML format using QuestionRecord, building the XML
    with minidom to properly handle CDATA sections for formatted text.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Converting {len(records)} questions to Moodle XML: {output_file}")

    doc = minidom.Document()
    quiz = doc.createElement("quiz")
    doc.appendChild(quiz)

    # Helper to create a simple element with text, e.g., <tag>text</tag>
    def create_text_element(parent, name, text):
        elem = doc.createElement(name)
        if text is not None:
            elem.appendChild(doc.createTextNode(str(text)))
        parent.appendChild(elem)
        return elem

    # Helper to create an element with a nested <text> child, e.g., <tag><text>text</text></tag>
    def create_sub_text_element(parent, name, text):
        elem = doc.createElement(name)
        text_elem = doc.createElement("text")
        text_elem.appendChild(doc.createTextNode(str(text)))
        elem.appendChild(text_elem)
        parent.appendChild(elem)
        return elem

    # Helper for feedback elements with CDATA
    def create_feedback_element(parent, name, text):
        elem = doc.createElement(name)
        elem.setAttribute("format", "html")
        text_elem = doc.createElement("text")
        text_elem.appendChild(doc.createCDATASection(text))
        elem.appendChild(text_elem)
        parent.appendChild(elem)
        return elem

    for i, record in enumerate(records):
        content = record.get_latest_content()
        question_id = record.question_id
        
        question_elem = doc.createElement("question")
        question_elem.setAttribute("type", "multichoice")
        quiz.appendChild(question_elem)
        
        # Name
        name = doc.createElement("name")
        question_elem.appendChild(name)
        safe_name = re.sub(r'[^\w\s-]', '', content.text[:50])
        create_text_element(name, "text", f"Q{i+1}: {safe_name}")

        # Question Text
        questiontext = doc.createElement("questiontext")
        questiontext.setAttribute("format", "html")
        question_elem.appendChild(questiontext)
        
        q_text_html = f"<p>{_format_text_for_moodle_xml_html(content.text)}</p>"
        
        if record.image_reference:
            image_path = os.path.normpath(os.path.join(os.path.dirname(output_file), record.image_reference))
            try:
                with open(image_path, "rb") as image_file:
                    b64_encoded = base64.b64encode(image_file.read()).decode('utf-8')
                    image_filename = os.path.basename(image_path)
                    
                    style = ""
                    if max_image_width: style += f"width: {max_image_width}px; "
                    if max_image_height: style += f"max-height: {max_image_height}px;"
                    
                    q_text_html += f'<p><img src="@@PLUGINFILE@@/{image_filename}" alt="Question Image" style="{style}"></p>'
                    
                    file_elem = doc.createElement("file")
                    file_elem.setAttribute("name", image_filename)
                    file_elem.setAttribute("path", "/")
                    file_elem.setAttribute("encoding", "base64")
                    file_elem.appendChild(doc.createTextNode(b64_encoded))
                    questiontext.appendChild(file_elem)
            except FileNotFoundError:
                logging.warning(f"Image file not found: {image_path}. Skipping image for question {question_id}.")
            except Exception as e:
                logging.error(f"Error processing image {image_path}: {e}", exc_info=True)

        questiontext_text = doc.createElement("text")
        questiontext.appendChild(questiontext_text)
        questiontext_text.appendChild(doc.createCDATASection(q_text_html))

        # General Feedback
        generalfeedback = doc.createElement("generalfeedback")
        generalfeedback.setAttribute("format", "html")
        question_elem.appendChild(generalfeedback)
        generalfeedback_text = doc.createElement("text")
        generalfeedback.appendChild(generalfeedback_text)
        if content.explanation:
            formatted_explanation = _format_text_for_moodle_xml_html(content.explanation)
            generalfeedback_text.appendChild(doc.createCDATASection(f"<p>{formatted_explanation}</p>"))
        else:
            generalfeedback_text.appendChild(doc.createCDATASection(""))

        # Tags
        tags_elem = doc.createElement("tags")
        question_elem.appendChild(tags_elem)
        latest_eval = record.reviewed.evaluation if record.reviewed and record.reviewed.evaluation else \
                      record.generated.evaluation if record.generated and record.generated.evaluation else None
        if latest_eval:
            if latest_eval.difficulty_score is not None:
                create_sub_text_element(tags_elem, "tag", f"difficulty_{latest_eval.difficulty_score:.2f}")
            if latest_eval.pedagogical_value is not None:
                create_sub_text_element(tags_elem, "tag", f"pedagogy_{latest_eval.pedagogical_value:.2f}")

        # Other metadata
        create_text_element(question_elem, "defaultgrade", "1.0")
        create_text_element(question_elem, "penalty", "0.3333333")
        create_text_element(question_elem, "hidden", "0")
        create_text_element(question_elem, "idnumber", question_id)
        create_text_element(question_elem, "single", "true")
        create_text_element(question_elem, "shuffleanswers", "true")
        create_text_element(question_elem, "answernumbering", "abc")

        # Standard feedback blocks
        create_feedback_element(question_elem, "correctfeedback", "<p>Your answer is correct.</p>")
        create_feedback_element(question_elem, "partiallycorrectfeedback", "<p>Your answer is partially correct.</p>")
        create_feedback_element(question_elem, "incorrectfeedback", "<p>Your answer is incorrect.</p>")

        # Answers
        options = [content.correct_answer] + content.distractors
        random.shuffle(options)

        for option_text in options:
            fraction = "100" if option_text == content.correct_answer else "0"
            answer = doc.createElement("answer")
            answer.setAttribute("fraction", fraction)
            answer.setAttribute("format", "html")
            question_elem.appendChild(answer)

            answer_text = doc.createElement("text")
            answer.appendChild(answer_text)
            formatted_option = _format_text_for_moodle_xml_html(option_text)
            answer_text.appendChild(doc.createCDATASection(f"<p>{formatted_option}</p>"))
            
            create_feedback_element(answer, "feedback", "")

    try:
        pretty_xml = doc.toprettyxml(indent="  ", encoding='utf-8')
        with open(output_file, 'wb') as f:
            f.write(pretty_xml)
        logging.info(f"Successfully converted questions to Moodle XML: {output_file}")
    except Exception as e:
        logging.error(f"Failed to write Moodle XML file {output_file}: {e}", exc_info=True)
