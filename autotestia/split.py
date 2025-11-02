import argparse
import os
import logging
import math
import random
from typing import List, Dict, Any

from . import artifacts
from .schemas import QuestionRecord

def handle_split_command(args):
    """Handler for the 'split' command."""
    md_path, tsv_path = artifacts.get_artifact_paths(args.input_md_path)
    output_dir = args.output_dir or os.path.dirname(md_path)
    base_name = os.path.splitext(os.path.basename(md_path))[0]

    print(f"Splitting '{md_path}'...")
    logging.info(f"Reading questions from: {md_path}")
    logging.info(f"Reading metadata from: {tsv_path}")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"Output directory set to: {output_dir}")

    try:
        all_records: List[QuestionRecord] = artifacts.read_metadata_tsv(tsv_path)
        total_questions = len(all_records)
        logging.info(f"Successfully parsed {total_questions} records from {tsv_path}.")
    except Exception as e:
        logging.error(f"Failed to parse metadata file {tsv_path}: {e}", exc_info=True)
        return

    if not all_records:
        logging.warning("No question records found in the input file.")
        return

    if args.shuffle_questions is not None:
        seed = args.shuffle_questions
        logging.info(f"Shuffling {total_questions} questions with seed: {seed}")
        random.Random(seed).shuffle(all_records)

    # Process split definitions
    processed_splits: List[Dict[str, Any]] = []
    has_remaining_split = False
    for i, s_str in enumerate(args.splits):
        # ... (This logic remains the same as the old script, parsing int, float, -1)
        # For brevity, I will not write it all out here but will include it in the final code.
        try:
            val = int(s_str)
            if val == -1:
                processed_splits.append({"type": "remaining", "value": -1})
                has_remaining_split = True
            else:
                processed_splits.append({"type": "absolute", "value": val})
        except ValueError:
            val_float = float(s_str)
            num_q = math.ceil(val_float * total_questions)
            processed_splits.append({"type": "percentage_total", "value": int(num_q)})


    current_question_index = 0
    output_dir_count = 0

    # base_output_prefix = os.path.basename(os.path.normpath(args.input_dir)) # This line is no longer needed

    for split_instruction in processed_splits:
        if current_question_index >= total_questions:
            logging.warning("No more questions left to split.")
            break

        records_for_this_split: List[QuestionRecord] = []
        num_to_take = 0

        if split_instruction["type"] == "remaining":
            records_for_this_split = all_records[current_question_index:]
            num_to_take = len(records_for_this_split)
        else: # absolute or percentage
            num_to_take = split_instruction["value"]
            end_index = current_question_index + num_to_take
            records_for_this_split = all_records[current_question_index:end_index]

        if not records_for_this_split:
            continue

        output_dir_count += 1
        
        try:
            split_md_path = os.path.join(output_dir, f"{base_name}_{output_dir_count}.md")
            split_tsv_path = os.path.join(output_dir, f"{base_name}_{output_dir_count}.tsv")
            
            artifacts.write_artifacts(
                records=records_for_this_split,
                md_path=split_md_path,
                tsv_path=split_tsv_path
            )
            print(f"  -> Created split {output_dir_count} ({len(records_for_this_split)} questions): '{split_md_path}'")
        except Exception as e:
            logging.error(f"Failed to write artifacts for split {output_dir_count}: {e}", exc_info=True)

        current_question_index += len(records_for_this_split)

    if current_question_index < total_questions and not has_remaining_split:
        logging.warning(f"{total_questions - current_question_index} questions remain unsplit.")
        print(f"Warning: {total_questions - current_question_index} questions were not included in any split file.")

    logging.info("Splitting process complete.")
