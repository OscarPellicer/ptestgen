import subprocess
import os
import logging
from typing import List, Optional
import random
import shutil
import sys

from .schemas import PexamQuestion

# Define a cache directory for pexams tools
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".pexams_cache")
MARP_INSTALL_DIR = os.path.join(CACHE_DIR, "marp")
MARP_PACKAGE_JSON = os.path.join(MARP_INSTALL_DIR, "package.json")

def _get_marp_command() -> List[str]:
    """
    Finds the best available command for running Marp, installing it locally if needed.
    Priority: Global marp > VS Code Extension > Cached local marp > Install local marp > npx fallback.
    """
    # 1. Prefer globally installed 'marp'
    if shutil.which("marp"):
        logging.info("Using globally installed 'marp'.")
        return ["marp"]

    # 2. Check for marp from VS Code extension
    try:
        home = os.path.expanduser("~")
        vscode_extensions_path = os.path.join(home, ".vscode", "extensions")
        if os.path.isdir(vscode_extensions_path):
            for item in os.listdir(vscode_extensions_path):
                if item.lower().startswith("marp-team.marp-vscode"):
                    marp_executable_name = "marp.cmd" if sys.platform == "win32" else "marp"
                    potential_path = os.path.join(vscode_extensions_path, item, "node_modules", ".bin", marp_executable_name)
                    if os.path.exists(potential_path):
                        logging.info(f"Using 'marp' from VS Code extension: {potential_path}")
                        return [potential_path]
    except Exception as e:
        logging.warning(f"Could not check for VS Code marp extension: {e}")


    # 3. Check for our locally managed 'marp'
    marp_executable_name = "marp.cmd" if sys.platform == "win32" else "marp"
    local_marp_path = os.path.join(MARP_INSTALL_DIR, "node_modules", ".bin", marp_executable_name)
    if os.path.exists(local_marp_path):
        logging.info(f"Using locally cached 'marp' from {MARP_INSTALL_DIR}.")
        return [local_marp_path]

    # 4. If not found, try to install it locally for future use
    logging.info("Locally cached 'marp' not found. Attempting one-time installation...")
    if shutil.which("npm"):
        os.makedirs(MARP_INSTALL_DIR, exist_ok=True)
        # Create a dummy package.json to manage the dependency
        with open(MARP_PACKAGE_JSON, "w") as f:
            f.write('{"name": "pexams-marp-dependency"}')
            
        logging.info(f"Running 'npm install @marp-team/marp-cli' in {MARP_INSTALL_DIR}... This may take a moment.")
        try:
            is_windows = sys.platform == "win32"
            subprocess.run(
                ["npm", "install", "@marp-team/marp-cli"],
                cwd=MARP_INSTALL_DIR,
                check=True,
                capture_output=True,
                text=True,
                shell=is_windows # npm.cmd on Windows
            )
            logging.info("Successfully installed marp-cli to local cache.")
            if os.path.exists(local_marp_path):
                return [local_marp_path]
            else:
                logging.error("Installation seemed successful, but the marp executable was not found where expected.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to install marp-cli locally: {e.stderr}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during marp-cli installation: {e}")

    # 5. Fallback to npx if installation failed or npm wasn't found
    if shutil.which("npx"):
        logging.warning("Falling back to 'npx' for this run. This might be slow. For better performance, ensure 'npm' is installed and working.")
        return ["npx", "@marp-team/marp-cli@latest"]
        
    # 6. If nothing works
    return []


def _generate_answer_sheet_markdown(
    questions: List[PexamQuestion],
    exam_model: int,
    exam_title: str,
    exam_course: Optional[str],
    exam_date: Optional[str],
    lang: str = "en",
    id_length: int = 10
) -> str:
    """Generates the pure HTML for the answer sheet with absolutely positioned elements."""

    lang_strings = {
        "en": {"name": "Student name", "id": "Student ID", "title": "Answer sheet - Model", "course": "Course", "date": "Date"},
        "es": {"name": "Nombre alumno", "id": "Nº identificación", "title": "Hoja de respuestas - Modelo", "course": "Curso", "date": "Fecha"},
        "ca": {"name": "Nom alumne", "id": "Nº identificació", "title": "Full de respostes - Model", "course": "Curs", "date": "Data"},
        "de": {"name": "Name des Schülers", "id": "Schüler-ID", "title": "Antwortblatt - Modell", "course": "Kurs", "date": "Datum"},
        "fr": {"name": "Nom de l'étudiant", "id": "ID de l'étudiant", "title": "Feuille de réponses - Modèle", "course": "Cours", "date": "Date"},
        "it": {"name": "Nome dell'alunno", "id": "ID dell'alunno", "title": "Foglio di risposte - Modello", "course": "Corso", "date": "Data"},
        "nl": {"name": "Naam van de leerling", "id": "Leerling-ID", "title": "Antwoordblad - Model", "course": "Cursus", "date": "Datum"},
        "pt": {"name": "Nome do aluno", "id": "ID do aluno", "title": "Folha de respostas - Modelo", "course": "Curso", "date": "Data"},
        "ru": {"name": "Имя студента", "id": "ID студента", "title": "Бланк ответов - Модель", "course": "Курс", "date": "Дата"},
        "zh": {"name": "学生姓名", "id": "学生ID", "title": "答卷 - 模型", "course": "课程", "date": "日期"},
        "ja": {"name": "学生名", "id": "学生ID", "title": "答卷 - 模型", "course": "课程", "date": "日期"},
    }
    selected_lang = lang_strings.get(lang, lang_strings["en"])

    exam_info_parts = []
    if exam_course:
        exam_info_parts.append(f"<span>{selected_lang['course']}: {exam_course}</span>")
    if exam_date:
        exam_info_parts.append(f"<span>{selected_lang['date']}: {exam_date}</span>")
    exam_info_html = "\n".join(exam_info_parts)

    header = f"""
<!-- _class: answer-sheet-page -->
<div class="fiducial top-left"></div>
<div class="fiducial top-right"></div>
<div class="fiducial bottom-left"></div>
<div class="fiducial bottom-right"></div>

<h1 class="exam-title">{exam_title}</h1>
<h2 class="exam-subtitle">{selected_lang['title']} {exam_model}</h2>

<div class="exam-info">
{exam_info_html}
</div>

<div class="student-info">
    <div class="student-name"><b>{selected_lang['name']}</b></div>
    <div class="student-id-grid">
        <b>{selected_lang['id']}</b>
        {'<div class="id-box"></div>' * id_length}
    </div>
</div>

<div class="answer-sheet-container">
"""

    # --- Absolute Positioning Logic ---
    # Define fixed positions for the answer groups. Fills one column completely before moving to the next.
    # Supports up to 15 groups (75 questions) in 3 columns.
    positions = [
        # Column 1 (Questions 1-25)
        (10, 20), (45, 20), (80, 20), (115, 20), (150, 20),
        # Column 2 (Questions 26-50)
        (10, 85), (45, 85), (80, 85), (115, 85), (150, 85),
        # Column 3 (Questions 51-75)
        (10, 150), (45, 150), (80, 150), (115, 150), (150, 150),
    ]

    groups_html = []
    header_row = '<div class="answer-header"><div class="header-q-num">&nbsp;</div>' + \
                 ''.join([f'<div class="header-option">{chr(ord("A")+i)}</div>' for i in range(5)]) + \
                 '</div>'

    for i in range(0, len(questions), 5):
        group_index = i // 5
        if group_index >= len(positions):
            logging.warning(f"Not enough predefined positions for all question groups. Group {group_index+1} will not be placed.")
            break

        pos_top, pos_left = positions[group_index]
        group_questions = questions[i:i+5]

        # Apply positioning directly to the answer-group div, removing the wrapper
        # Using !important to ensure inline styles override any CSS
        # Use CSS transform translate for robust positioning in Marp/Chromium
        group_html = (
            f'<div class="answer-group" '
            f'style="position: absolute; top: 0; left: 0; transform: translate({pos_left}mm, {pos_top}mm);">'
        )
        group_html += header_row

        for q in group_questions:
            row_html = f'<div class="answer-row"><div class="question-number">{q.id}</div>' # Use correct q.id
            row_html += '<div class="options-container">' + ('<div class="option-box"></div>' * 5) + '</div>'
            row_html += '</div>'
            group_html += row_html

        group_html += '</div>' # Close answer-group
        groups_html.append(group_html)

    all_groups_html = "\n".join(groups_html)

    return f"{header}\n{all_groups_html}\n</div>"


def _estimate_question_height(question: PexamQuestion) -> int:
    """Estimates the 'height' of a question in arbitrary units (e.g., lines)."""
    # Base height for question number and spacing
    height = 2
    # Add height for question text (approx. 1 unit per 80 chars)
    height += (len(question.text) // 80) + 1
    # Add height for options
    height += len(question.options)
    for option in question.options:
        height += (len(option.text) // 80)
    # Add a fixed height for an image
    if question.image_path:
        height += 8  # Arbitrary value, needs tuning
    return height


def _generate_questions_markdown(
    questions: List[PexamQuestion], 
    columns: int = 1
) -> str:
    """Generates the Markdown for the question pages, with automatic page breaks."""
    
    # Heuristic page height limit in 'lines'
    PAGE_HEIGHT_LIMIT = 60 
    page_height_limit_with_cols = PAGE_HEIGHT_LIMIT * columns

    md_parts = []
    current_page_height = 0
    first_page = True
    
    md_parts.append('\n<div class="questions-container">\n')

    for q in questions:
        q_height = _estimate_question_height(q)

        if not first_page and current_page_height + q_height > page_height_limit_with_cols:
            # End previous page and start a new one
            md_parts.append("\n</div>\n") # Close container for this page
            md_parts.append("---")
            md_parts.append('\n<div class="questions-container">\n')
            current_page_height = 0
        
        # Add a blank line before the div for proper rendering
        md_parts.append('\n<div class="question-wrapper">\n')

        question_text = q.text.replace('\n', '  \n')
        md_parts.append(f"**{q.id}.** {question_text}\n")
        
        if q.image_path:
            md_parts.append(f"![Image for question {q.id}]({q.image_path})\n")

        for i, option in enumerate(q.options):
            option_label = chr(ord('A') + i)
            # Use pure markdown for the list of options for better rendering of inner markdown (e.g. backticks)
            option_text_md = option.text.replace('\n', '  \n') # Preserve newlines
            md_parts.append(f"- **{option_label})** {option_text_md}")
            
        md_parts.append('</div>\n')

        current_page_height += q_height
        first_page = False
            
    md_parts.append('</div>\n') # Close final questions-container
    return "\n".join(md_parts)


def generate_exams(
    questions: List[PexamQuestion], 
    output_dir: str, 
    num_models: int = 4, 
    exam_title: str = "Final Exam",
    exam_course: Optional[str] = None,
    exam_date: Optional[str] = None,
    font_size: str = "11pt",
    columns: int = 1,
    id_length: int = 10,
    lang: str = "en"
):
    """
    Generates exam PDFs from a list of questions using Marp.
    """
    logging.info(f"Starting pexams PDF generation for {len(questions)} questions.")
    logging.info(f"Exams will be output to: {output_dir}")

    marp_command = _get_marp_command()
    if not marp_command:
        logging.error("Could not find a way to run Marp. Please install Node.js (which includes npm and npx).")
        return

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
        logging.info(f"Created output directory: {output_dir}")
        
    css_path = os.path.join(os.path.dirname(__file__), "exam_template.css")
    if not os.path.exists(css_path):
        logging.error(f"Marp CSS theme not found at {css_path}. Cannot generate exams.")
        return

    for i in range(1, num_models + 1):
        model_questions = list(questions)
        random.shuffle(model_questions)
        
        # Re-number questions for this exam model
        for q_idx, q in enumerate(model_questions, 1):
            q.id = q_idx

        # The language parameter will need to be passed down from the pipeline
        answer_sheet_md = _generate_answer_sheet_markdown(
            model_questions, 
            i, 
            exam_title=exam_title,
            exam_course=exam_course,
            exam_date=exam_date,
            lang=lang, 
            id_length=id_length
        )
        questions_md = _generate_questions_markdown(
            model_questions, columns=columns
        )

        final_md_content = f"""---
marp: true
theme: exam
_class:
  - {font_size.replace("pt", "")}pt
header: "{exam_title if exam_title else ''} - {exam_date if exam_date else ''}"
footer: "Model {i}"
style: |
    @import '{os.path.basename(css_path)}';
---

<!-- _header: . -->
<!-- _footer: . -->

{answer_sheet_md}

---

<!-- _header: . -->
<!-- _footer: . -->

<!-- Leave a blank page between the answer sheet and the questions -->

---

{questions_md}

"""
        md_filename = f"exam_model_{i}.md"
        md_filepath = os.path.join(output_dir, md_filename)
        
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(final_md_content)
        logging.info(f"Generated Markdown for exam model {i}: {md_filepath}")
        
        # Run Marp CLI to convert to PDF
        pdf_filepath = os.path.join(output_dir, f"exam_model_{i}.pdf")
        
        # We need to copy the theme to the output dir for Marp to find it
        theme_basename = os.path.basename(css_path)
        shutil.copy(css_path, os.path.join(output_dir, theme_basename))
        
        command = marp_command + [
            "--pdf",
            "--allow-local-files",
            "--theme-set", theme_basename,
            "--theme", "exam", # Explicitly apply the theme registered via --theme-set
            md_filename, # Use just the filename, not the full path
            "-o",
            pdf_filepath
        ]
        
        logging.info(f"Running Marp command: {' '.join(command)}")
        try:
            # On Windows, npx is a .cmd script and needs shell=True to be found by subprocess.
            is_windows = sys.platform == "win32"
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                cwd=output_dir, # Run marp from the output dir
                shell=is_windows 
            )
            if process.stdout:
                logging.info(f"Marp STDOUT:\n{process.stdout}")
            if process.stderr:
                logging.info(f"Marp STDERR:\n{process.stderr}")
            logging.info(f"Successfully generated PDF for model {i}: {pdf_filepath}")
        except FileNotFoundError:
            # This error can happen on Windows if shell=True is needed for npx.cmd
            # or if Node.js is not properly installed.
            logging.error("Marp/npx command failed to start. Please ensure Node.js is correctly installed and in your PATH.")
            break # Stop trying to generate more models
        except subprocess.CalledProcessError as e:
            logging.error(f"Marp CLI failed for model {i} with return code {e.returncode}.")
            logging.error(f"Marp STDERR:\n{e.stderr}")
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred while running Marp for model {i}: {e}")
            break
