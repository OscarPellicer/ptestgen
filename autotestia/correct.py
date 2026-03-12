import argparse
import logging
import os
import sys

from . import artifacts
from . import config
from .pipeline import AutoTestIAPipeline
from .schemas import QuestionStage
from . import correct_online

from pexams import correct_exams
from pexams import analysis
from pexams import utils

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

    if not os.path.isdir(args.exam_dir):
        logging.error(f"Exam directory not found: {args.exam_dir}")
        sys.exit(1)

    if args.penalty < 0:
        logging.warning("Penalty cannot be negative (it is subtracted). Converting to positive.")
        args.penalty = abs(args.penalty)

    # --- 2. Run Pexams Correction ---
    # Load solutions first to verify exam_dir
    solutions_full, solutions_simple, max_score = utils.load_solutions(args.exam_dir)
    if not solutions_simple:
        logging.error("Could not load solutions from exam directory.")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    if args.only_analysis:
        logging.info("Skipping image correction (--only-analysis). Using existing results.")
        correction_success = True
    else:
        correction_success = correct_exams.correct_exams(
            input_path=args.input_path,
            solutions_per_model=solutions_simple,
            output_dir=args.output_dir,
            questions_dir=args.exam_dir
        )
    
    if not correction_success:
        logging.error("Pexams correction failed.")
        sys.exit(1)

    # --- 3. Run Pexams Analysis ---
    logging.info("Correction finished. Starting analysis.")
    results_csv = os.path.join(args.output_dir, "correction_results.csv")
    
    if not os.path.exists(results_csv):
        logging.error(f"Correction results file not found at {results_csv}")
        sys.exit(1)

    analysis.analyze_results(
        csv_filepath=results_csv,
        max_score=max_score,
        output_dir=args.output_dir,
        void_questions_str=args.void_questions,
        solutions_per_model=solutions_full,
        void_questions_nicely_str=args.void_questions_nicely,
        penalty=args.penalty
    )

    # --- 4. Read Stats and Update TSV ---
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

    # --- 5. Evaluate Final (Optional) ---
    if args.evaluate_final:
        logging.info("Running final evaluation on questions...")
        
        # Filter for records that need evaluation or evaluate all?
        # The flag usually implies "ensure evaluated". 
        # But we can just run evaluate_records on all of them, the evaluator might re-evaluate.
        # Ideally we check if evaluation exists.
        
        pipeline = AutoTestIAPipeline() # Uses default config
        pipeline.evaluator.evaluate_records(
            records,
            stage=QuestionStage.FINAL,
            custom_instructions=args.evaluator_instructions,
            language=args.lang if hasattr(args, 'lang') else config.DEFAULT_LANGUAGE
        )
        
        artifacts.write_metadata_tsv(records, tsv_path)
        logging.info("Final evaluation complete and metadata updated.")

    logging.info("AutoTestIA correct command finished successfully.")

