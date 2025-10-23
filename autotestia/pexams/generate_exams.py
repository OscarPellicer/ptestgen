import logging
from typing import List, Optional, Union
import random
import os
import markdown
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from faker import Faker
import cv2
import numpy as np

from .schemas import PexamQuestion, PexamExam
from . import layout
from .translations import LANG_STRINGS

def _generate_answer_sheet_html(
    questions: List[PexamQuestion],
    exam_model: int,
    exam_title: str,
    exam_course: Optional[str],
    exam_date: Optional[str],
    lang: str = "en",
    id_length: int = 10
) -> str:
    """Generates the pure HTML for the answer sheet with absolutely positioned elements."""

    selected_lang = LANG_STRINGS.get(lang, LANG_STRINGS["en"])
    
    layout_data = layout.get_answer_sheet_layout(len(questions), id_length)
    html_elements = []

    # --- Header Elements ---
    style_title = f"position: absolute; left: {layout_data.exam_title[0]}mm; top: {layout_data.exam_title[1]}mm;"
    html_elements.append(f'<h1 class="exam-title" style="{style_title}">{exam_title}</h1>')

    style_subtitle = f"position: absolute; left: {layout_data.exam_subtitle[0]}mm; top: {layout_data.exam_subtitle[1]}mm;"
    html_elements.append(f'<h2 class="exam-subtitle" style="{style_subtitle}">{selected_lang["title"]} {exam_model}</h2>')
    
    exam_info_parts = []
    if exam_course: exam_info_parts.append(f"<span>{selected_lang['course']}: {exam_course}</span>")
    if exam_date: exam_info_parts.append(f"<span>{selected_lang['date']}: {exam_date}</span>")
    exam_info_html = "\n".join(exam_info_parts)
    style_info = f"position: absolute; left: {layout_data.exam_info[0]}mm; top: {layout_data.exam_info[1]}mm;"
    html_elements.append(f'<div class="exam-info" style="{style_info}">{exam_info_html}</div>')

    # --- Student Info ---
    style_name_label = f"position: absolute; left: {layout_data.student_name_label[0]}mm; top: {layout_data.student_name_label[1]}mm;"
    html_elements.append(f'<div class="student-name-label" style="{style_name_label}"><b>{selected_lang["name"]}</b></div>')
    
    snb_coords = layout_data.student_name_box
    x_snb, y_snb = snb_coords.top_left
    w_snb = snb_coords.bottom_right[0] - x_snb
    h_snb = snb_coords.bottom_right[1] - y_snb
    style_name_box = f"position: absolute; left: {x_snb}mm; top: {y_snb}mm; width: {w_snb}mm; height: {h_snb}mm;"
    html_elements.append(f'<div class="student-name-box" style="{style_name_box}"></div>')

    style_id_label = f"position: absolute; left: {layout_data.student_id_label[0]}mm; top: {layout_data.student_id_label[1]}mm;"
    html_elements.append(f'<div class="student-id-label" style="{style_id_label}"><b>{selected_lang["id"]}</b></div>')
    
    for id_box_coords in layout_data.student_id_boxes:
        x, y = id_box_coords.top_left
        w = id_box_coords.bottom_right[0] - x
        h = id_box_coords.bottom_right[1] - y
        style = f"position: absolute; left: {x}mm; top: {y}mm; width: {w}mm; height: {h}mm;"
        html_elements.append(f'<div class="id-box" style="{style}"></div>')

    # --- Signature ---
    style_sig_label = f"position: absolute; left: {layout_data.student_signature_label[0]}mm; top: {layout_data.student_signature_label[1]}mm;"
    html_elements.append(f'<div class="student-signature-label" style="{style_sig_label}"><b>{selected_lang["signature"]}</b></div>')

    ssb_coords = layout_data.student_signature_box
    x_ssb, y_ssb = ssb_coords.top_left
    w_ssb = ssb_coords.bottom_right[0] - x_ssb
    h_ssb = ssb_coords.bottom_right[1] - y_ssb
    style_sig_box = f"position: absolute; left: {x_ssb}mm; top: {y_ssb}mm; width: {w_ssb}mm; height: {h_ssb}mm;"
    html_elements.append(f'<div class="student-signature-box" style="{style_sig_box}"></div>')

    # --- Instructions ---
    example_correct_html = '<div class="example-box correct"></div>'
    example_incorrect_html = '<div class="example-box incorrect"><div class="incorrect-line"></div></div>'

    instructions_html = f"""
    <div class="instructions-box">
        <h4>{selected_lang.get('instructions_title', 'Instructions')}</h4>
        <ul>
            <li>{selected_lang.get('instructions_id', '')}</li>
            <li>{selected_lang.get('instructions_answers', '')}</li>
            <li class="instruction-example-container">
                <div class="instruction-example">
                    <span>{selected_lang.get('instructions_example_correct', '')}</span>
                    {example_correct_html}
                </div>
                <div class="instruction-example">
                    <span>{selected_lang.get('instructions_example_incorrect', '')}</span>
                    {example_incorrect_html}
                </div>
            </li>
            <li>{selected_lang.get('instructions_corrections', '')}</li>
        </ul>
    </div>
    """
    style_instructions = f"position: absolute; left: {layout_data.instructions[0]}mm; top: {layout_data.instructions[1]}mm;"
    html_elements.append(f'<div style="{style_instructions}">{instructions_html}</div>')

    # --- Answer Grid Elements ---
    for group_index, labels in layout_data.header_labels.items():
        for i, (x, y) in labels.items():
            label = chr(ord("A") + i)
            style = (f"position: absolute; left: {x}mm; top: {y}mm; "
                     f"width: {layout.HEADER_OPTION_LABEL_WIDTH}mm; height: {layout.HEADER_ROW_HEIGHT}mm;")
            html_elements.append(f'<div class="header-option" style="{style}">{label}</div>')

    for q_id, (x, y) in layout_data.question_numbers.items():
        style = (f"position: absolute; left: {x}mm; top: {y}mm; "
                 f"width: {layout.QUESTION_NUMBER_WIDTH}mm; height: {layout.ANSWER_ROW_HEIGHT}mm;")
        html_elements.append(f'<div class="question-number" style="{style}">{q_id}</div>')

    for q_id, options in layout_data.answer_boxes.items():
        for opt_idx, coords in options.items():
            x, y = coords.top_left
            style = (f"position: absolute; left: {x}mm; top: {y}mm; "
                     f"width: {layout.OPTION_BOX_WIDTH}mm; height: {layout.OPTION_BOX_HEIGHT}mm;")
            html_elements.append(f'<div class="option-box" style="{style}"></div>')
            
    all_elements_html = "\n".join(html_elements)

    return f"""
<div class="page-container answer-sheet-page">
    <div class="fiducial top-left"></div>
    <div class="fiducial top-right"></div>
    <div class="fiducial bottom-left"></div>
    <div class="fiducial bottom-right"></div>
    {all_elements_html}
</div>
"""


def _generate_questions_markdown(
    questions: List[PexamQuestion]
) -> str:
    """Generates the Markdown for the question pages."""
    md_parts = []
    for q in questions:
        md_parts.append('\n<div class="question-wrapper">\n')

        # Convert question text to HTML, ensuring it's treated as a single paragraph block
        question_text_html = markdown.markdown(q.text.replace('\n', ' <br> ')).strip()
        # Remove paragraph tags that markdown lib might add
        if question_text_html.startswith("<p>"):
            question_text_html = question_text_html[3:-4]
        
        md_parts.append(f'<div class="question-text"><b>{q.id}.</b> {question_text_html}</div>\n')
        
        if q.image_source:
            src = q.image_source
            if os.path.exists(src):
                src = f"file:///{os.path.abspath(src)}"
            md_parts.append(f'<img src="{src}" alt="Image for question {q.id}">\n')

        md_parts.append('<div class="options-block">')
        for i, option in enumerate(q.options):
            option_label = chr(ord('A') + i)
            # Convert option text to HTML, ensuring it's a single paragraph block
            option_text_html = markdown.markdown(option.text.replace('\n', ' <br> ')).strip()
            if option_text_html.startswith("<p>"):
                option_text_html = option_text_html[3:-4]

            md_parts.append(f'<div class="option-item"><span class="option-label"><b>{option_label})</b></span><span class="option-text">{option_text_html}</span></div>')
        md_parts.append("</div>") # Close options-block
            
        md_parts.append('</div>\n')

    return "\n".join(md_parts)


def generate_exams(
    questions: Union[List[PexamQuestion], str], 
    output_dir: str, 
    num_models: int = 4, 
    exam_title: str = "Final Exam",
    exam_course: Optional[str] = None,
    exam_date: Optional[str] = None,
    columns: int = 1,
    id_length: int = 10,
    lang: str = "en",
    keep_html: bool = False,
    font_size: str = "11pt",
    test_mode: bool = False
):
    """
    Generates exam PDFs from a list of questions using Playwright.
    The questions can be provided as a list of PexamQuestion objects or a path to a JSON file.
    """
    logging.info(f"Starting pexams PDF generation.")
    
    if isinstance(questions, str):
        if not os.path.exists(questions):
            logging.error(f"Questions JSON file not found at: {questions}")
            return
        logging.info(f"Loading questions from: {questions}")
        try:
            loaded_exam = PexamExam.model_validate_json(Path(questions).read_text(encoding="utf-8"))
        except Exception as e:
            logging.error(f"Failed to parse questions JSON file: {e}")
            return
        questions_list = loaded_exam.questions
    else:
        questions_list = questions

    logging.info(f"Loaded {len(questions_list)} questions.")
    logging.info(f"Exams will be output to: {output_dir}")

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
        logging.info(f"Created output directory: {output_dir}")
        
    css_path = os.path.join(os.path.dirname(__file__), "pexams.css")
    if not os.path.exists(css_path):
        logging.error(f"CSS theme not found at {css_path}. Cannot generate exams.")
        return
        
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    column_classes = {1: "", 2: "two-columns", 3: "three-columns"}
    column_class = column_classes.get(columns, "")

    for i in range(1, num_models + 1):
        model_questions = list(questions_list)
        random.shuffle(model_questions)
        
        # Re-number questions for this exam model
        for q_idx, q in enumerate(model_questions, 1):
            q.id = q_idx

        # Save the questions for this model to a JSON file
        model_exam = PexamExam(questions=model_questions)
        questions_json_path = os.path.join(output_dir, f"exam_model_{i}_questions.json")
        with open(questions_json_path, "w", encoding="utf-8") as f:
            f.write(model_exam.model_dump_json(indent=4))
        logging.info(f"Saved questions for model {i} to: {questions_json_path}")

        answer_sheet_html = _generate_answer_sheet_html(
            model_questions, 
            i, 
            exam_title=exam_title,
            exam_course=exam_course,
            exam_date=exam_date,
            lang=lang, 
            id_length=id_length
        )
        questions_md = _generate_questions_markdown(model_questions)
        questions_html = markdown.markdown(questions_md, extensions=['fenced_code', 'codehilite'])
        
        final_html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{exam_title} - Model {i}</title>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,300..800;1,300..800&family=Roboto:ital,wght@0,300;0,400;0,500;0,700&display=swap">
    <style>
        {css_content}
    </style>
    <style>
        body {{ font-size: {font_size}; }}
    </style>
</head>
<body>
    {answer_sheet_html}
    <div class="page-container" style="page-break-after: always;"></div>
    <div class="page-container questions-container {column_class}">
        {questions_html}
    </div>
</body>
</html>
"""
        html_filepath = os.path.join(output_dir, f"exam_model_{i}.html")
        pdf_filepath = os.path.join(output_dir, f"exam_model_{i}.pdf")

        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(final_html_content)
        logging.info(f"Generated HTML for exam model {i}: {html_filepath}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                # Use file:// protocol to load the local HTML file
                page.goto(f"file:///{os.path.abspath(html_filepath)}")
                
                header_text = f"{exam_title} - {exam_date}" if exam_date else exam_title

                page.pdf(
                    path=pdf_filepath,
                    format='A4',
                    print_background=True,
                    margin={'top': '15mm', 'bottom': '15mm', 'left': '15mm', 'right': '15mm'},
                    display_header_footer=True,
                    header_template=f'<div style="font-family: Open Sans, sans-serif; font-size: 9px; color: #888; width: 100%; text-align: center;">{header_text}</div>',
                    footer_template=f'<div style="font-family: Open Sans, sans-serif; font-size: 9px; color: #888; width: 100%; text-align: center;">Model {i} - Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>'
                )
                browser.close()
            logging.info(f"Successfully generated PDF for model {i}: {pdf_filepath}")

            if test_mode:
                logging.info(f"Test mode enabled: Generating simulated scan for model {i}")
                _generate_simulated_scan(pdf_filepath, model_questions, output_dir, i)

        except PlaywrightError as e:
            logging.error(f"Playwright failed to generate PDF for model {i}: {e}")
            logging.error("Have you installed the browser binaries? Try running 'playwright install'")
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred while generating PDF for model {i}: {e}")
            break
        finally:
            if not keep_html and os.path.exists(html_filepath):
                os.remove(html_filepath)
                logging.info(f"Removed temporary HTML file: {html_filepath}")

def _generate_simulated_scan(original_pdf_path: str, questions: List[PexamQuestion], output_dir: str, model_num: int):
    """
    Takes the first page of a PDF, converts it to an image,
    and adds fake answers, name, ID, and signature to simulate a scan.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logging.error("pdf2image is required for test mode. Please install it.")
        return

    fake = Faker()
    scan_output_dir = os.path.join(output_dir, "simulated_scans")
    os.makedirs(scan_output_dir, exist_ok=True)

    # 1. Convert first page of PDF to an image
    try:
        images = convert_from_path(original_pdf_path, first_page=1, last_page=1, dpi=300)
        if not images: return
        page_image = images[0]
        img_np = np.array(page_image)
        img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        logging.error(f"Failed to convert PDF to image for simulation: {e}")
        return

    # Define coordinate transformation constants
    DPI = 300
    MM_PER_INCH = 25.45
    PX_PER_MM = DPI / MM_PER_INCH
    MARGIN_MM = 15 # The margin used when generating the PDF
    
    # Add a small adjustment to shift content down and to the right
    ADJUSTMENT_MM = 2 

    offset_x = int((MARGIN_MM + ADJUSTMENT_MM) * PX_PER_MM)
    offset_y = int((MARGIN_MM + ADJUSTMENT_MM) * PX_PER_MM)

    # 2. Get layout data
    layout_data = layout.get_answer_sheet_layout(len(questions))

    # 3. Add fake data
    # Fake Name
    name_box = layout_data.student_name_box
    name_pos = (
        int(name_box.top_left[0] * PX_PER_MM) + offset_x + 10,
        int(name_box.center[1] * PX_PER_MM) + offset_y + 15
    )
    cv2.putText(img_cv, fake.name(), name_pos, cv2.FONT_HERSHEY_SIMPLEX, 2, (20, 20, 20), 4)

    # Fake ID
    fake_id = "".join(random.choices("0123456789", k=len(layout_data.student_id_boxes)))
    for i, box in enumerate(layout_data.student_id_boxes):
        text = fake_id[i]
        font_scale = 1.8
        font_thickness = 4
        (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        
        center_x_px = int(box.center[0] * PX_PER_MM) + offset_x
        center_y_px = int(box.center[1] * PX_PER_MM) + offset_y
        
        id_pos = (center_x_px - text_width // 2, center_y_px + text_height // 2)
        cv2.putText(img_cv, text, id_pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (20, 20, 20), font_thickness)

    # Fake Signature (scribble)
    sig_box = layout_data.student_signature_box
    center_y = int(sig_box.center[1] * PX_PER_MM) + offset_y
    start_x = int(sig_box.top_left[0] * PX_PER_MM) + offset_x + 15
    end_x = int(sig_box.bottom_right[0] * PX_PER_MM) + offset_x - 15
    for x in range(start_x, end_x, 10):
        y_offset = random.randint(-20, 20)
        cv2.line(img_cv, (x, center_y + y_offset), (x+10, center_y - y_offset), (30, 30, 30), 4)

    # Fake Answers (more realistic filling)
    for q_id, options in layout_data.answer_boxes.items():
        if random.random() > 0.1: # 10% chance to leave blank
            chosen_option = random.choice(list(options.values()))
            
            tl_x_mm, tl_y_mm = chosen_option.top_left
            br_x_mm, br_y_mm = chosen_option.bottom_right

            # Calculate pixel coordinates directly from the answer box layout, adding the page margin offset.
            tl_x = int(tl_x_mm * PX_PER_MM) + offset_x
            tl_y = int(tl_y_mm * PX_PER_MM) + offset_y
            br_x = int(br_x_mm * PX_PER_MM) + offset_x
            br_y = int(br_y_mm * PX_PER_MM) + offset_y

            # Create a distorted, hand-drawn-like fill
            points = np.array([
                [tl_x + random.randint(1, 4), tl_y + random.randint(1, 4)],
                [br_x - random.randint(1, 4), tl_y + random.randint(1, 4)],
                [br_x - random.randint(1, 4), br_y - random.randint(1, 4)],
                [tl_x + random.randint(1, 4), br_y - random.randint(1, 4)]
            ])
            cv2.fillPoly(img_cv, [points], (10, 10, 10))

    # 4. Save the simulated scan
    output_path = os.path.join(scan_output_dir, f"simulated_scan_model_{model_num}.png")
    cv2.imwrite(output_path, img_cv)
    logging.info(f"Saved simulated scan to {output_path}")
