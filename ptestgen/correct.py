import logging
import os
import sys

from . import artifacts
from . import config
from .pipeline import PTestGenPipeline
from .schemas import QuestionStage
from . import correct_online

from pexams.main import run_correction

def handle_correct(args):
    """Handler for the 'correct' command."""
    logging.info("Running CORRECT command...")

    # --- 1. Validation ---
    if not os.path.exists(args.input_md_path):
        logging.error(f"Input questions file not found: {args.input_md_path}")
        sys.exit(1)
        
    md_path, tsv_path = artifacts.get_artifact_paths(args.input_md_path)
    if not os.path.exists(tsv_path):
        logging.error(f"Metadata TSV file not found: {tsv_path}")
        sys.exit(1)

    # --- 2. Correct the scans, analyse them and fill --input-csv: the same code as `pexams correct` ---
    # args.lang is a language name ("Spanish"); the annotated sheets are labelled by its code.
    if not run_correction(args, lang=config.language_code(getattr(args, "lang", config.DEFAULT_LANGUAGE))):
        logging.error("Pexams correction failed.")
        sys.exit(1)

    # --- 3. Read Stats and Update TSV ---
    stats_csv_path = os.path.join(args.output_dir, "question_stats.csv")
    records = artifacts.read_metadata_tsv(tsv_path)
    if os.path.exists(md_path):
        md_questions = artifacts.read_questions_md(md_path)
        records = artifacts.synchronize_artifacts(records, md_questions)

    updated_count = correct_online.update_tsv_from_question_stats(
        stats_csv_path=stats_csv_path,
        records=records,
        tsv_path=tsv_path,
        source="pexams",
    )
    if updated_count >= 0:
        logging.info(f"Updated statistics for {updated_count} questions in '{tsv_path}'.")

    # --- 4. Evaluate Final (Optional) ---
    if args.evaluate_final:
        logging.info("Running final evaluation on questions...")
        
        # Filter for records that need evaluation or evaluate all?
        # The flag usually implies "ensure evaluated". 
        # But we can just run evaluate_records on all of them, the evaluator might re-evaluate.
        # Ideally we check if evaluation exists.
        
        pipeline = PTestGenPipeline() # Uses default config
        pipeline.evaluator.evaluate_records(
            records,
            stage=QuestionStage.FINAL,
            custom_instructions=args.evaluator_instructions,
            language=args.lang if hasattr(args, 'lang') else config.DEFAULT_LANGUAGE
        )
        
        artifacts.write_metadata_tsv(records, tsv_path)
        logging.info("Final evaluation complete and metadata updated.")

    logging.info("PTestGen correct command finished successfully.")



