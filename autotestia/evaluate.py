import argparse
import logging
import os
import sys

from . import artifacts
from . import config
from .pipeline import AutoTestIAPipeline
from .schemas import QuestionStage

def handle_evaluate(args):
    """Handler for the 'evaluate' command."""
    logging.info(f"Running EVALUATE command (missing_only={args.missing_only})...")

    # --- 1. Validation ---
    md_path, tsv_path = artifacts.get_artifact_paths(args.input_md_path)
    if not os.path.exists(tsv_path):
        logging.error(f"Metadata TSV file not found: {tsv_path}")
        sys.exit(1)

    records = artifacts.read_metadata_tsv(tsv_path)
    if not records:
        logging.warning("No records found in metadata file.")
        return

    pipeline = AutoTestIAPipeline()
    
    # --- 2. Check and Evaluate Each Stage ---
    
    stages_to_check = []
    if args.stages:
        stages_to_check = args.stages
    else:
        stages_to_check = ['generated', 'reviewed', 'final']

    total_evaluated = 0

    # We process by stage to batch calls if possible, but evaluate_records takes a list.
    # So filter lists for each stage.

    if 'generated' in stages_to_check:
        to_eval = [r for r in records if r.generated and r.generated.content and (not args.missing_only or not r.generated.evaluation)]
        if to_eval:
            logging.info(f"Found {len(to_eval)} records for GENERATED evaluation.")
            pipeline.evaluator.evaluate_records(
                to_eval,
                stage=QuestionStage.GENERATED,
                custom_instructions=args.evaluator_instructions,
                language=args.language
            )
            total_evaluated += len(to_eval)

    if 'reviewed' in stages_to_check:
        to_eval = [r for r in records if r.reviewed and r.reviewed.content and (not args.missing_only or not r.reviewed.evaluation)]
        if to_eval:
            logging.info(f"Found {len(to_eval)} records for REVIEWED evaluation.")
            pipeline.evaluator.evaluate_records(
                to_eval,
                stage=QuestionStage.REVIEWED,
                custom_instructions=args.evaluator_instructions,
                language=args.language
            )
            total_evaluated += len(to_eval)

    if 'final' in stages_to_check:
        to_eval = [r for r in records if r.final and r.final.content and (not args.missing_only or not r.final.evaluation)]
        if to_eval:
            logging.info(f"Found {len(to_eval)} records for FINAL evaluation.")
            pipeline.evaluator.evaluate_records(
                to_eval,
                stage=QuestionStage.FINAL,
                custom_instructions=args.evaluator_instructions,
                language=args.language
            )
            total_evaluated += len(to_eval)

    # --- 3. Save ---
    if total_evaluated > 0:
        artifacts.write_metadata_tsv(records, tsv_path)
        logging.info(f"Updated evaluations for {total_evaluated} stages/records.")
    else:
        logging.info("No evaluations needed.")

