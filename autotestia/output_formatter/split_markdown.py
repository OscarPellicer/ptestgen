import argparse
import os
import logging
import math
import random # Added for shuffling
from typing import List, Union, Dict, Any # Added Dict, Any

# Adjust import path based on the actual location of schemas.py and markdown_writer.py
# Assuming split_markdown.py is in autotestia/output_formatter/
from autotestia.schemas import Question
from autotestia.output_formatter.markdown_writer import parse_reviewed_markdown, write_questions_to_markdown

def main():
    parser = argparse.ArgumentParser(description="Split a Markdown file containing AutoTestIA questions into multiple files.")

    parser.add_argument("input_md_file",
                        help="Path to the input Markdown file to be split.")
    parser.add_argument("--splits",
                        nargs='+',
                        type=str, # Changed to str to handle mixed types (int/float)
                        required=True,
                        help="A list of integers (number of questions) or floats (proportion of total, 0.0-1.0) "
                             "defining the questions for each output file. "
                             "The last value can be -1 (integer) to include all remaining questions.")
    parser.add_argument("--output-dir",
                        default="output/splits",
                        help="Directory where the split Markdown files will be saved (default: output/splits).")
    parser.add_argument("--output-prefix",
                        default=None, # Default will be derived from input_md_file
                        help="Prefix for the output split filenames. E.g., split_part. Defaults to the input filename without extension.")
    parser.add_argument("--shuffle-questions",
                        type=int,
                        metavar='SEED',
                        nargs='?',
                        const=lambda: random.randint(1, 10000), # Use a random seed if flag is present without value
                        default=None, # No shuffling if flag is absent
                        help="Shuffle the order of questions before splitting. Provide an optional integer seed for reproducibility.")
    parser.add_argument("--log-level",
                        default='WARNING',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level (default: WARNING).")

    args = parser.parse_args()

    # Configure Logging
    log_level_name = args.log_level.upper()
    logging.basicConfig(level=log_level_name,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logging.info(f"Logging level set to: {log_level_name}")

    if not os.path.exists(args.input_md_file):
        logging.error(f"Input Markdown file not found: {args.input_md_file}")
        print(f"Error: Input Markdown file not found: {args.input_md_file}")
        return

    if not args.splits:
        logging.error("No splits defined. Please provide values for --splits.")
        print("Error: No splits defined. Use --splits to specify how to divide the questions.")
        return

    # Determine output prefix
    output_prefix = args.output_prefix
    if output_prefix is None:
        output_prefix = os.path.splitext(os.path.basename(args.input_md_file))[0]
    logging.info(f"Using output prefix: {output_prefix}")

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    logging.info(f"Output directory set to: {args.output_dir}")

    try:
        all_questions: List[Question] = parse_reviewed_markdown(args.input_md_file)
        total_questions = len(all_questions)
        logging.info(f"Successfully parsed {total_questions} questions from {args.input_md_file}.")
    except Exception as e:
        logging.error(f"Failed to parse input Markdown file {args.input_md_file}: {e}", exc_info=True)
        print(f"Error: Could not parse {args.input_md_file}. Ensure it is a valid question Markdown file.")
        return

    if not all_questions:
        logging.warning("No questions found in the input file. No output will be generated.")
        print("Warning: No questions found in the input file.")
        return

    # Shuffle questions if requested
    if args.shuffle_questions is not None:
        seed = args.shuffle_questions
        if callable(seed):
             seed = seed() # Call lambda to get random int if --shuffle-questions is used without a value
        logging.info(f"Shuffling {total_questions} questions with seed: {seed}")
        random.Random(seed).shuffle(all_questions)

    # Process split definitions
    processed_splits: List[Dict[str, Any]] = []
    has_remaining_split = False
    for i, s_str in enumerate(args.splits):
        try:
            val = int(s_str)
            if val == -1:
                if i == len(args.splits) - 1:
                    processed_splits.append({"type": "remaining", "value": -1})
                    has_remaining_split = True
                else:
                    logging.error("Split value -1 (all remaining) can only be used before the last item in --splits. Ignoring.")
                    print("Error: Split value -1 can only be the last split definition.")
                    # Optionally: return or raise error for strictness
                    continue
            elif val > 0:
                processed_splits.append({"type": "absolute", "value": val})
            else:
                logging.warning(f"Absolute split value must be positive or -1. Ignoring invalid split: {val}")
                continue
        except ValueError:
            try:
                val_float = float(s_str)
                if 0 < val_float <= 1.0:
                    num_q = math.ceil(val_float * total_questions)
                    processed_splits.append({"type": "percentage_total", "value": int(num_q)})
                else:
                    logging.warning(f"Percentage split value must be between 0 (exclusive) and 1.0 (inclusive). Ignoring invalid split: {val_float}")
                    continue
            except ValueError:
                logging.error(f"Invalid split value: '{s_str}'. Must be an integer, -1, or a float between 0 and 1.0. Skipping this split definition.")
                continue

    if not processed_splits and args.splits: # If all split inputs were invalid
        logging.error("All provided split definitions were invalid. No files will be generated.")
        print("Error: All --splits values were invalid.")
        return

    current_question_index = 0
    output_file_count = 0

    for i, split_instruction in enumerate(processed_splits):
        if current_question_index >= total_questions:
            logging.warning(f"No more questions left to split. Stopping before processing split definition {i+1} ('{args.splits[i]}').")
            break

        questions_for_this_file: List[Question] = []
        num_to_take = 0

        if split_instruction["type"] == "remaining":
            # This was already validated to be the last one if present
            questions_for_this_file = all_questions[current_question_index:]
            num_to_take = len(questions_for_this_file)
        elif split_instruction["type"] == "absolute" or split_instruction["type"] == "percentage_total":
            num_to_take = split_instruction["value"]
            if num_to_take <= 0: # Should have been caught by processing, but good to double check
                 logging.warning(f"Skipping split {i+1} due to non-positive question count: {num_to_take}")
                 continue
            end_index = current_question_index + num_to_take
            questions_for_this_file = all_questions[current_question_index:end_index]
        else:
            logging.error(f"Internal error: Unknown split type: {split_instruction['type']}")
            continue

        if not questions_for_this_file:
            # Log details about why no questions are being output for this split
            original_split_request = args.splits[i] if i < len(args.splits) else 'N/A'
            logging.info(f"No questions available for split {i+1} (original request: '{original_split_request}', calculated take: {num_to_take}, current index: {current_question_index}, total: {total_questions}).")
            if split_instruction["type"] == "remaining" and not has_remaining_split:
                pass # Avoid duplicate logs if it was already clear no questions were left for a non-explicit remaining
            elif not questions_for_this_file and current_question_index >= total_questions:
                logging.info("All questions have already been assigned to previous splits.")
            continue

        output_file_count += 1
        output_filename = os.path.join(args.output_dir, f"{output_prefix}_{output_file_count}.md")

        try:
            write_questions_to_markdown(questions_for_this_file, output_filename)
            logging.info(f"Successfully wrote {len(questions_for_this_file)} questions to {output_filename}")
            print(f"Generated: {output_filename} ({len(questions_for_this_file)} questions)")
        except Exception as e:
            logging.error(f"Failed to write questions to {output_filename}: {e}", exc_info=True)
            print(f"Error: Could not write to {output_filename}.")

        current_question_index += len(questions_for_this_file)

    if current_question_index < total_questions and not has_remaining_split:
        logging.warning(f"{total_questions - current_question_index} questions remain unsplit because the --splits argument did not cover all questions and did not end with -1.")
        print(f"Warning: {total_questions - current_question_index} questions were not included in any split file.")

    logging.info("Markdown splitting process complete.")

if __name__ == "__main__":
    main() 