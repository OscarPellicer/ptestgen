import argparse
import logging
import json
import os

from . import correct_exams, generate_exams
from .schemas import PexamExam, PexamQuestion
from pydantic import ValidationError

def main():
    """Main CLI entry point for the pexams library."""
    
    parser = argparse.ArgumentParser(
        description="Pexams: Generate and correct exams using Python, Playwright, and OpenCV."
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Correction Command ---
    correct_parser = subparsers.add_parser(
        "correct",
        help="Correct scanned exam answer sheets from a PDF file or a folder of images.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    correct_parser.add_argument(
        "--input-path",
        type=str,
        required=True,
        help="Path to the single PDF file or a folder containing scanned answer sheets as PNG/JPG images."
    )
    correct_parser.add_argument(
        "--solutions-json",
        type=str,
        required=True,
        help="Path to a JSON file containing the solutions. \n"
             "The file should be a dictionary mapping question ID (str or int) to the 0-based index of the correct answer (int)."
    )
    correct_parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory to save the correction results CSV and any debug images."
    )
    correct_parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level."
    )

    # --- Generation Command ---
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate exam PDFs from a JSON file of questions."
    )
    generate_parser.add_argument(
        "--questions-json",
        type=str,
        required=True,
        help="Path to the JSON file containing the exam questions."
    )
    generate_parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory to save the generated exam PDFs."
    )
    generate_parser.add_argument("--num-models", type=int, default=4, help="Number of different exam models to generate.")
    generate_parser.add_argument("--exam-title", type=str, default="Final Exam", help="Title of the exam.")
    generate_parser.add_argument("--exam-course", type=str, default=None, help="Course name for the exam.")
    generate_parser.add_argument("--exam-date", type=str, default=None, help="Date of the exam.")
    generate_parser.add_argument("--columns", type=int, default=1, choices=[1, 2, 3], help="Number of columns for the questions.")
    generate_parser.add_argument("--font-size", type=str, default="11pt", help="Base font size for the exam (e.g., '10pt', '12px').")
    generate_parser.add_argument("--id-length", type=int, default=10, help="Number of boxes for the student ID.")
    generate_parser.add_argument("--lang", type=str, default="en", help="Language for the answer sheet.")
    generate_parser.add_argument("--keep-html", action="store_true", help="Keep the intermediate HTML files.")
    generate_parser.add_argument("--test-mode", action="store_true", help="Generate simulated scans with fake answers for testing the correction process.")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = getattr(logging, args.log_level.upper() if hasattr(args, 'log_level') else 'INFO', logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.command == "correct":
        if not os.path.exists(args.input_path):
            logging.error(f"Input path not found: {args.input_path}")
            return
        if not os.path.exists(args.solutions_json):
            logging.error(f"Solutions JSON not found: {args.solutions_json}")
            return
            
        try:
            with open(args.solutions_json, 'r') as f:
                solutions_raw = json.load(f)
                # Convert keys to int for consistency
                solutions = {int(k): int(v) for k, v in solutions_raw.items()}
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"Failed to parse solutions JSON file: {e}")
            return

        os.makedirs(args.output_dir, exist_ok=True)
        
        correct_exams.correct_exams(
            input_path=args.input_path,
            solutions=solutions,
            output_dir=args.output_dir
        )
    
    elif args.command == "generate":
        if not os.path.exists(args.questions_json):
            logging.error(f"Questions JSON file not found: {args.questions_json}")
            return
        
        try:
            exam = PexamExam.parse_file(args.questions_json)
            questions = exam.questions
        except ValidationError as e:
            logging.error(f"Failed to validate questions JSON file: {e}")
            return
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse questions JSON file: {e}")
            return

        generate_exams.generate_exams(
            questions=questions,
            output_dir=args.output_dir,
            num_models=args.num_models,
            exam_title=args.exam_title,
            exam_course=args.exam_course,
            exam_date=args.exam_date,
            columns=args.columns,
            id_length=args.id_length,
            lang=args.lang,
            keep_html=args.keep_html,
            font_size=args.font_size,
            test_mode=args.test_mode
        )

if __name__ == "__main__":
    main()
