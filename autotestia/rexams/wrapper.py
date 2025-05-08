import subprocess
import os
import logging
from typing import Optional, Dict, List
import shutil
import sys
import glob # ADDED: For finding R versions in Program Files/dirs
from datetime import date # ADDED: For default date

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

def _is_executable(path: str) -> bool:
    """Checks if a path is an executable file."""
    return os.path.isfile(path) and os.access(path, os.X_OK)

def _find_rscript_executable(r_exec_param: Optional[str]) -> Optional[str]:
    """
    Tries to find a valid Rscript executable.
    Search order:
    1. If r_exec_param is a specific path (not "Rscript" or "Rscript.exe"), validate and use it.
       If invalid, returns None without further search.
    2. If r_exec_param is None or a generic name ("Rscript", "Rscript.exe"):
       a. Check PATH for 'Rscript.exe' (Windows) or 'Rscript'.
       b. Check common installation directories for Windows, macOS, and Linux.
    """
    # 1. Handle specific path provided by user
    if r_exec_param and r_exec_param.lower() not in ["rscript", "rscript.exe"]:
        # This implies user provided a specific path, not just the command name
        abs_path = os.path.abspath(r_exec_param)
        if _is_executable(abs_path):
            logging.info(f"Using user-specified Rscript path: {abs_path}")
            return abs_path
        else:
            logging.warning(f"User-specified Rscript path '{r_exec_param}' (resolved to '{abs_path}') is not a valid executable. No further search will be performed.")
            return None # Fail fast if specific path is invalid

    # 2. General search (if r_exec_param was None or a generic name)
    # 2a. Check PATH using shutil.which() for standard names
    default_exec_names = ["Rscript.exe", "Rscript"] if sys.platform == "win32" else ["Rscript"]
    for name in default_exec_names:
        found_in_path = shutil.which(name)
        if found_in_path and _is_executable(found_in_path):
            logging.info(f"Found Rscript in PATH: {found_in_path}")
            return found_in_path

    # 2b. Check common installation locations
    common_paths = []
    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        r_base_paths = [os.path.join(program_files, "R"), os.path.join(program_files_x86, "R")]
        for r_base in r_base_paths:
            if os.path.isdir(r_base):
                version_dirs = sorted(glob.glob(os.path.join(r_base, "R-*")), reverse=True) # Try newest first
                for r_version_dir in version_dirs:
                    for bin_subdir in ["bin", os.path.join("bin", "x64"), os.path.join("bin", "i386")]:
                        common_paths.append(os.path.join(r_version_dir, bin_subdir, "Rscript.exe"))
    elif sys.platform == "darwin": # macOS
        common_paths.extend([
            "/usr/local/bin/Rscript",
            "/Library/Frameworks/R.framework/Versions/Current/Resources/bin/Rscript",
            "/Library/Frameworks/R.framework/Resources/bin/Rscript",
        ])
        # Check Homebrew paths
        homebrew_brew_path = shutil.which("brew")
        if homebrew_brew_path:
            homebrew_prefix_dir = os.path.dirname(os.path.dirname(homebrew_brew_path)) # e.g., /opt/homebrew or /usr/local
            common_paths.append(os.path.join(homebrew_prefix_dir, "bin", "Rscript"))
            common_paths.append(os.path.join(homebrew_prefix_dir, "opt", "r", "bin", "Rscript")) # For `brew install r`
        else: # Fallback common homebrew paths
            common_paths.append("/opt/homebrew/bin/Rscript") # Apple Silicon default
            common_paths.append("/usr/local/opt/r/bin/Rscript") # Older Intel via /usr/local/opt
    else: # Linux/other Unix
        common_paths.extend([
            "/usr/bin/Rscript",
            "/usr/local/bin/Rscript",
        ])
        # Check /opt/R for versioned installs like /opt/R/4.1.0/bin/Rscript
        if os.path.isdir("/opt/R"):
            # Use glob to find Rscript within versioned subdirectories of /opt/R
            # Example: /opt/R/4.1.2/bin/Rscript
            opt_r_paths = sorted(glob.glob("/opt/R/*/bin/Rscript"), reverse=True)
            common_paths.extend(opt_r_paths)

    for path_to_check in common_paths:
        if _is_executable(path_to_check):
            logging.info(f"Found Rscript in common location: {path_to_check}")
            return path_to_check
            
    logging.warning("Rscript executable could not be located automatically via PATH or common installation directories.")
    return None

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
