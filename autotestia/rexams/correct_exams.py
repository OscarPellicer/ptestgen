import subprocess
import os
import logging
import argparse
import sys
import shutil
import glob
from typing import Optional, List, Tuple
import zipfile
import tempfile

# New imports for PDF processing and image manipulation
try:
    import PyPDF2 # Maintained fork, or use 'import pypdf' for the original
except ImportError:
    try:
        import pypdf as PyPDF2 # Try the original name if the fork isn't there
        logging.info("Using 'pypdf' as PyPDF2 was not found.")
    except ImportError:
        logging.critical("PyPDF2 or pypdf library not found. Please install it: pip install PyPDF2 or pip install pypdf")
        sys.exit(1)

try:
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError, PDFPopplerTimeoutError
except ImportError:
    logging.critical("pdf2image library not found. Please install it: pip install pdf2image (and ensure Poppler is installed).")
    sys.exit(1)
try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    logging.critical("Pillow (PIL) library not found. Please install it: pip install Pillow")
    sys.exit(1)
# import math # math is no longer directly used here, it's in cv_utils

# Custom imports
from autotestia.rexams.analyze_exam_results import analyze_results
from autotestia.rexams.check_consistency import check_student_data_consistency
from autotestia.rexams.cv_utils import split_and_rotate_scans
from autotestia.rexams.r_utils import _find_rscript_executable

# Import the new post-processor function and its Playwright availability status
try:
    from autotestia.rexams.report_postprocessor import process_exam_results_zip, PLAYWRIGHT_AVAILABLE as POSTPROCESSOR_PLAYWRIGHT_AVAILABLE
    logging.info(f"POSTPROCESSOR_PLAYWRIGHT_AVAILABLE after import attempt: {POSTPROCESSOR_PLAYWRIGHT_AVAILABLE}")
except ImportError: # Should not happen if file exists, but good for robustness
    logging.error("Failed to import report_postprocessor module. PNG generation for student reports will be unavailable.")
    def process_exam_results_zip(exams_output_dir: str): # Dummy function
        logging.warning("report_postprocessor not available, process_exam_results_zip called but will do nothing.")
    POSTPROCESSOR_PLAYWRIGHT_AVAILABLE = False

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # REMOVE THIS LINE

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
    student_info_csv: str,
    solutions_rds: str,
    output_path: str,
    language: str = "en",
    scan_thresholds: Tuple[float, float] = (0.04, 0.42),
    partial_eval: bool = True,
    negative_points: float = -1/3,
    max_score: Optional[float] = None,
    scale_mark_to: float = 10.0,
    split_pages_python_control: bool = False,
    force_split_python_control: bool = False,
    r_executable: Optional[str] = None,
    student_csv_cols: Optional[dict] = None,
    student_csv_encoding: str = "UTF-8",
    registration_format: str = "%08s",
    force_nops_scan: bool = False,
    rotate_scans_r_control: bool = False,
    python_rotate_control: bool = True,
) -> bool:
    """
    Calls the R script to perform exam auto-correction.
    Manages PDF splitting and rotation in Python if `split_pages_python_control` is True.
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

    def add_arg(opt_name: str, value, is_flag=False):
        if is_flag:
            if value:
                command.append(opt_name)
        elif value is not None:
            command.extend([opt_name, str(value)])

    # --- PDF Pre-processing by Python ---
    # The directory `output_path/scanned_pages` is what the R script expects
    # for nops_scan input if R's own splitting is not used.
    r_nops_scan_input_dir = os.path.join(os.path.abspath(output_path), "scanned_pages")

    if split_pages_python_control: # Python's --split-pages is TRUE
        logging.info("Python is handling PDF splitting and rotation.")
        if not all_scans_pdf:
            logging.error("`--all-scans-pdf` is required when Python's `--split-pages` is enabled.")
            return False
        
        processed_dir = split_and_rotate_scans(
            all_scans_pdf_path=os.path.abspath(all_scans_pdf),
            output_dir_for_processed_scans=r_nops_scan_input_dir, # Python populates R's expected dir
            force_processing=force_split_python_control,
            python_script_output_path=os.path.abspath(output_path), # For debug images subdir
            do_python_rotation=python_rotate_control,
        )
        if not processed_dir:
            logging.error("Python PDF splitting and rotation failed. Aborting.")
            return False
        
        # Tell R script NOT to split and NOT to rotate.
        # `--split-pages` for R is not added.
        # `--all-scans-pdf` for R is not added.
        add_arg("--rotate-scans", False, is_flag=True) # Python handled rotation
    else:
        logging.info("Python is NOT handling PDF splitting/rotation. R script will manage based on its flags.")
        # R script will handle splitting if its --split-pages is set.
        # Pass relevant args for R's own processing.
        if all_scans_pdf: # If a combined PDF is provided for R to potentially split
            add_arg("--all-scans-pdf", os.path.abspath(all_scans_pdf))
            # We need to tell R to split this. The R script's --split-pages flag does this.
            # This implies the Python script should have a way to pass this intent.
            # Let's assume if split_pages_python_control is FALSE, AND all_scans_pdf is given,
            # R should try to split it. This requires the R script's --split-pages flag to be set.
            # The current R script's --split-pages flag is a boolean action.
            # Let's make the `force_split_python_control` also control R's `--force-split` in this case.
            add_arg("--split-pages", True, is_flag=True) # Tell R to use its splitting mechanism
            if force_split_python_control: # If forcing, applies to R's split too
                add_arg("--force-split", True, is_flag=True)
        
        # Pass the original rotate_scans_r_control to R
        add_arg("--rotate-scans", rotate_scans_r_control, is_flag=True)


    # --- Common R Script Arguments ---
    add_arg("--student-info-csv", os.path.abspath(student_info_csv))
    add_arg("--solutions-rds", os.path.abspath(solutions_rds))
    # `output_path` is crucial. R script constructs `derived_scans_dir` from it.
    # If Python processed scans, it placed them into `output_path/scanned_pages`.
    # If R processes, it will also create/use `output_path/scanned_pages`. This matches.
    add_arg("--output-path", os.path.abspath(output_path))

    add_arg("--language", language)
    add_arg("--scan-thresholds", f"{scan_thresholds[0]},{scan_thresholds[1]}")

    if partial_eval:
        add_arg("--partial", True, is_flag=True)
    else:
        add_arg("--no-partial", True, is_flag=True)

    add_arg("--negative-points", negative_points)
    add_arg("--max-score", max_score)
    add_arg("--scale-mark-to", scale_mark_to)
    add_arg("--force-nops-scan", force_nops_scan, is_flag=True)

    if student_csv_cols:
        add_arg("--student-csv-id-col", student_csv_cols.get("id"))
        add_arg("--student-csv-reg-col", student_csv_cols.get("reg"))
        add_arg("--student-csv-name-col", student_csv_cols.get("name"))
        add_arg("--student-csv-surname-col", student_csv_cols.get("surname"))

    add_arg("--student-csv-encoding", student_csv_encoding)
    add_arg("--registration-format", registration_format)

    shell_command_parts = []
    for part in command:
        if " " in part and not (part.startswith('"') and part.endswith('"')):
            shell_command_parts.append(f'"{part}"')
        else:
            shell_command_parts.append(part)

    shell_command_str = " ".join(shell_command_parts)
    logging.info("To run this R script manually in a shell, use a command like:")
    logging.info(shell_command_str)

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
            logging.info("R correction script executed successfully.")
            expected_csv = os.path.join(os.path.abspath(output_path), "exam_corrected_results.csv")
            if not os.path.exists(expected_csv):
                logging.warning(f"R script finished, but main results CSV '{expected_csv}' not found. Please check R script logs and output directory.")
            return True
        else:
            logging.error(f"R correction script execution failed with return code {process.returncode}.")
            if process.stderr.strip(): logging.error(f"R script STDERR (Full):\n{process.stderr}")
            elif process.stdout.strip(): logging.error(f"R script STDOUT (Full, as STDERR was empty):\n{process.stdout}")
            return False

    except FileNotFoundError:
        logging.error(f"Critical FileNotFoundError: Rscript '{final_r_executable}' or R script '{R_CORRECTION_SCRIPT_PATH}' not found.", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while running the R correction script: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Python wrapper for R/exams auto-correction, with integrated consistency checks and results analysis.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Input Files ---
    parser.add_argument("--all-scans-pdf", type=str, help="Path to the single PDF containing all scanned exams.")
    parser.add_argument("--student-info-csv", type=str, required=True, help="Path to the input CSV with student information.")
    parser.add_argument("--solutions-rds", type=str, required=True, help="Path to the exam.rds file from R/exams.")
    parser.add_argument("--output-path", type=str, required=True, help="Main directory for all outputs.")
    
    # --- R Script and Language ---
    parser.add_argument("--r-executable", type=str, default=None, help="Path to Rscript. Tries to find automatically if None.")
    parser.add_argument("--language", type=str, default="en", choices=["en", "es", "ca", "de", "fr"], help="Language for nops_eval.")
    
    # --- Scan and Evaluation Parameters ---
    parser.add_argument("--scan-thresholds", type=str, default="0.04,0.42", help="Scan thresholds for nops_scan (lower,upper).")
    parser.add_argument("--partial-eval", action=argparse.BooleanOptionalAction, default=True, help="Enable partial scoring.")
    parser.add_argument("--negative-points", type=float, default=-1/3, help="Penalty for incorrect answers.")
    parser.add_argument("--max-score", type=float, default=None, help="Maximum raw score (for analysis and R script scaling).")
    parser.add_argument("--scale-mark-to", type=float, default=10.0, help="Target score for R script's mark scaling.")

    # --- PDF Processing Controls (Python vs R) ---
    parser.add_argument("--split-pages", action=argparse.BooleanOptionalAction, default=False,
                        dest="split_pages_python_control",
                        help="Enable PDF splitting & rotation by this Python script.")
    parser.add_argument("--force-split", action=argparse.BooleanOptionalAction, default=False,
                        dest="force_split_python_control",
                        help="Force overwrite for PDF splitting (Python or R based on --split-pages).")
    parser.add_argument("--python-rotate", action=argparse.BooleanOptionalAction, default=True, # Default True now for --split-pages
                        dest="python_rotate_control",
                        help="Enable actual rotation by Python if --split-pages (Python) is active.")
    parser.add_argument("--rotate-scans", action=argparse.BooleanOptionalAction, default=False,
                        dest="rotate_scans_r_control",
                        help="Enable image rotation by R's nops_scan (if Python's --split-pages is off).")

    # --- Execution Flow Control ---
    parser.add_argument("--force-r-eval", action="store_true", default=False,
                        help="Force R script evaluation even if results CSV exists.")
    parser.add_argument("--force-nops-scan", action=argparse.BooleanOptionalAction, default=False,
                        help="Force R's nops_scan to re-run.")
    
    # --- Consistency Check Control ---
    parser.add_argument("--run-consistency-check-on-fail", action=argparse.BooleanOptionalAction, default=True,
                        help="Run consistency check if R script fails.")
    parser.add_argument("--always-run-consistency-check", action="store_true", default=False,
                        help="Always run consistency check after R script attempt.")

    # --- Analysis Control ---
    parser.add_argument("--run-analysis", action=argparse.BooleanOptionalAction, default=True,
                        help="Run results analysis if results CSV exists/is created.")
    
    # --- Student CSV Configuration ---
    parser.add_argument("--student-csv-id-col", type=str, default="ID.Usuario")
    parser.add_argument("--student-csv-reg-col", type=str, default="Número.de.Identificación")
    parser.add_argument("--student-csv-name-col", type=str, default="Nombre")
    parser.add_argument("--student-csv-surname-col", type=str, default="Apellidos")
    parser.add_argument("--student-csv-encoding", type=str, default="UTF-8")
    parser.add_argument("--registration-format", type=str, default="%08s")

    # --- PNG Generation Control ---
    parser.add_argument("--force-png-generation", action="store_true", default=False,
                        help="Force regeneration of PNGs from student HTML reports even if they already exist.")
    
    # --- Log Level Control ---
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set the log level. Default is INFO.")

    # --- Question Voiding Arguments (passed to analyze_results) ---
    parser.add_argument("--void-questions", type=str, default=None,
                        help="Comma-separated list of question numbers to remove from score calculation during analysis (e.g., '3,4').")
    parser.add_argument("--void-questions-nicely", type=str, default=None,
                        help="Comma-separated list of question numbers to void if incorrect/NA during analysis, count if correct (e.g., '5,6').")

    args = parser.parse_args()
    # Configure logging as early as possible using the parsed log level
    # Ensure the format string is included here if it was removed from a module-level call
    log_level_to_set = args.log_level.upper()
    logging.basicConfig(level=log_level_to_set, format='%(asctime)s - %(levelname)s - %(message)s')

    # Forcefully set level for the root logger and all existing loggers
    # This can help if other modules initialized their loggers before basicConfig was fully effective for them.
    logging.getLogger().setLevel(log_level_to_set)
    for logger_name in logging.Logger.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(log_level_to_set)

    # ... (logging guidelines from your script) ...
    logging.info("To ensure optimal processing by R/exams:")
    logging.info("  Scanning: 300 DPI, Black and White (1-bit), PDF format.")
    logging.info("  If using --split-pages (Python), ensure each exam sheet is a distinct page in order.")

    try:
        st_lower, st_upper = map(float, args.scan_thresholds.split(','))
        scan_thresholds_tuple = (st_lower, st_upper)
    except ValueError:
        parser.error("Invalid --scan-thresholds format.")
        return

    student_csv_cols_dict = {
        "id": args.student_csv_id_col, "reg": args.student_csv_reg_col,
        "name": args.student_csv_name_col, "surname": args.student_csv_surname_col
    }
    
    # ---- Main Logic ----
    output_path_abs = os.path.abspath(args.output_path)
    results_csv_path = os.path.join(output_path_abs, "exam_corrected_results.csv")
    processed_register_path = os.path.join(output_path_abs, "processed_student_register.csv")
    scanned_pages_dir = os.path.join(output_path_abs, "scanned_pages")


    r_script_was_run = False
    r_script_successfully_completed = False

    if args.force_r_eval or not os.path.exists(results_csv_path):
        logging.info(f"Preparing to run R correction script. Force run: {args.force_r_eval}. Results exist: {os.path.exists(results_csv_path)}")
        r_script_was_run = True
        try:
            r_script_successfully_completed = run_correction_script(
                all_scans_pdf=args.all_scans_pdf, student_info_csv=args.student_info_csv,
                solutions_rds=args.solutions_rds, output_path=args.output_path,
                language=args.language, scan_thresholds=scan_thresholds_tuple,
                partial_eval=args.partial_eval, negative_points=args.negative_points,
                max_score=args.max_score, scale_mark_to=args.scale_mark_to,
                split_pages_python_control=args.split_pages_python_control,
                force_split_python_control=args.force_split_python_control,
                r_executable=args.r_executable, student_csv_cols=student_csv_cols_dict,
                student_csv_encoding=args.student_csv_encoding,
                registration_format=args.registration_format,
                force_nops_scan=args.force_nops_scan,
                rotate_scans_r_control=args.rotate_scans_r_control,
                python_rotate_control=args.python_rotate_control,
            )
        except Exception as e_r_script: # Catch any exception from run_correction_script itself
            logging.error(f"Exception during R script execution: {e_r_script}", exc_info=True)
            r_script_successfully_completed = False
    else:
        logging.info(f"R script evaluation skipped as results file '{results_csv_path}' already exists. Use --force-r-eval to re-run.")
        # If results exist and R script is skipped, we treat it as a "success" for analysis purposes.
        r_script_successfully_completed = True 


    # --- Consistency Check ---
    trigger_consistency_check = args.always_run_consistency_check or \
                                (r_script_was_run and not r_script_successfully_completed and args.run_consistency_check_on_fail)
    
    if trigger_consistency_check:
        logging.info("Attempting to run consistency check...")
        daten_txt_temp_path = None
        temp_dir_for_daten = None
        try:
            # Find nops_scan_*.zip
            nops_scan_zip_path = None
            if os.path.isdir(scanned_pages_dir):
                zip_files = glob.glob(os.path.join(scanned_pages_dir, "nops_scan_*.zip"))
                if zip_files:
                    nops_scan_zip_path = max(zip_files, key=os.path.getmtime) # Get the latest
                    logging.info(f"Consistency Check: Found nops_scan ZIP: {nops_scan_zip_path}")
            
            if nops_scan_zip_path and os.path.exists(nops_scan_zip_path):
                temp_dir_for_daten = tempfile.mkdtemp(prefix="daten_extract_")
                with zipfile.ZipFile(nops_scan_zip_path, 'r') as zip_ref:
                    if 'Daten.txt' in zip_ref.namelist():
                        zip_ref.extract('Daten.txt', temp_dir_for_daten)
                        daten_txt_temp_path = os.path.join(temp_dir_for_daten, 'Daten.txt')
                        logging.info(f"Consistency Check: Extracted Daten.txt to {daten_txt_temp_path}")
                    else:
                        logging.warning("Consistency Check: Daten.txt not found inside the nops_scan ZIP.")
            else:
                logging.warning(f"Consistency Check: nops_scan ZIP not found in {scanned_pages_dir}. Cannot extract Daten.txt.")

            # Check if essential files for consistency check exist
            pln_exists = os.path.exists(args.student_info_csv)
            daten_exists = daten_txt_temp_path and os.path.exists(daten_txt_temp_path)
            
            if pln_exists and daten_exists:
                # processed_register_path might not exist if R failed early, so it's optional for the call
                check_student_data_consistency(
                    pln_path=args.student_info_csv,
                    daten_txt_path=daten_txt_temp_path,
                    processed_register_path=processed_register_path if os.path.exists(processed_register_path) else None,
                    output_path_for_debug=output_path_abs
                )
            else:
                logging.warning("Consistency Check: Skipping due to missing essential files "
                               f"(Student Info CSV exists: {pln_exists}, Daten.txt extracted: {daten_exists}).")
        except Exception as e_consistency:
            logging.error(f"Error during consistency check preparation or execution: {e_consistency}", exc_info=True)
        finally:
            if temp_dir_for_daten and os.path.exists(temp_dir_for_daten):
                shutil.rmtree(temp_dir_for_daten)
                logging.debug(f"Cleaned up temporary directory for Daten.txt: {temp_dir_for_daten}")
    
    # --- Results Analysis ---
    # Run analysis if flag is set AND (R script completed OR R script was skipped because results exist)
    should_run_analysis = args.run_analysis and \
                          (r_script_successfully_completed or (not r_script_was_run and os.path.exists(results_csv_path)))

    if should_run_analysis:
        if os.path.exists(results_csv_path):
            if args.max_score is not None:
                logging.info("Running exam results analysis...")
                analysis_output_dir = os.path.join(output_path_abs, "analysis_plots")
                analyze_results(
                    csv_filepath=results_csv_path,
                    max_score=args.max_score,
                    output_dir=analysis_output_dir,
                    void_questions_str=args.void_questions,
                    void_questions_nicely_str=args.void_questions_nicely
                )
            else:
                logging.warning("Skipping results analysis: --max-score not provided.")
        else:
            logging.warning(f"Skipping results analysis: Results CSV file '{results_csv_path}' not found.")
    elif args.run_analysis: # Flag was true, but conditions not met
        logging.info(f"Results analysis was requested but conditions not met (R success: {r_script_successfully_completed}, Results CSV exists: {os.path.exists(results_csv_path)})")

    # --- PNG Generation from HTML reports in exam_corrected_results.zip ---
    # This step runs if the R script was successful (or skipped due to existing results)
    # and the necessary zip file ('exam_corrected_results.zip') is expected to be in output_path_abs.
    if r_script_successfully_completed or (not r_script_was_run and os.path.exists(os.path.join(output_path_abs, "exam_corrected_results.zip"))):
        if POSTPROCESSOR_PLAYWRIGHT_AVAILABLE:
            logging.info("Attempting to generate PNGs from student HTML reports (if exam_corrected_results.zip was produced).")
            try:
                process_exam_results_zip(output_path_abs, force_regeneration=args.force_png_generation) # Pass the force flag
            except Exception as e_postproc:
                logging.error(f"An error occurred during student report PNG generation: {e_postproc}", exc_info=True)
        else:
            logging.warning("Skipping PNG generation for student reports as Playwright is not available or report_postprocessor module had issues. "
                            "To enable, install Playwright: pip install playwright && playwright install")
    elif POSTPROCESSOR_PLAYWRIGHT_AVAILABLE: # Playwright is there, but conditions to run PNG step not met
        logging.info(f"PNG generation for student reports skipped. R script success: {r_script_successfully_completed}, Zip exists (checked if R not run): {os.path.exists(os.path.join(output_path_abs, 'exam_corrected_results.zip')) if not r_script_was_run else 'N/A'}")


    # --- Final Status ---
    if r_script_was_run:
        if r_script_successfully_completed and os.path.exists(results_csv_path):
            logging.info("Exam correction process completed successfully (R script run and results found).")
            sys.exit(0)
        elif r_script_successfully_completed and not os.path.exists(results_csv_path):
            logging.error("Exam correction process indicates R script success, but results CSV is missing. Please check R logs.")
            sys.exit(1)
        else: # R script failed
            logging.error("Exam correction process failed (R script execution error). Check logs for details.")
            sys.exit(1)
    elif os.path.exists(results_csv_path) and args.run_analysis : # R script not run, results existed, analysis was run
         logging.info("Exam correction process: R script skipped (results existed), analysis performed.")
         sys.exit(0)
    elif os.path.exists(results_csv_path) and not args.run_analysis : # R script not run, results didn't exist (shouldn't happen with current logic unless --force-r-eval was false and file vanished)
         logging.info("Exam correction process: R script skipped (results existed), analysis was disabled by user.")
         sys.exit(0)
    else: # R script not run, and results didn't exist (shouldn't happen with current logic unless --force-r-eval was false and file vanished)
        logging.error("Exam correction process: R script was not run and no pre-existing results found. This state should generally not be reached.")
        sys.exit(1)


if __name__ == "__main__":
    main()