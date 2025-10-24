import argparse
import logging
import os
import glob
import re
from pathlib import Path

from pexams.correct_exams import correct_exams
from pexams.analysis import analyze_results
from pexams.schemas import PexamExam

def main():
    """CLI for correcting exams using the pexams library."""
    
    parser = argparse.ArgumentParser(
        description="Correct exams using the pexams library."
    )
    
    parser.add_argument(
        "--input-path",
        type=str,
        required=True,
        help="Path to the single PDF file or a folder containing scanned answer sheets as PNG/JPG images."
    )
    parser.add_argument(
        "--exam-dir",
        type=str,
        required=True,
        help="Path to the directory containing exam models and solutions (e.g., the output from 'generate')."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory to save the correction results CSV and any debug images."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level."
    )
    parser.add_argument(
        "--void-questions",
        type=str,
        default=None,
        help="Comma-separated list of question numbers to remove from score calculation (e.g., '3,4')."
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

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

if __name__ == "__main__":
    main()
