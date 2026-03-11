"""
Handlers for 'autotestia correct wooclap' and 'autotestia correct moodle'.

These wrap the pexams online_results parsers and analysis pipeline, then
perform the extra autotestia-specific step of updating metadata.tsv with
the per-question answer-distribution statistics — exactly mirroring the
behaviour of autotestia/correct.py for pexams scanned exams.
"""

import logging
import os
import re
import sys

import pandas as pd

from Levenshtein import ratio as levenshtein_ratio

from . import artifacts, config
from .pipeline import AutoTestIAPipeline
from .pexams_converter import convert_autotestia_to_pexam
from .schemas import QuestionRecord, QuestionStage

from pexams import analysis, utils as pexams_utils
from pexams.io.online_results import parse_wooclap_results, parse_moodle_results

logger = logging.getLogger(__name__)

# Minimum similarity (0-1) to accept a Levenshtein fallback match.
LEVENSHTEIN_MATCH_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Shared helpers for updating TSV from question_stats.csv
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Strip and collapse whitespace for stable text matching."""
    if not text or not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", str(text).strip())


def _build_distribution_from_stats_row(row) -> dict:
    """Build the stats_answer_distribution dict from a question_stats.csv row (truncated texts as keys)."""
    dist = {}
    labels = [
        col.split("_")[1]
        for col in row.index
        if col.startswith("option_") and col.endswith("_count")
    ]
    for label in labels:
        count_col = f"option_{label}_count"
        text_col = f"option_{label}_text"
        try:
            count = int(row[count_col])
        except (ValueError, TypeError):
            count = 0
        if text_col in row and pd.notna(row[text_col]):
            dist[str(row[text_col]).strip()] = count
        else:
            dist[label] = count
    return dist


def _build_distribution_from_stats_row_with_record(row, record) -> dict:
    """
    Build stats_answer_distribution using the record's full option texts when possible.

    question_stats.csv uses truncated option text (e.g. width=50 in pexams). This
    resolves each truncated text to the record's full option text so the TSV stores
    full text, not "..." truncated strings.
    """
    dist = {}
    labels = [
        col.split("_")[1]
        for col in row.index
        if col.startswith("option_") and col.endswith("_count")
    ]
    try:
        full_options = list(record.get_latest_content().options)  # [correct_answer] + distractors
    except Exception:
        full_options = []

    for label in labels:
        count_col = f"option_{label}_count"
        text_col = f"option_{label}_text"
        try:
            count = int(row[count_col])
        except (ValueError, TypeError):
            count = 0
        stats_text = ""
        if text_col in row and pd.notna(row[text_col]):
            stats_text = str(row[text_col]).strip()
        if not stats_text:
            dist[label] = count
            continue

        # Resolve truncated stats text to full option text from the record
        truncated_clean = stats_text.rstrip(".").strip() if stats_text.endswith("...") else stats_text
        truncated_norm = _normalize_text(truncated_clean)
        key = stats_text  # fallback: keep truncated
        for full in full_options:
            if not full:
                continue
            full_norm = _normalize_text(full)
            if full_norm == truncated_norm or full_norm.startswith(truncated_norm) or truncated_norm.startswith(full_norm):
                key = full
                break
            if truncated_norm and full_norm and levenshtein_ratio(truncated_norm, full_norm) >= 0.99:
                key = full
                break
        dist[key] = count

    return dist


def _resolve_record_for_stats_row(
    row,
    records: list,
    records_map: dict,
    stats_question_text_key: str = "question_text",
) -> tuple:
    """
    Resolve a question_stats row to a QuestionRecord.

    Tries in order: (1) original_id exact match, (2) exact text match
    (normalized, truncation-aware), (3) best Levenshtein ratio above threshold.

    Returns (record, match_type) where match_type is "id", "exact_text", "levenshtein",
    or (None, None) if no match.
    """
    original_id = str(row.get("original_id", "")).strip()
    if original_id and original_id in records_map:
        return records_map[original_id], "id"

    stats_text = _normalize_text(row.get(stats_question_text_key, ""))
    if not stats_text:
        return None, None

    # Build (record, normalized_record_text) for records that have content.
    candidates = []
    for rec in records:
        try:
            rec_text = rec.get_latest_content().text
        except Exception:
            continue
        norm_rec = _normalize_text(rec_text)
        if norm_rec:
            candidates.append((rec, norm_rec))

    if not candidates:
        return None, None

    # Exact text match (truncation-aware: stats text is often truncated)
    for rec, norm_rec in candidates:
        if norm_rec == stats_text:
            return rec, "exact_text"
        if stats_text.startswith(norm_rec) or norm_rec.startswith(stats_text):
            return rec, "exact_text"

    # Best Levenshtein match above threshold
    best_rec, best_ratio = None, LEVENSHTEIN_MATCH_THRESHOLD
    for rec, norm_rec in candidates:
        r = levenshtein_ratio(stats_text, norm_rec)
        if r > best_ratio:
            best_ratio = r
            best_rec = rec
    if best_rec is not None:
        return best_rec, "levenshtein"

    return None, None


def update_tsv_from_question_stats(
    stats_csv_path: str,
    records: list,
    tsv_path: str,
    source: str,
    stats_question_text_key: str = "question_text",
) -> int:
    """
    Read question_stats.csv, match each row to a TSV record (by original_id,
    then exact text, then Levenshtein), apply stats, and write the TSV.

    Used by both correct.py (pexams) and correct_online.py (wooclap/moodle).
    Returns the number of questions whose stats were updated.
    """
    if not os.path.exists(stats_csv_path):
        logger.warning("question_stats.csv not found at '%s'. Skipping metadata update.", stats_csv_path)
        return 0

    try:
        stats_df = pd.read_csv(stats_csv_path)
    except Exception as e:
        logger.error("Failed to read question_stats.csv: %s", e)
        return 0

    records_map = {rec.question_id: rec for rec in records}
    updated_count = 0
    match_counts = {"id": 0, "exact_text": 0, "levenshtein": 0}

    for _, row in stats_df.iterrows():
        rec, match_type = _resolve_record_for_stats_row(
            row, records, records_map, stats_question_text_key=stats_question_text_key
        )
        if rec is None:
            continue

        rec.stats_source = source
        rec.stats_total_answers = int(row["total_answers"])
        rec.stats_answer_distribution = _build_distribution_from_stats_row_with_record(row, rec)
        updated_count += 1
        if match_type:
            match_counts[match_type] += 1
            if match_type != "id":
                logger.debug(
                    "Stats row matched by %s: original_id=%s -> question_id=%s",
                    match_type,
                    row.get("original_id"),
                    rec.question_id,
                )
                if match_type == "levenshtein":
                    stats_full = str(row.get(stats_question_text_key) or "")
                    stats_show = stats_full[:200] + ("..." if len(stats_full) > 200 else "")
                    rec_full = ""
                    try:
                        rec_full = rec.get_latest_content().text or ""
                    except Exception:
                        pass
                    rec_show = rec_full[:200] + ("..." if len(rec_full) > 200 else "")
                    logger.info(
                        "Levenshtein match: stats row text %r -> TSV question_id=%r text %r",
                        stats_show,
                        rec.question_id,
                        rec_show,
                    )

    if match_counts["exact_text"] or match_counts["levenshtein"]:
        logger.info(
            "Stats matching: %d by id, %d by exact text, %d by Levenshtein.",
            match_counts["id"],
            match_counts["exact_text"],
            match_counts["levenshtein"],
        )

    try:
        artifacts.write_metadata_tsv(records, tsv_path)
        logger.info("Updated statistics for %d question(s) in '%s'.", updated_count, tsv_path)
    except Exception as e:
        logger.error("Failed to write metadata TSV: %s", e)
        return 0

    if updated_count == 0 and len(stats_df) > 0:
        logger.warning(
            "No question stats could be matched to your TSV. Try re-exporting to pexams from AutoTestIA "
            "so that exam_model_*_questions.json contain original_id; then run correct again (or --only-analysis)."
        )

    return updated_count


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_questions_and_solutions(input_md_path: str):
    """Read the autotestia TSV, convert records to PexamQuestion objects, and
    build the solutions structures needed by pexams analysis.

    Returns ``(records, questions, solutions_full, solutions_simple, max_score)``
    or raises ``SystemExit`` on error.
    """
    md_path, tsv_path = artifacts.get_artifact_paths(input_md_path)

    # Ensure TSV exists first – it's the source of truth for questions.
    if not os.path.exists(tsv_path):
        logger.error("Metadata TSV not found: %s", tsv_path)
        sys.exit(1)

    # If the questions markdown file is missing but the TSV exists, regenerate
    # the .md from the latest question versions stored in the TSV without
    # prompting the user (non-interactive / script-friendly behaviour).
    if not os.path.exists(md_path):
        logger.warning("Questions file not found, regenerating from TSV: %s", md_path)
        records_for_md = artifacts.read_metadata_tsv(tsv_path)
        if not records_for_md:
            logger.error("No questions found in %s; cannot generate markdown file.", tsv_path)
            sys.exit(1)
        artifacts.write_questions_md(records_for_md, md_path)
        logger.info("Generated questions markdown file from TSV: %s", md_path)

    records = artifacts.read_metadata_tsv(tsv_path)
    if not records:
        logger.error("No questions found in %s", tsv_path)
        sys.exit(1)

    # Exclude removed questions from parsing/report; full records kept for TSV write-back.
    records_for_report = [r for r in records if not artifacts.is_question_removed(r)]
    questions = convert_autotestia_to_pexam(records_for_report, md_path)
    if not questions:
        logger.error("Could not convert any question records to PexamQuestion objects.")
        sys.exit(1)

    solutions_full, solutions_simple, max_score = pexams_utils.create_solutions_from_questions(questions)
    return records, questions, solutions_full, solutions_simple, max_score


def _run_analysis_and_update_tsv(
    records,
    tsv_path: str,
    correction_csv: str,
    output_dir: str,
    solutions_full: dict,
    max_score: int,
    penalty: float,
    evaluate_final: bool,
    evaluator_instructions,
    lang: str,
    generate_report: bool,
    source: str = "wooclap",
):
    """Run pexams analysis, read the resulting question_stats.csv, and update
    the autotestia metadata.tsv — the same logic used in correct.py step 4-5.
    """
    if generate_report:
        analysis.analyze_results(
            csv_filepath=correction_csv,
            max_score=max_score,
            output_dir=output_dir,
            solutions_per_model=solutions_full,
            penalty=penalty,
        )
    else:
        # Run only the parts we need for stats — skip PDF/plot generation by
        # calling analyze_results with a flag-less path; the CSV stats are
        # always produced as a side-effect of analyze_results regardless.
        analysis.analyze_results(
            csv_filepath=correction_csv,
            max_score=max_score,
            output_dir=output_dir,
            solutions_per_model=solutions_full,
            penalty=penalty,
        )

    # --- Update TSV stats from question_stats.csv (same as correct.py) ---
    updated_count = update_tsv_from_question_stats(
        stats_csv_path=os.path.join(output_dir, "question_stats.csv"),
        records=records,
        tsv_path=tsv_path,
        source=source,
    )
    if updated_count > 0:
        print(f"Updated statistics for {updated_count} question(s) in '{tsv_path}'.")

    # --- Optional final LLM evaluation ---
    if evaluate_final:
        logger.info("Running final evaluation on questions…")
        records = artifacts.read_metadata_tsv(tsv_path)
        pipeline = AutoTestIAPipeline()
        pipeline.evaluator.evaluate_records(
            records,
            stage=QuestionStage.FINAL,
            custom_instructions=evaluator_instructions,
            language=lang,
        )
        artifacts.write_metadata_tsv(records, tsv_path)
        logger.info("Final evaluation complete and metadata updated.")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_correct_wooclap(args):
    """Handler for 'autotestia correct wooclap'."""
    logger.info("Running CORRECT WOOCLAP command…")

    records, questions, solutions_full, _, max_score = _load_questions_and_solutions(
        args.input_md_path
    )
    _, tsv_path = artifacts.get_artifact_paths(args.input_md_path)

    os.makedirs(args.output_dir, exist_ok=True)

    results_df = parse_wooclap_results(
        results_path=args.results,
        questions=questions,
        fuzzy_threshold=args.fuzzy_threshold / 100.0,
        encoding=args.encoding,
        sep=args.sep,
    )

    correction_csv = os.path.join(args.output_dir, "correction_results.csv")
    results_df.to_csv(correction_csv, index=False)
    print(f"Correction results saved to: {correction_csv}")

    _run_analysis_and_update_tsv(
        records=records,
        tsv_path=tsv_path,
        correction_csv=correction_csv,
        output_dir=args.output_dir,
        solutions_full=solutions_full,
        max_score=max_score,
        penalty=getattr(args, "penalty", 0.0),
        evaluate_final=getattr(args, "evaluate_final", False),
        evaluator_instructions=getattr(args, "evaluator_instructions", None),
        lang=getattr(args, "lang", config.DEFAULT_LANGUAGE),
        generate_report=not getattr(args, "no_generate_report", False),
        source="wooclap",
    )

    logger.info("autotestia correct wooclap finished successfully.")


def handle_correct_moodle(args):
    """Handler for 'autotestia correct moodle'."""
    logger.info("Running CORRECT MOODLE command…")

    records, questions, solutions_full, _, max_score = _load_questions_and_solutions(
        args.input_md_path
    )
    _, tsv_path = artifacts.get_artifact_paths(args.input_md_path)

    os.makedirs(args.output_dir, exist_ok=True)

    question_order = None
    if getattr(args, "question_order", None):
        question_order = [int(x.strip()) - 1 for x in args.question_order.split(",")]

    results_df = parse_moodle_results(
        results_path=args.results,
        questions=questions,
        question_order=question_order,
        encoding=args.encoding,
        sep=args.sep,
    )

    correction_csv = os.path.join(args.output_dir, "correction_results.csv")
    results_df.to_csv(correction_csv, index=False)
    print(f"Correction results saved to: {correction_csv}")

    _run_analysis_and_update_tsv(
        records=records,
        tsv_path=tsv_path,
        correction_csv=correction_csv,
        output_dir=args.output_dir,
        solutions_full=solutions_full,
        max_score=max_score,
        penalty=getattr(args, "penalty", 0.0),
        evaluate_final=getattr(args, "evaluate_final", False),
        evaluator_instructions=getattr(args, "evaluator_instructions", None),
        lang=getattr(args, "lang", config.DEFAULT_LANGUAGE),
        generate_report=not getattr(args, "no_generate_report", False),
        source="moodle",
    )

    logger.info("autotestia correct moodle finished successfully.")
