import subprocess
import os
import logging
from typing import Optional, Dict, List
import shutil
import sys
import glob # ADDED: For finding R versions in Program Files/dirs
from datetime import date # ADDED: For default date

# Custom imports from the rexams package
from autotestia.rexams.r_utils import _find_rscript_executable, _is_executable # Use from r_utils

# Path to the R script, assuming it's in the same directory as this wrapper
R_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "generate_exams.R")

LANGUAGE_CONFIGS = {
    "es": {
        "r_code": "es",
        "institution": "Universitat de València",
        "logo": "logo_uv.jpg", 
        "intro": ('\\underline{Instrucciones:}\\n'
                  '\\begin{itemize}\\n'
                  '\\item \\textbf{Está completamente prohibido tener dispositivos electrónicos o apuntes durante la realización del examen}\\n'
                  '\\item \\textbf{No utilizar tipex para corregir}\\n'
                  '\\item \\textbf{\\underline{Penalización}: Cada respuesta errónea puntúa -1/3 puntos}\\n'
                  '\\end{itemize}')
    },
    "ca": {
        "r_code": "ca",
        "institution": "Universitat de València",
        "logo": "logo_uv.jpg",
        "intro": ('\\underline{Instruccions:}\\n'
                  '\\begin{itemize}\\n'
                  '\\item \\textbf{Està completament prohibit tindre dispositius electrònics o apunts durant la realització de l\'examen}\\n'
                  '\\item \\textbf{No utilitzar típex per a corregir}\\n'
                  '\\item \\textbf{\\underline{Penalització}: Cada resposta errònia puntua -1/3 punts}\\n'
                  '\\end{itemize}')
    },
    "en": {
        "r_code": "en",
        "institution": "University of Valencia",
        "logo": "logo_uv.jpg",
        "intro": ('\\underline{Instructions:}\\n'
                  '\\begin{itemize}\\n'
                  '\\item \\textbf{It is strictly forbidden to have electronic devices or notes during the exam}\\n'
                  '\\item \\textbf{Do not use correction fluid (e.g., Tipp-Ex)}\\n'
                  '\\item \\textbf{\\underline{Penalty}: Each incorrect answer scores -1/3 points}\\n'
                  '\\end{itemize}')
    }
}

def _normalize_language_key(lang_str: str) -> str:
    """Normalizes various language inputs to a standard key ('es', 'ca', 'en')."""
    lang_str = lang_str.strip().lower()
    if lang_str in ["es", "spa", "spanish", "español", "castellano"]:
        return "es"
    if lang_str in ["ca", "cat", "catalan", "català", "val", "valencian", "valencià"]:
        return "ca"
    if lang_str in ["en", "eng", "english", "inglés", "anglès"]: # "ingles" without accent
        return "en"
    logging.warning(f"Unknown language string '{lang_str}', defaulting to Spanish (es).")
    return "es"

def generate_rexams_pdfs(
    questions_input_dir: str,
    exams_output_dir: str,
    language_str: str,
    num_models: int = 4,
    r_executable: Optional[str] = None, # Default suggests the command name, triggers full search if not a path
    custom_r_params: Optional[Dict[str, str]] = None
) -> bool:
    """
    Calls the R script to generate PDF exams from .Rmd files.

    Args:
        questions_input_dir: Directory where the .Rmd question files are located.
        exams_output_dir: Directory where the R script should save its output (PDFs, etc.).
        language_str: Language string (e.g., "Spanish", "en", "valencià").
        num_models: Number of different exam models to generate.
        r_executable: Path to the Rscript executable. If "Rscript" (default) or None,
                      an attempt is made to find it. If a specific path is given, it's used.
        custom_r_params: Dictionary to override default R script parameters like 'date', 
                         'seed', 'logo', 'title', 'course', 'institution', 'max_questions', 'intro_text'.

    Returns:
        True if R script execution was successful, False otherwise.
        
    Raises:
        FileNotFoundError: If Rscript executable cannot be found.
    """
    # --- Find Rscript executable ---
    final_r_executable = _find_rscript_executable(r_executable)
    if not final_r_executable:
        error_msg = (
            f"Rscript executable (searched for '{r_executable if r_executable else 'Rscript'}') not found. "
            "Please install R and ensure Rscript is in your PATH, "
            "or provide the full path via the 'r_executable' argument."
        )
        logging.error(error_msg)
        raise FileNotFoundError(error_msg)
    # --- End Rscript executable search ---

    logging.info(f"Using Rscript executable: {final_r_executable}")
    logging.info(f"Starting R/exams PDF generation from: {questions_input_dir}")
    logging.info(f"Exams will be output to: {exams_output_dir}")

    if not os.path.isdir(questions_input_dir):
        logging.error(f"R/exams questions input directory not found: {questions_input_dir}")
        return False

    if not os.path.isfile(R_SCRIPT_PATH):
        logging.error(f"R script not found at: {R_SCRIPT_PATH}")
        print(f"Error: R script not found at {R_SCRIPT_PATH}")
        return False

    lang_key = _normalize_language_key(language_str)
    lang_config = LANGUAGE_CONFIGS.get(lang_key, LANGUAGE_CONFIGS["es"])

    # Prepare R script arguments
    # These are always set based on language or explicit values
    r_args = {
        "questions-dir": os.path.abspath(questions_input_dir),
        "output-dir": os.path.abspath(exams_output_dir),
        "n-models": str(num_models),
        "language": lang_config["r_code"],
        "institution": lang_config.get("institution", ""),
        "intro-text": lang_config.get("intro", ""),
        "date": date.today().isoformat(),
        "seed": "12345",
        "max-questions": "45"
    }

    # Handle logo path: default from lang_config, can be overridden by custom_r_params
    logo_to_use = lang_config.get("logo", "") # Default to empty string if not in lang_config

    # Override with custom_r_params if provided
    # This will add/overwrite any key, including "exam-title", "course", "logo", "seed", etc.
    if custom_r_params:
        for key, value in custom_r_params.items():
            # Ensure keys are R-compatible (hyphenated)
            r_key = key.replace('_', '-')
            r_args[r_key] = str(value)
            if r_key == "logo": # If logo is in custom_r_params, it takes precedence
                logo_to_use = str(value)

    # Resolve logo path (after potential override from custom_r_params)
    # The 'logo' key in r_args might be updated here if logo_to_use is valid
    if logo_to_use and isinstance(logo_to_use, str) and logo_to_use.strip():
        if not os.path.isabs(logo_to_use):
            potential_logo_path = os.path.abspath(os.path.join(os.path.dirname(R_SCRIPT_PATH), logo_to_use))
            if os.path.isfile(potential_logo_path):
                r_args["logo"] = potential_logo_path
            else:
                r_args["logo"] = logo_to_use 
                logging.warning(f"Relative logo '{logo_to_use}' not found at '{potential_logo_path}'. Passing name as is to R script.")
        else: 
            if os.path.isfile(logo_to_use):
                r_args["logo"] = logo_to_use
            else:
                r_args["logo"] = logo_to_use # Pass invalid absolute path as is, R script will warn
                logging.warning(f"Absolute logo path '{logo_to_use}' not found. Passing as is to R script.")
    elif "logo" in r_args: # If logo was set to empty string or None by custom_params
         r_args["logo"] = "" # Ensure it's an empty string for R if it's meant to be unset
    else: # No logo from lang_config or custom_params, ensure it's explicitly empty for R
        r_args["logo"] = ""

    command: List[str] = [final_r_executable, R_SCRIPT_PATH]
    # Add arguments to command only if they have a non-empty value OR are non-string defaults like n-models
    # For title and course, if not in r_args (because not from CLI), they won't be passed,
    # letting R script defaults apply.
    for key, value in r_args.items():
        # Special handling for logo: if it's an empty string, R script handles "no logo"
        if key == "logo" and value == "":
             command.extend([f"--{key}", ""]) # Pass empty string for no logo
        elif value is not None : # Pass other args if they have a value
            command.extend([f"--{key}", str(value)])

    logging.info(f"Executing R command: {' '.join(command)}")

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False, 
            encoding='utf-8' 
        )

        if process.stdout:
            logging.info(f"R script STDOUT:\n{process.stdout}")
        if process.stderr:
            logging.info(f"R script STDERR:\n{process.stderr}") 

        if process.returncode == 0:
            logging.info("R script executed successfully.")
            if not os.listdir(exams_output_dir) and num_models > 0 and not glob.glob(os.path.join(exams_output_dir, "*.pdf")): # Check if output dir is empty of PDFs
                 logging.warning(f"R script finished, but the output directory {exams_output_dir} appears empty or lacks PDF exams. This might be an issue if exams were expected.")
            return True
        else:
            logging.error(f"R script execution failed with return code {process.returncode}.")
            logging.error(f"R script STDERR (Full):\n{process.stderr}") 
            err = process.stderr.splitlines()[-10:]
            print(f"Error: R script execution failed. Check logs. STDERR (last 10 lines):\n{err}")
            return False

    except FileNotFoundError: 
        # This should ideally be caught by _find_rscript_executable now for the executable itself
        logging.error(f"Critical FileNotFoundError during R script execution (e.g. Rscript not found, or R_SCRIPT_PATH invalid). Rscript: {final_r_executable}, Script: {R_SCRIPT_PATH}")
        print(f"Error: FileNotFoundError during R script execution. Rscript: '{final_r_executable}', Script: '{R_SCRIPT_PATH}'")
        raise 
    except Exception as e:
        logging.error(f"An error occurred while running the R script: {e}", exc_info=True)
        print(f"Error: An exception occurred while running R script: {e}")
        return False
