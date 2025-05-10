import subprocess
import os
import logging
import argparse
import sys
import shutil
import glob
from typing import Optional, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Path to the R script for correction, assuming it's in the same directory as this wrapper
R_CORRECTION_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "run_autocorrection.R")

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
    if r_exec_param and r_exec_param.lower() not in ["rscript", "rscript.exe"]:
        abs_path = os.path.abspath(r_exec_param)
        if _is_executable(abs_path):
            logging.info(f"Using user-specified Rscript path: {abs_path}")
            return abs_path
        else:
            logging.warning(f"User-specified Rscript path '{r_exec_param}' (resolved to '{abs_path}') is not a valid executable. No further search will be performed.")
            return None

    default_exec_names = ["Rscript.exe", "Rscript"] if sys.platform == "win32" else ["Rscript"]
    for name in default_exec_names:
        found_in_path = shutil.which(name)
        if found_in_path and _is_executable(found_in_path):
            logging.info(f"Found Rscript in PATH: {found_in_path}")
            return found_in_path

    common_paths = []
    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        r_base_paths = [os.path.join(program_files, "R"), os.path.join(program_files_x86, "R")]
        for r_base in r_base_paths:
            if os.path.isdir(r_base):
                version_dirs = sorted(glob.glob(os.path.join(r_base, "R-*")), reverse=True)
                for r_version_dir in version_dirs:
                    for bin_subdir in ["bin", os.path.join("bin", "x64"), os.path.join("bin", "i386")]:
                        common_paths.append(os.path.join(r_version_dir, bin_subdir, "Rscript.exe"))
    elif sys.platform == "darwin":
        common_paths.extend([
            "/usr/local/bin/Rscript",
            "/Library/Frameworks/R.framework/Versions/Current/Resources/bin/Rscript",
            "/Library/Frameworks/R.framework/Resources/bin/Rscript",
        ])
        homebrew_brew_path = shutil.which("brew")
        if homebrew_brew_path:
            homebrew_prefix_dir = os.path.dirname(os.path.dirname(homebrew_brew_path))
            common_paths.append(os.path.join(homebrew_prefix_dir, "bin", "Rscript"))
            common_paths.append(os.path.join(homebrew_prefix_dir, "opt", "r", "bin", "Rscript"))
        else:
            common_paths.append("/opt/homebrew/bin/Rscript")
            common_paths.append("/usr/local/opt/r/bin/Rscript")
    else: # Linux/other Unix
        common_paths.extend(["/usr/bin/Rscript", "/usr/local/bin/Rscript"])
        if os.path.isdir("/opt/R"):
            opt_r_paths = sorted(glob.glob("/opt/R/*/bin/Rscript"), reverse=True)
            common_paths.extend(opt_r_paths)

    for path_to_check in common_paths:
        if _is_executable(path_to_check):
            logging.info(f"Found Rscript in common location: {path_to_check}")
            return path_to_check
            
    logging.warning("Rscript executable could not be located automatically.")
    return None

def run_correction_script(
    all_scans_pdf: Optional[str],
    scans_dir: str,
    student_info_csv: str,
    solutions_rds: str,
    output_basename: str,
    language: str = "en",
    scan_thresholds: Tuple[float, float] = (0.04, 0.42),
    partial_eval: bool = True,
    negative_points: float = -1/3,
    max_score: Optional[float] = None,
    scale_mark_to: float = 10.0,
    split_pages: bool = False,
    force_split: bool = False,
    r_executable: Optional[str] = None,
    processed_register_filename: str = "processed_student_register.csv",
    student_csv_cols: Optional[dict] = None, # For id, reg, name, surname cols
    student_csv_encoding: str = "UTF-8",
    registration_format: str = "%08s"

) -> bool:
    """
    Calls the R script to perform exam auto-correction.
    """
    final_r_executable = _find_rscript_executable(r_executable)
    if not final_r_executable:
        error_msg = (
            f"Rscript executable (searched for '{r_executable if r_executable else 'Rscript'}') not found. "
            "Please install R and ensure Rscript is in your PATH, "
            "or provide the full path via the 'r_executable' argument."
        )
        logging.error(error_msg)
        raise FileNotFoundError(error_msg)

    if not os.path.isfile(R_CORRECTION_SCRIPT_PATH):
        logging.error(f"R correction script not found at: {R_CORRECTION_SCRIPT_PATH}")
        return False

    command: List[str] = [final_r_executable, R_CORRECTION_SCRIPT_PATH]

    # Helper to add optional arguments
    def add_arg(opt_name: str, value, is_flag=False):
        if is_flag:
            if value: # Add flag if True
                command.append(opt_name)
        elif value is not None:
            command.extend([opt_name, str(value)])
    
    # Add arguments, ensuring paths are absolute for robustness
    if split_pages:
        if not all_scans_pdf:
            logging.error("--all-scans-pdf is required when --split-pages is enabled.")
            return False
        add_arg("--all-scans-pdf", os.path.abspath(all_scans_pdf))
        add_arg("--split-pages", True, is_flag=True)
        if force_split:
            add_arg("--force-split", True, is_flag=True)
    
    add_arg("--scans-dir", os.path.abspath(scans_dir))
    add_arg("--student-info-csv", os.path.abspath(student_info_csv))
    add_arg("--solutions-rds", os.path.abspath(solutions_rds))
    add_arg("--output-basename", os.path.abspath(output_basename)) # R script handles dirname creation
    
    add_arg("--language", language)
    add_arg("--scan-thresholds", f"{scan_thresholds[0]},{scan_thresholds[1]}")
    
    if partial_eval:
        add_arg("--partial", True, is_flag=True)
    else:
        add_arg("--no-partial", True, is_flag=True) # R script uses --no-partial to set partial=FALSE
        
    add_arg("--negative-points", negative_points)
    add_arg("--max-score", max_score)
    add_arg("--scale-mark-to", scale_mark_to)
    add_arg("--processed-register-filename", processed_register_filename)

    if student_csv_cols:
        add_arg("--student-csv-id-col", student_csv_cols.get("id"))
        add_arg("--student-csv-reg-col", student_csv_cols.get("reg"))
        add_arg("--student-csv-name-col", student_csv_cols.get("name"))
        add_arg("--student-csv-surname-col", student_csv_cols.get("surname"))
    
    add_arg("--student-csv-encoding", student_csv_encoding)
    add_arg("--registration-format", registration_format)


    logging.info(f"Executing R correction command: {' '.join(command)}")

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8' # Ensure consistent encoding
        )

        if process.stdout:
            logging.info(f"R script STDOUT:\n{process.stdout}")
        if process.stderr: # R often prints info messages to stderr
            logging.info(f"R script STDERR:\n{process.stderr}")

        if process.returncode == 0:
            logging.info("R correction script executed successfully.")
            # Check if expected output files were created (e.g., output_basename.csv)
            expected_csv = os.path.abspath(output_basename) + ".csv"
            if not os.path.exists(expected_csv):
                logging.warning(f"R script finished, but main results CSV '{expected_csv}' not found. Please check R script logs and output directory.")
            return True
        else:
            logging.error(f"R correction script execution failed with return code {process.returncode}.")
            # R might have already printed errors, but log its stderr again if not empty
            if process.stderr:
                 logging.error(f"R script STDERR (Full):\n{process.stderr}")
            else: # If R stderr is empty, but failed, stdout might contain error
                 logging.error(f"R script STDOUT (Full, as STDERR was empty):\n{process.stdout}")
            return False

    except FileNotFoundError:
        logging.error(f"Critical FileNotFoundError: Rscript '{final_r_executable}' or R script '{R_CORRECTION_SCRIPT_PATH}' not found.", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while running the R correction script: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Python wrapper for R/exams auto-correction script.",
        formatter_class=argparse.RawTextHelpFormatter # For preserving newlines in help
    )

    # --- Input Files/Dirs ---
    parser.add_argument("--all-scans-pdf", type=str,
                        help="Path to the single PDF containing all scanned exams (required if --split-pages is used).")
    parser.add_argument("--scans-dir", type=str, required=True,
                        help="Directory for individual scanned exam pages (input for nops_scan, output for splitting).")
    parser.add_argument("--student-info-csv", type=str, required=True,
                        help="Path to the input CSV with student information.\n"
                             "Expected columns can be configured (see --student-csv-* args).\n"
                             "Default expected columns (case-sensitive):\n"
                             "  - 'Número.de.Identificación': Student ID as written on the exam sheet.\n"
                             "  - 'Nombre': Student's first name.\n"
                             "  - 'Apellidos': Student's surname(s).\n"
                             "  - 'ID.Usuario': Unique student identifier (e.g., Moodle username).\n"
                             "The 'registration' number in the R script will be formatted (e.g., zero-padded) "
                             "using --registration-format (default: '%08s'). Ensure this matches exam sheet format.")
    parser.add_argument("--solutions-rds", type=str, required=True,
                        help="Path to the exam.rds file generated by R/exams (e.g., by exams2nops or generate_exams.R).")

    # --- Output Configuration ---
    parser.add_argument("--output-basename", type=str, required=True,
                        help="Basename for results files (e.g., 'results_dir/exam01_corrected').\n"
                             "The script will create files like 'results_dir/exam01_corrected.csv' and '.rds'.\n"
                             "The directory part must exist or be creatable by the R script.")
    parser.add_argument("--processed-register-filename", type=str, default="processed_student_register.csv",
                        help="Filename for the intermediate processed student registration CSV. "
                             "It will be saved in the same directory as --output-basename. (default: %(default)s)")

    # --- R Script and Language ---
    parser.add_argument("--r-executable", type=str, default=None,
                        help="Path to the Rscript executable. If not provided, attempts to find it automatically.")
    parser.add_argument("--language", type=str, default="en", choices=["en", "es", "ca", "de", "fr"], # Common languages for nops_eval
                        help="Language for nops_eval messages and potential outputs. (default: %(default)s)")

    # --- Scan and Evaluation Parameters ---
    parser.add_argument("--scan-thresholds", type=str, default="0.04,0.42",
                        help="Comma-separated scan thresholds (lower,upper) for nops_scan. (default: %(default)s)")
    parser.add_argument("--partial-eval", action=argparse.BooleanOptionalAction, default=True, # Py 3.9+
                        help="Enable partial scoring for schoice/mchoice questions. (default: enabled)")
    parser.add_argument("--negative-points", type=float, default=-1/3,
                        help="Penalty for incorrect answers (e.g., -0.3333). (default: %(default)f)")
    parser.add_argument("--max-score", type=float, default=None,
                        help="Maximum raw score of the exam (e.g., 44). Required for scaling marks.")
    parser.add_argument("--scale-mark-to", type=float, default=10.0,
                        help="Target score for scaling the final mark (e.g., 10). (default: %(default)f)")

    # --- PDF Splitting ---
    parser.add_argument("--split-pages", action=argparse.BooleanOptionalAction, default=False,
                        help="Enable PDF splitting of --all-scans-pdf into --scans-dir. (default: disabled)")
    parser.add_argument("--force-split", action=argparse.BooleanOptionalAction, default=False,
                        help="Force overwrite of existing split PDF files if --split-pages is enabled. (default: disabled)")
    
    # --- Student CSV Configuration ---
    parser.add_argument("--student-csv-id-col", type=str, default="ID.Usuario", help="Column name for student unique ID in student CSV. (default: %(default)s)")
    parser.add_argument("--student-csv-reg-col", type=str, default="Número.de.Identificación", help="Column name for student registration (ID on sheet) in student CSV. (default: %(default)s)")
    parser.add_argument("--student-csv-name-col", type=str, default="Nombre", help="Column name for student first name in student CSV. (default: %(default)s)")
    parser.add_argument("--student-csv-surname-col", type=str, default="Apellidos", help="Column name for student surname(s) in student CSV. (default: %(default)s)")
    parser.add_argument("--student-csv-encoding", type=str, default="UTF-8", help="Encoding for the student CSV file. (default: %(default)s)")
    parser.add_argument("--registration-format", type=str, default="%08s",
                        help="Format string (sprintf style) for student registration numbers, e.g., '%%08s' for 8-character string padding. (default: %(default)s)")


    args = parser.parse_args()

    # Parse scan_thresholds
    try:
        st_lower, st_upper = map(float, args.scan_thresholds.split(','))
        scan_thresholds_tuple = (st_lower, st_upper)
    except ValueError:
        parser.error("Invalid --scan-thresholds format. Expected 'lower,upper' (e.g., '0.04,0.42').")
        return # Should exit due to parser.error

    student_csv_cols_dict = {
        "id": args.student_csv_id_col,
        "reg": args.student_csv_reg_col,
        "name": args.student_csv_name_col,
        "surname": args.student_csv_surname_col
    }

    success = run_correction_script(
        all_scans_pdf=args.all_scans_pdf,
        scans_dir=args.scans_dir,
        student_info_csv=args.student_info_csv,
        solutions_rds=args.solutions_rds,
        output_basename=args.output_basename,
        language=args.language,
        scan_thresholds=scan_thresholds_tuple,
        partial_eval=args.partial_eval,
        negative_points=args.negative_points,
        max_score=args.max_score,
        scale_mark_to=args.scale_mark_to,
        split_pages=args.split_pages,
        force_split=args.force_split,
        r_executable=args.r_executable,
        processed_register_filename=args.processed_register_filename,
        student_csv_cols=student_csv_cols_dict,
        student_csv_encoding=args.student_csv_encoding,
        registration_format=args.registration_format
    )

    if success:
        logging.info("Exam correction process completed successfully.")
        sys.exit(0)
    else:
        logging.error("Exam correction process failed. Check logs for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()
