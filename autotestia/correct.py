import logging
import os
import glob
import re
from pathlib import Path

from pexams.correct_exams import correct_exams
from pexams.analysis import analyze_results
from pexams.schemas import PexamExam

# Import for rexams, will be used later
from autotestia.rexams.correct_exams import run_correction_script, analyze_results, check_student_data_consistency

def _handle_pexams(args):
    """Handles the logic for pexams correction."""
    logging.info("Starting pexams correction...")

    if not os.path.exists(args.input_path):
        logging.error(f"Input path not found: {args.input_path}")
        return
    if not os.path.isdir(args.exam_dir):
        logging.error(f"Exam directory not found: {args.exam_dir}")
        return

    # Load all solutions from exam_dir
    solutions_per_model = {}
    max_score = 0
    try:
        solution_files = glob.glob(os.path.join(args.exam_dir, "exam_model_*_questions.json"))
        if not solution_files:
            logging.error(f"No 'exam_model_..._questions.json' files found in {args.exam_dir}")
            return

        for sol_file in solution_files:
            model_id_match = re.search(r"exam_model_(\w+)_questions.json", os.path.basename(sol_file))
            if model_id_match:
                model_id = model_id_match.group(1)
                exam = PexamExam.model_validate_json(Path(sol_file).read_text(encoding="utf-8"))
                solutions = {q.id: q.correct_answer_index for q in exam.questions if q.correct_answer_index is not None}
                solutions_per_model[model_id] = solutions
                if len(solutions) > max_score:
                    max_score = len(solutions)
        logging.info(f"Loaded solutions for models: {list(solutions_per_model.keys())}")
    except Exception as e:
        logging.error(f"Failed to load or parse solutions from {args.exam_dir}: {e}", exc_info=True)
        return

    os.makedirs(args.output_dir, exist_ok=True)
    
    correction_success = correct_exams(
        input_path=args.input_path,
        solutions_per_model=solutions_per_model,
        output_dir=args.output_dir
    )
    
    if correction_success:
        logging.info("Correction finished. Starting analysis.")
        results_csv = os.path.join(args.output_dir, "correction_results.csv")
        if os.path.exists(results_csv):
            analyze_results(
                csv_filepath=results_csv,
                max_score=max_score,
                output_dir=args.output_dir,
                void_questions_str=args.void_questions
            )
        else:
            logging.error(f"Analysis skipped: correction results file not found at {results_csv}")


def _handle_rexams(args):
    """Handles the logic for rexams correction by calling the core script functions."""
    logging.info("Starting R/exams correction...")

    try:
        st_lower, st_upper = map(float, args.scan_thresholds.split(','))
        scan_thresholds_tuple = (st_lower, st_upper)
    except ValueError:
        logging.error("Invalid --scan-thresholds format.")
        return

    student_csv_cols_dict = {
        "id": args.student_csv_id_col, "reg": args.student_csv_reg_col,
        "name": args.student_csv_name_col, "surname": args.student_csv_surname_col
    }

    results_csv_path = os.path.join(os.path.abspath(args.output_path), "exam_corrected_results.csv")
    r_script_successfully_completed = False

    if args.force_overwrite or not os.path.exists(results_csv_path):
        logging.info("Preparing to run R correction script...")
        try:
            r_script_successfully_completed = run_correction_script(
                all_scans_pdf=args.all_scans_pdf,
                student_info_csv=args.student_info_csv,
                solutions_rds=args.solutions_rds,
                output_path=args.output_path,
                language=args.exam_language,
                scan_thresholds=scan_thresholds_tuple,
                partial_eval=args.partial_eval,
                negative_points=args.negative_points,
                max_score=args.max_score,
                scale_mark_to=args.scale_mark_to,
                split_pages_python_control=args.split_pages_python_control,
                force_split_operation=args.force_overwrite,
                r_executable=args.r_executable,
                student_csv_cols=student_csv_cols_dict,
                student_csv_encoding=args.student_csv_encoding,
                registration_format=args.registration_format,
                force_nops_scan_r_script=args.force_overwrite,
                python_rotate_control=args.python_rotate_control,
                python_bw_threshold=args.python_bw_threshold
            )
        except Exception as e:
            logging.error(f"Exception during R script execution: {e}", exc_info=True)
            r_script_successfully_completed = False
    else:
        logging.info(f"R script evaluation skipped as results file '{results_csv_path}' already exists.")
        r_script_successfully_completed = True

    if r_script_successfully_completed and os.path.exists(results_csv_path):
        if args.max_score is not None:
            logging.info("Running exam results analysis...")
            analysis_output_dir = os.path.join(os.path.abspath(args.output_path), "analysis_plots")
            analyze_results(
                csv_filepath=results_csv_path,
                max_score=args.max_score,
                output_dir=analysis_output_dir,
                void_questions_str=args.void_questions,
                void_questions_nicely_str=args.void_questions_nicely
            )
        else:
            logging.warning("Skipping results analysis: --max-score not provided.")
    elif r_script_successfully_completed:
        logging.error("R script finished, but results CSV is missing.")
    else:
        logging.error("R script execution failed. Check logs for details.")


def handle_correct_command(args):
    """Dispatcher for the 'correct' command."""
    if args.correct_type == "pexams":
        _handle_pexams(args)
    elif args.correct_type == "rexams":
        _handle_rexams(args)
    else:
        logging.error(f"Unknown correction type: {args.correct_type}")
