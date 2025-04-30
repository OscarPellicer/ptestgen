import argparse
import random
import os
import sys
import logging
from typing import Optional

# Adjust path to import from the parent directory's 'autotestia' package
# script_dir = os.path.dirname(__file__)
# parent_dir = os.path.dirname(script_dir)
# sys.path.insert(0, parent_dir)

try:
    from autotestia.output_formatter import markdown_writer
    from autotestia.schemas import Question # Needed for type hinting
except ImportError as e:
    print(f"Error importing autotestia modules: {e}", file=sys.stderr)
    print("Ensure the script is run from the project root or the PYTHONPATH is set correctly.", file=sys.stderr)
    sys.exit(1)

def select_and_shuffle_questions(input_md_path: str, output_md_path: str, num_questions: int, seed: Optional[int] = None):
    """
    Parses a Markdown file, shuffles the questions, selects a subset,
    and writes them to a new Markdown file.
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    # --- Parse Input ---
    try:
        logging.info(f"Parsing input Markdown file: {input_md_path}")
        all_questions = markdown_writer.parse_reviewed_markdown(input_md_path)
        if not all_questions:
            logging.warning("Input Markdown file contained no valid questions.")
            # Write an empty file? Or just exit? Let's write an empty one.
            markdown_writer.write_questions_to_markdown([], output_md_path)
            logging.info(f"Empty output file written to {output_md_path}")
            return
        logging.info(f"Parsed {len(all_questions)} questions.")
    except FileNotFoundError:
        logging.error(f"Input Markdown file not found: {input_md_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing input Markdown file: {e}", exc_info=True)
        sys.exit(1)

    # --- Shuffle Questions ---
    shuffled_questions = list(all_questions) # Create a copy
    if seed is not None:
        logging.info(f"Shuffling questions with seed: {seed}")
        random.Random(seed).shuffle(shuffled_questions)
    else:
        logging.info("Shuffling questions randomly (no seed provided).")
        random.shuffle(shuffled_questions)

    # --- Select Subset ---
    if num_questions <= 0:
        logging.error(f"Number of questions must be positive. Got: {num_questions}")
        sys.exit(1)

    if num_questions >= len(shuffled_questions):
        selected_questions = shuffled_questions
        logging.warning(f"Requested {num_questions} questions, but only {len(shuffled_questions)} available. Selecting all.")
    else:
        selected_questions = shuffled_questions[:num_questions]
        logging.info(f"Selected the first {len(selected_questions)} questions after shuffling.")

    # --- Write Output ---
    try:
        logging.info(f"Writing {len(selected_questions)} questions to output Markdown: {output_md_path}")
        # Ensure output directory exists
        output_dir = os.path.dirname(output_md_path)
        if output_dir:
             os.makedirs(output_dir, exist_ok=True)
        markdown_writer.write_questions_to_markdown(selected_questions, output_md_path)
        logging.info("Successfully wrote output file.")
    except Exception as e:
        logging.error(f"Error writing output Markdown file: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shuffle and select a subset of questions from an AutoTestIA Markdown file.")
    parser.add_argument("input_md", help="Path to the input Markdown file containing questions.")
    parser.add_argument("output_md", help="Path to write the selected questions.")
    parser.add_argument("-n", "--num-questions", type=int, required=True, help="Number of questions to select.")
    parser.add_argument("-s", "--seed", type=int, default=None, help="Optional seed for shuffling reproducibility.")

    args = parser.parse_args()

    select_and_shuffle_questions(args.input_md, args.output_md, args.num_questions, args.seed)