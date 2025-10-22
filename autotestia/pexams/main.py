import argparse
import logging
import json
import os

from . import correct_exams, generate_exams
from .schemas import PexamQuestion

def main():
    """Main CLI entry point for the pexams library."""
    
    parser = argparse.ArgumentParser(
        description="Pexams: Generate and correct exams using Python, Marp, and OpenCV."
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Correction Command ---
    correct_parser = subparsers.add_parser(
        "correct",
        help="Correct scanned exam answer sheets from a PDF file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    correct_parser.add_argument(
        "--scans-pdf",
        type=str,
        required=True,
        help="Path to the single PDF file containing all scanned answer sheets."
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

    # --- Generation Command (Placeholder) ---
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate exam PDFs from a source (not fully implemented via CLI yet)."
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.command == "correct":
        if not os.path.exists(args.scans_pdf):
            logging.error(f"Scans PDF not found: {args.scans_pdf}")
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
            scanned_pdf_path=args.scans_pdf,
            solutions=solutions,
            output_dir=args.output_dir
        )
    
    elif args.command == "generate":
        logging.warning("The 'generate' command is not fully implemented via the CLI yet.")
        # Placeholder for future implementation
        # For example:
        # questions = ... # load from a file
        # generate_exams.generate_exams(questions, "generated_exams")
        pass

if __name__ == "__main__":
    main()
