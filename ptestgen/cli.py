"""The ``ptestgen`` argument parser: one small builder per command.

Handlers are imported on first use, so that ``ptestgen --help`` and light commands do not load
the LLM SDKs, OpenCV or Playwright.
"""
import argparse
import importlib
import logging
import random

from ptestgen import config  # loads the .env files
from pexams.main import add_correct_arguments, add_generate_pdf_arguments

EFFORTS = ["low", "medium", "high", "xhigh", "max"]
API_KEY_ENV_HELP = "(default: ANTHROPIC_API_KEY or OPENROUTER_API_KEY)."


def _lazy(module, name):
    """A command handler imported from ``module`` the first time it runs."""
    def handler(args):
        return getattr(importlib.import_module(module), name)(args)
    return handler


handle_generate = _lazy("ptestgen.commands", "handle_generate")
handle_export = _lazy("ptestgen.commands", "handle_export")
handle_test = _lazy("ptestgen.selftest", "handle_test")
handle_split_command = _lazy("ptestgen.split", "handle_split_command")
handle_merge_command = _lazy("ptestgen.merge", "handle_merge_command")
handle_shuffle_command = _lazy("ptestgen.shuffle", "handle_shuffle_command")
handle_correct = _lazy("ptestgen.correct", "handle_correct")
handle_correct_wooclap = _lazy("ptestgen.correct_online", "handle_correct_wooclap")
handle_correct_moodle = _lazy("ptestgen.correct_online", "handle_correct_moodle")
handle_evaluate = _lazy("ptestgen.evaluate", "handle_evaluate")


def setup_logging(log_level):
    """Configures the root logger."""
    log_level_name = log_level.upper()
    logging.basicConfig(level=log_level_name,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logging.info(f"Logging level set to: {log_level_name}")


def _add_seed_option(parser, flag, default, help_text):
    """An optional-value seed flag: absent gives ``default``, bare gives a random seed."""
    parser.add_argument(flag, type=int, metavar='SEED', nargs='?', const=random.randint(1, 10000),
                        default=default, help=help_text)


def _add_evaluator_instructions(parser):
    parser.add_argument("--evaluator-instructions", type=str, default=None,
                        help="Custom instructions for the evaluator prompt.")


def add_generate_parser(subparsers, common):
    p = subparsers.add_parser("generate", help="Generate questions from a source.", parents=[common])
    p.add_argument("input_material", nargs='*', default=[],
                   help="Paths to the input material files (e.g., .txt, .pdf). Can be multiple. If omitted, generation relies on instructions.")
    p.add_argument("-o", "--output-md-path", default="generated/questions.md",
                   help="Path to save the output markdown file. A .tsv file will be created alongside it.")
    p.add_argument("--generator-instructions", type=str, default=None, help="Custom instructions for the generator prompt.")
    p.add_argument("--reviewer-instructions", type=str, default=None, help="Custom instructions for the reviewer prompt.")
    _add_evaluator_instructions(p)
    p.add_argument("-i", "--images", nargs='+', default=[],
                   help="Optional image file path(s) to generate image-specific questions from.")
    p.add_argument("--include-images", action="store_true",
                   help="Attach images extracted from input documents as context for text-based generation. Does not create image-specific questions.")
    p.add_argument("-n", "--num-questions", type=int, default=config.DEFAULT_NUM_QUESTIONS,
                   help=f"Number of questions to generate from text (default: {config.DEFAULT_NUM_QUESTIONS}).")
    p.add_argument("--num-questions-per-image", type=int, default=1, help="Number of questions to generate per image (default: 1).")
    p.add_argument("--question-type", choices=["multiple_choice", "open_answer", "mixed"], default="multiple_choice",
                   help="Type of questions to generate: multiple_choice, open_answer, or mixed.")
    p.add_argument("--provider", choices=config.GENERATOR_MODEL_MAP.keys(), default=config.LLM_PROVIDER,
                   help=f"LLM provider to use (default: {config.LLM_PROVIDER}).")
    for role in ("generator", "reviewer", "evaluator"):
        p.add_argument(f"--{role}-model", default=None, help=f"Specific model for the {role} agent.")
    p.add_argument("--api-key-env", default=None, help=f"Environment variable holding the selected provider's API key {API_KEY_ENV_HELP}")
    p.add_argument("--effort", default=None, choices=EFFORTS, help="Reasoning effort for the three agents.")
    p.add_argument("--use-llm-review", action=argparse.BooleanOptionalAction, default=config.DEFAULT_LLM_REVIEW_ENABLED,
                   help="Enable LLM-based review.")
    p.add_argument("--skip-manual-review", action='store_true', help="Skip the manual review step (not recommended with new workflow).")
    p.add_argument("--language", default=config.DEFAULT_LANGUAGE, help=f"Language for the questions (default: {config.DEFAULT_LANGUAGE}).")
    p.add_argument("--evaluate-initial", action="store_true", help="Run evaluator on questions after generation.")
    p.add_argument("--evaluate-reviewed", action="store_true", help="Run evaluator on questions after the review stage.")
    p.set_defaults(func=handle_generate)


def _export_common_parser():
    """Arguments shared by every export format."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("input_md_path", help="Path to the input questions.md file.")
    _add_seed_option(p, "--shuffle-questions", None, "Shuffle question order.")
    _add_seed_option(p, "--shuffle-answers", 0, "Shuffle answer order.")
    p.add_argument("--num-final-questions", type=int, help="Randomly select N questions.")
    p.add_argument("--evaluate-final", action="store_true", help="Run evaluator on the final questions.")
    p.add_argument("--evaluator-model", default=None, help="Specific model for the evaluator agent.")
    _add_evaluator_instructions(p)
    p.add_argument("--max-image-width", type=int, default=None, help="Maximum width for images in pixels.")
    p.add_argument("--max-image-height", type=int, default=None, help="Maximum height for images in pixels.")
    return p


def _rexams_exam_parser():
    """Exam header arguments of the R/exams export."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--exam-title", help="Custom title for the exam PDF.")
    p.add_argument("--exam-course", help="Custom course name for the exam PDF.")
    p.add_argument("--exam-date", help="Custom date for the exam PDF.")
    p.add_argument("--exam-models", type=int, default=1, help="Number of different exam versions to generate.")
    p.add_argument("--exam-language", default=config.DEFAULT_LANGUAGE, help="Language for the exam PDF.")
    return p


def add_export_parser(subparsers, common):
    # This parser is just a container for the format subparsers.
    parser_export = subparsers.add_parser("export", help="Export questions to a specified format.")
    formats = parser_export.add_subparsers(dest="format", required=True, help="The output format.")
    parents = [common, _export_common_parser()]

    for name, help_text in (("moodle_xml", "Export to Moodle XML format."),
                            ("gift", "Export to GIFT format."),
                            ("wooclap", "Export to Wooclap CSV format."),
                            ("none", "Run export pre-processing without creating a final file.")):
        formats.add_parser(name, parents=parents, help=help_text)

    parser_pexams = formats.add_parser("pexams", parents=parents, help="Export to pexams PDF format.")
    # The flags and help are pexams' own; ptestgen prints one model in a smaller font by default.
    add_generate_pdf_arguments(parser_pexams, defaults={
        "num_models": 1, "font_size": "9pt", "lang": config.language_code(config.DEFAULT_LANGUAGE)})

    formats.add_parser("rexams", parents=parents + [_rexams_exam_parser()], help="Export to R/exams format.")
    parser_export.set_defaults(func=handle_export)


def _correct_common_parser():
    """Arguments shared by every ``correct`` source."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("input_md_path", help="Path to the questions.md file (used to update statistics in metadata.tsv).")
    p.add_argument("--output-dir", required=True, help="Directory to save correction results.")
    p.add_argument("--evaluate-final", action="store_true", help="Run the LLM evaluator on questions after correction.")
    _add_evaluator_instructions(p)
    p.add_argument("--lang", default=config.DEFAULT_LANGUAGE, help="Language for evaluation.")
    p.add_argument("--penalty", type=float, default=0.0, help="Score penalty for wrong answers (positive float; default: 0.0).")
    return p


def _add_online_results_arguments(parser):
    """Reading options of a Wooclap/Moodle results file (``--results`` is added by the caller)."""
    parser.add_argument("--encoding", default="auto", help="File encoding (default: auto-detect).")
    parser.add_argument("--sep", default="auto", help="CSV separator (default: auto-detect).")
    parser.add_argument("--no-generate-report", action="store_true", help="Skip PDF report generation.")


def add_correct_parser(subparsers, common):
    parser_correct = subparsers.add_parser(
        "correct", parents=[common],
        help="Correct exams (pexams scans, Wooclap results, or Moodle results) and update metadata.")
    sources = parser_correct.add_subparsers(dest="source", required=True,
                                            help="The source format of the student results.")
    parents = [common, _correct_common_parser()]

    p = sources.add_parser("pexams", parents=parents, help="Correct scanned pexams answer sheets.")
    # pexams' scan-correction flags; --output-dir, --penalty and --lang come from the common parser
    # (--lang is a language name there, used by the evaluator and, as a code, for the sheet labels).
    add_correct_arguments(p)
    p.set_defaults(func=handle_correct)

    p = sources.add_parser("wooclap", parents=parents,
                           help="Ingest Wooclap quiz results (CSV/XLSX from 'Export to Excel').")
    p.add_argument("--results", required=True, help="Path to the Wooclap results file (CSV or XLSX).")
    p.add_argument("--fuzzy-threshold", type=int, default=80,
                   help="Minimum similarity (0–100) for fuzzy question-text matching. Default: 80.")
    _add_online_results_arguments(p)
    p.set_defaults(func=handle_correct_wooclap)

    p = sources.add_parser("moodle", parents=parents,
                           help="Ingest Moodle quiz results (CSV/XLSX from Results > Responses > Download).")
    p.add_argument("--results", required=True, help="Path to the Moodle results file (CSV or XLSX).")
    p.add_argument("--question-order", default=None,
                   help="Comma-separated 1-based question indices mapping 'Resposta 1' to question N. "
                        "Default: sequential order.")
    _add_online_results_arguments(p)
    p.set_defaults(func=handle_correct_moodle)


def add_evaluate_parser(subparsers, common):
    p = subparsers.add_parser("evaluate", help="Run evaluator on questions.", parents=[common])
    p.add_argument("input_md_path", help="Path to the questions.md file.")
    p.add_argument("--stages", nargs='+', choices=['generated', 'reviewed', 'final'], default=['generated', 'reviewed', 'final'],
                   help="Stages to evaluate.")
    _add_evaluator_instructions(p)
    p.add_argument("--language", default=config.DEFAULT_LANGUAGE, help="Language for evaluation.")
    p.add_argument("--missing-only", action="store_true", help="Only evaluate questions missing an evaluation.")
    p.add_argument("--evaluator-model", default=None, help="Specific model for the evaluator agent.")
    p.add_argument("--api-key-env", default=None, help=f"Environment variable holding the provider's API key {API_KEY_ENV_HELP}")
    p.add_argument("--effort", default=None, choices=EFFORTS, help="Reasoning effort for the evaluator.")
    p.set_defaults(func=handle_evaluate)


def add_split_parser(subparsers, common):
    p = subparsers.add_parser("split", help="Split a test into multiple parts.", parents=[common])
    p.add_argument("input_md_path", help="Path to the input questions.md file to split.")
    p.add_argument("--splits", nargs='+', type=str, required=True,
                   help="A list of integers (number of questions) or floats (proportion) defining the splits.")
    p.add_argument("--output-dir", help="Directory to save the split files (optional, defaults to the input file's directory).")
    _add_seed_option(p, "--shuffle-questions", None, "Shuffle questions before splitting. Provide an optional seed.")
    p.set_defaults(func=handle_split_command)


def add_merge_parser(subparsers, common):
    p = subparsers.add_parser("merge", help="Merge multiple tests into one.", parents=[common])
    p.add_argument("input_md_paths", nargs='+', help="List of paths to the input questions.md files to merge.")
    p.add_argument("-o", "--output-md-path", required=True, help="Path to save the merged output markdown file.")
    p.set_defaults(func=handle_merge_command)


def add_shuffle_parser(subparsers, common):
    p = subparsers.add_parser("shuffle", help="Shuffle questions in a markdown file in-place.", parents=[common])
    p.add_argument("input_md_file", help="Path to the markdown file to shuffle.")
    p.add_argument("--seed", type=int, help="Optional integer seed for reproducible shuffling.")
    p.add_argument("-y", "--yes", action="store_true", help="Bypass the confirmation prompt and overwrite the file directly.")
    p.set_defaults(func=handle_shuffle_command)


def add_test_parser(subparsers, common):
    p = subparsers.add_parser("test", help="Run a full pipeline test to check for runtime errors.", parents=[common])
    p.set_defaults(func=handle_test)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PTestGen: A tool for AI-assisted generation of test questions.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # Parent parser for the arguments of every command.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set the logging verbosity.")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    for add in (add_generate_parser, add_export_parser, add_correct_parser, add_evaluate_parser,
                add_split_parser, add_merge_parser, add_shuffle_parser, add_test_parser):
        add(subparsers, common)

    from ptestgen import agent_skill, course
    agent_skill.add_parser(subparsers, [common])
    course.add_parser(subparsers, [common])
    return parser
