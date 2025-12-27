import argparse
import os
import sys
from dotenv import load_dotenv
import logging
import random
import shutil

# Load .env file BEFORE importing config or pipeline
# This ensures environment variables are set when config is loaded
load_dotenv()

# Now import local modules
from autotestia.pipeline import AutoTestIAPipeline
from autotestia import config # Import config AFTER dotenv load
from autotestia import artifacts # Import artifacts module
from autotestia.split import handle_split_command
from autotestia.merge import handle_merge_command
from autotestia.shuffle import handle_shuffle_command
from autotestia.correct import handle_correct
from autotestia.evaluate import handle_evaluate


def setup_logging(log_level):
    """Configures the root logger."""
    log_level_name = log_level.upper()
    logging.basicConfig(level=log_level_name,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logging.info(f"Logging level set to: {log_level_name}")

def handle_test(args):
    """Handler for the 'test' command."""
    logging.info("Running TEST command...")

    output_dir = "generated_test"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Test artifacts will be saved in '{os.path.abspath(output_dir)}'")

    try:
        script_dir = os.path.dirname(__file__)
        image_path = os.path.join(script_dir, "media", "image.jpg")
        test_questions = 2

        instructions = "This is a TEST RUN for the AutoTestIA library, a library that allows you to generate multiple-choice questions from text or images using LLms. Generate questions about Python programming. MAKE SURE to include at least one instance of all the formatting options in the questions and answers: **bold text**, *italic text*, `code`, $LaTeX_expression$ (such as $\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$)."

        # --- 1. Generation ---
        print("\n--- Step 1: Generating questions (OpenRouter) ---")
        or_md_path = os.path.join(output_dir, "openrouter_questions.md")
        args_gen_or = argparse.Namespace(
            input_material=None, output_md_path=or_md_path,
            generator_instructions=instructions, reviewer_instructions=None, evaluator_instructions=None,
            images=[image_path] if image_path else [], num_questions=test_questions, provider="openrouter",
            generator_model="google/gemini-2.5-pro", # A quicker model for testing
            reviewer_model="google/gemini-2.5-flash",
            evaluator_model="google/gemini-2.5-flash",
            use_llm_review=True, language="es",
            evaluate_initial=True, evaluate_reviewed=True,
            num_questions_per_image=1
        )
        handle_generate(args_gen_or)

        print("\n--- Step 1b: Generating questions (OpenAI) ---")
        openai_md_path = os.path.join(output_dir, "openai_questions.md")
        args_gen_openai = argparse.Namespace(
            input_material=None, output_md_path=openai_md_path,
            generator_instructions=instructions, reviewer_instructions=None, evaluator_instructions=None,
            images=[image_path] if image_path else [], num_questions=test_questions, provider="openai",
            generator_model="gpt-4o", 
            reviewer_model="gpt-4o-mini", 
            evaluator_model="gpt-4o",
            use_llm_review=True, language="es",
            evaluate_initial=True, evaluate_reviewed=True,
            num_questions_per_image=1
        )
        handle_generate(args_gen_openai)

        # --- 2. Split ---
        print("\n--- Step 2: Splitting test ---")
        split_dir = os.path.join(output_dir, "splits")
        args_split = argparse.Namespace(
            input_md_path=or_md_path, splits=["1", "1", "-1"],
            output_dir=split_dir, shuffle_questions=None
        )
        handle_split_command(args_split)
        
        # --- 3. Merge ---
        print("\n--- Step 3: Merging tests ---")
        merged_md_path = os.path.join(output_dir, "merged_questions.md")
        split_files = [os.path.join(split_dir, f) for f in os.listdir(split_dir) if f.endswith('.md')]
        args_merge = argparse.Namespace(
            input_md_paths=split_files + [openai_md_path],
            output_md_path=merged_md_path
        )
        handle_merge_command(args_merge)

        # --- 4. Shuffle ---
        print("\n--- Step 4: Shuffling test ---")
        args_shuffle = argparse.Namespace(
            input_md_file=merged_md_path, # Shuffle the new file
            seed=42,
            yes=True
        )
        handle_shuffle_command(args_shuffle)


        # --- 5. Simulate Manual Edit ---
        print("\n--- Step 5: Simulating manual edits ---")
        
        # Read the TSV to find a valid ID to change
        shuffled_tsv_path = artifacts.get_artifact_paths(merged_md_path)[1]
        records = artifacts.read_metadata_tsv(shuffled_tsv_path)
        
        if len(records) > 1:
            # Find an ID to change and one to modify
            id_to_change = records[0].question_id
            new_id = f"{id_to_change}_modified"
            id_to_modify_content = records[1].question_id
            
            with open(merged_md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Change an ID by replacing its markdown header
            content = content.replace(f"## {id_to_change}", f"## {new_id}")
            
            # Modify content of another question
            question_header_to_find = f"## {id_to_modify_content}"
            q_start_index = content.find(question_header_to_find)
            if q_start_index != -1:
                # Find the end of this question block by looking for the next header or end of file
                next_q_start_index = content.find("\n## ", q_start_index + 1)
                if next_q_start_index == -1:
                    next_q_start_index = len(content)

                # Find the start of the first answer option within this question's block
                first_answer_index = content.find("\n* ", q_start_index, next_q_start_index)
                
                if first_answer_index != -1:
                    # Append "(modified)" right before the answers start
                    content = content[:first_answer_index] + " (modified)" + content[first_answer_index:]

            with open(merged_md_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Applied edits to markdown file.")
        else:
            print("Not enough questions to simulate edits, skipping.")

        # --- 6. Export ---
        print("\n--- Step 6: Exporting to final formats ---")
        common_export_args = {
            'input_md_path': merged_md_path,
            'shuffle_questions': None, 'shuffle_answers': None, 'num_final_questions': None,
            'evaluate_final': True, 'evaluator_instructions': None, 'exam_title': 'Test Exam', 'exam_course': 'AutoTestIA Course',
            'exam_date': '2025-01-01', 'num_models': 1, 'lang': 'en',
            'font_size': '11pt', 'columns': 2,
            # 'max_image_width': 400, # If two columns, do not use max width
            'max_image_height': 300,
        }

        # Wooclap
        print("Exporting to Wooclap...")
        args_export_wooclap = argparse.Namespace(format='wooclap', **common_export_args)
        handle_export(args_export_wooclap)

        # Disable final evaluation for subsequent exports
        common_export_args['evaluate_final'] = False

        # Moodle XML
        print("Exporting to Moodle XML...")
        args_export_moodle = argparse.Namespace(format='moodle_xml', **common_export_args)
        handle_export(args_export_moodle)

        # Pexams
        print("Exporting to pexams (with fakes)...")
        pexams_export_args = common_export_args.copy()
        pexams_export_args.update({
            'generate_fakes': 1,
            'generate_references': True,
            'columns': 2,
            'font_size': '10pt',
            'custom_header': '## Instructions\nAnswer the questions carefully.',
            'shuffle_answers': 42 # Explicitly test deterministic answer shuffling
        })
        args_export_pexams = argparse.Namespace(format='pexams', **pexams_export_args)
        handle_export(args_export_pexams)

        # --- 7. Correct (New) ---
        print("\n--- Step 7: Correcting pexams scans via autotestia correct ---")
        base_name = os.path.splitext(os.path.basename(merged_md_path))[0]
        pexams_output_dir = os.path.join(output_dir, f"{base_name}_pexams_output")
        simulated_scans_dir = os.path.join(pexams_output_dir, "simulated_scans")
        correction_dir = os.path.join(pexams_output_dir, "correction_results")
        
        args_correct = argparse.Namespace(
            input_md_path=merged_md_path,
            input_path=simulated_scans_dir,
            exam_dir=pexams_output_dir,
            output_dir=correction_dir,
            evaluate_final=True, # Test the new evaluation feature
            evaluator_instructions=None,
            lang="en",
            void_questions=None, void_questions_nicely=None,
            input_csv=None, id_column=None, mark_column=None, name_column=None, simplify_csv=False,
            fuzzy_id_match=100, penalty=0.0, input_encoding="utf-8", input_sep=",", output_decimal_sep=".",
            only_analysis=False
        )
        handle_correct(args_correct)

        # Verify stats update
        shuffled_tsv_path = artifacts.get_artifact_paths(merged_md_path)[1]
        records = artifacts.read_metadata_tsv(shuffled_tsv_path)
        stats_updated = any(r.stats_total_answers is not None for r in records)
        if stats_updated:
            print("Verified: Statistics have been updated in the metadata TSV.")
        else:
            print("WARNING: Statistics were NOT updated in the metadata TSV (this might be expected if pexams fakes were skipped, but fakes were enabled).")

        # --- 8. Evaluate (New) ---
        print("\n--- Step 8: Testing evaluate command ---")
        args_eval = argparse.Namespace(
            input_md_path=merged_md_path,
            stages=['generated', 'reviewed', 'final'],
            evaluator_instructions=None,
            language="en",
            missing_only=True
        )
        handle_evaluate(args_eval)
        
        print("\n--- Test command finished successfully! ---")
    
    except Exception as e:
        logging.error(f"Test command failed: {e}", exc_info=True)
        print(f"\n--- ERROR: Test command failed ---\n{e}\n")
        sys.exit(1)


def handle_generate(args):
    """Handler for the 'generate' command."""
    logging.info("Running GENERATE command...")

    # --- Argument Validation ---
    if not args.input_material and not args.generator_instructions:
        logging.warning("Generating without an input file or specific generator instructions. Relying on default prompts.")
        print("Warning: No input file or --generator-instructions provided. Generation might be generic.", file=sys.stderr)

    # --- Configuration ---
    effective_provider = args.provider
    config_override = {"llm_provider": effective_provider}

    # Determine effective models
    model_keys = ["generator_model", "reviewer_model", "evaluator_model"]
    model_maps = [config.GENERATOR_MODEL_MAP, config.REVIEWER_MODEL_MAP, config.EVALUATOR_MODEL_MAP]

    for key, model_map in zip(model_keys, model_maps):
        cli_model = getattr(args, key)
        if cli_model:
            config_override[key] = cli_model
        else:
            config_override[key] = model_map.get(effective_provider, f"stub-{key}")

    # Override review flag if explicitly set
    if args.use_llm_review != config.DEFAULT_LLM_REVIEW_ENABLED:
        config_override["use_llm_review"] = args.use_llm_review

    # --- API Key Check ---
    if effective_provider not in ["stub", "ollama"]:
        api_key_var = config.PROVIDER_API_KEY_MAP.get(effective_provider)
        if not api_key_var or not os.getenv(api_key_var):
             print(f"Error: Provider '{effective_provider}' selected, but its API key ({api_key_var}) was not found in .env or environment variables.", file=sys.stderr)
             sys.exit(1)

    # --- Pipeline Execution ---
    md_path, tsv_path = artifacts.get_artifact_paths(args.output_md_path)
    pipeline = AutoTestIAPipeline(config_override=config_override)
    pipeline.generate(
        input_material_paths=args.input_material,
        image_paths=args.images,
        output_md_path=md_path,
        output_tsv_path=tsv_path,
        num_questions=args.num_questions,
        language=args.language,
        generator_instructions=args.generator_instructions,
        reviewer_instructions=args.reviewer_instructions,
        evaluator_instructions=args.evaluator_instructions,
        evaluate_initial=args.evaluate_initial,
        evaluate_reviewed=args.evaluate_reviewed,
        num_questions_per_image=args.num_questions_per_image
    )

def handle_export(args):
    """Handler for the 'export' command."""
    logging.info(f"Running EXPORT command from file: {args.input_md_path}")

    # --- Read Artifacts ---
    md_path, tsv_path = artifacts.get_artifact_paths(args.input_md_path)
    if not os.path.exists(md_path) or not os.path.exists(tsv_path):
        logging.error(f"Input file '{args.input_md_path}' must contain both '{artifacts.QUESTIONS_FILENAME}' and '{artifacts.METADATA_FILENAME}'.")
        sys.exit(1)
        
    records = artifacts.read_metadata_tsv(tsv_path)
    manually_edited_questions = artifacts.read_questions_md(md_path)

    # --- Synchronize Artifacts ---
    synced_records = artifacts.synchronize_artifacts(records, manually_edited_questions)
    
    # Filter out removed questions for export
    records_to_export = [
        rec for rec in synced_records 
        if not (rec.changes_rev_to_man and rec.changes_rev_to_man.status == "removed") and
           not (rec.changes_gen_to_rev and rec.changes_gen_to_rev.status == "removed")
    ]

    if not records_to_export:
        logging.warning("No valid questions remaining after synchronization. Nothing to export.")
        # Save the updated (potentially empty) metadata
        artifacts.write_metadata_tsv(synced_records, tsv_path)
        return

    # --- Pipeline Execution for Export ---
    pipeline = AutoTestIAPipeline() # No config override needed for export
    pipeline.export(
        records_to_export=records_to_export,
        input_md_path=md_path, # Pass the markdown path
        output_formats=[args.format],
        shuffle_questions_seed=args.shuffle_questions,
        shuffle_answers_seed=args.shuffle_answers,
        num_final_questions=args.num_final_questions,
        evaluate_final=args.evaluate_final,
        evaluator_instructions=args.evaluator_instructions,
        # Safely access exam-specific args that might not exist for all formats
        exam_title=getattr(args, 'exam_title', None),
        exam_course=getattr(args, 'exam_course', None),
        exam_date=getattr(args, 'exam_date', None),
        exam_models=getattr(args, 'num_models', getattr(args, 'exam_models', 1)),
        language=getattr(args, 'lang', getattr(args, 'exam_language', config.DEFAULT_LANGUAGE)),
        # Safely access pexams-specific args
        font_size=getattr(args, 'font_size', "11pt"),
        columns=getattr(args, 'columns', 1),
        generate_fakes=getattr(args, 'generate_fakes', 0),
        generate_references=getattr(args, 'generate_references', False),
        total_students=getattr(args, 'total_students', 0),
        extra_model_templates=getattr(args, 'extra_model_templates', 0),
        keep_html=getattr(args, 'keep_html', False) or (hasattr(args, 'log_level') and args.log_level == 'DEBUG'),
        max_image_width=getattr(args, 'max_image_width', None),
        max_image_height=getattr(args, 'max_image_height', None),
        custom_header=getattr(args, 'custom_header', None)
    )

    # --- Save Updated Metadata ---
    artifacts.write_metadata_tsv(synced_records, tsv_path)
    print(f"Metadata file at '{tsv_path}' has been updated with manual review changes.")

def main():
    parser = argparse.ArgumentParser(
        description="AutoTestIA: A tool for semi-automatic generation of multiple-choice questions.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Parent Parser for common arguments ---
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--log-level",
                               default="INFO",
                               choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                               help="Set the logging verbosity.")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # --- Generate Command ---
    parser_generate = subparsers.add_parser("generate", help="Generate questions from a source.", parents=[common_parser])
    parser_generate.add_argument("input_material",
                                 nargs='*',
                                 default=[],
                                 help="Paths to the input material files (e.g., .txt, .pdf). Can be multiple. If omitted, generation relies on instructions.")
    parser_generate.add_argument("-o", "--output-md-path", default="generated/questions.md", help="Path to save the output markdown file. A .tsv file will be created alongside it.")
    parser_generate.add_argument("--generator-instructions", type=str, default=None, help="Custom instructions for the generator prompt.")
    parser_generate.add_argument("--reviewer-instructions", type=str, default=None, help="Custom instructions for the reviewer prompt.")
    parser_generate.add_argument("--evaluator-instructions", type=str, default=None, help="Custom instructions for the evaluator prompt.")
    parser_generate.add_argument("-i", "--images", nargs='+', help="Optional paths to image files.", default=[])
    parser_generate.add_argument("-n", "--num-questions", type=int, default=config.DEFAULT_NUM_QUESTIONS, help=f"Number of questions to generate from text (default: {config.DEFAULT_NUM_QUESTIONS}).")
    parser_generate.add_argument("--num-questions-per-image", type=int, default=1, help="Number of questions to generate per image (default: 1).")
    parser_generate.add_argument("--provider", choices=config.GENERATOR_MODEL_MAP.keys(), default=config.LLM_PROVIDER, help=f"LLM provider to use (default: {config.LLM_PROVIDER}).")
    parser_generate.add_argument("--generator-model", default=None, help="Specific model for the generator agent.")
    parser_generate.add_argument("--reviewer-model", default=None, help="Specific model for the reviewer agent.")
    parser_generate.add_argument("--evaluator-model", default=None, help="Specific model for the evaluator agent.")
    parser_generate.add_argument("--use-llm-review", action=argparse.BooleanOptionalAction, default=config.DEFAULT_LLM_REVIEW_ENABLED, help="Enable LLM-based review.")
    parser_generate.add_argument("--skip-manual-review", action='store_true', help="Skip the manual review step (not recommended with new workflow).")
    parser_generate.add_argument("--language", default=config.DEFAULT_LANGUAGE, help=f"Language for the questions (default: {config.DEFAULT_LANGUAGE}).")
    parser_generate.add_argument("--evaluate-initial", action="store_true", help="Run evaluator on questions after generation.")
    parser_generate.add_argument("--evaluate-reviewed", action="store_true", help="Run evaluator on questions after the review stage.")
    parser_generate.set_defaults(func=handle_generate)

    # --- Export Command ---
    # This parser is just a container for the format subparsers
    parser_export = subparsers.add_parser("export", help="Export questions to a specified format.")
    export_subparsers = parser_export.add_subparsers(dest="format", required=True, help="The output format.")

    # Parent parser for common export arguments
    export_common_parser = argparse.ArgumentParser(add_help=False)
    export_common_parser.add_argument("input_md_path", help="Path to the input questions.md file.")
    export_common_parser.add_argument("--shuffle-questions", type=int, metavar='SEED', nargs='?', const=random.randint(1, 10000), default=None, help="Shuffle question order.")
    export_common_parser.add_argument("--shuffle-answers", type=int, metavar='SEED', nargs='?', const=random.randint(1, 10000), default=0, help="Shuffle answer order.")
    export_common_parser.add_argument("--num-final-questions", type=int, help="Randomly select N questions.")
    export_common_parser.add_argument("--evaluate-final", action="store_true", help="Run evaluator on the final questions.")
    export_common_parser.add_argument("--evaluator-instructions", type=str, default=None, help="Custom instructions for the evaluator prompt.")
    export_common_parser.add_argument("--max-image-width", type=int, default=None, help="Maximum width for images in pixels.")
    export_common_parser.add_argument("--max-image-height", type=int, default=None, help="Maximum height for images in pixels.")
    
    # Parent parser for exam-specific arguments (pexams, rexams)
    exam_parser = argparse.ArgumentParser(add_help=False)
    exam_parser.add_argument("--exam-title", help="Custom title for the exam PDF.")
    exam_parser.add_argument("--exam-course", help="Custom course name for the exam PDF.")
    exam_parser.add_argument("--exam-date", help="Custom date for the exam PDF.")
    exam_parser.add_argument("--exam-models", type=int, default=1, help="Number of different exam versions to generate.")
    exam_parser.add_argument("--exam-language", default=config.DEFAULT_LANGUAGE, help="Language for the exam PDF.")

    # Create subparsers for each format, now inheriting common_parser
    export_subparsers.add_parser("moodle_xml", parents=[common_parser, export_common_parser], help="Export to Moodle XML format.")
    export_subparsers.add_parser("gift", parents=[common_parser, export_common_parser], help="Export to GIFT format.")
    export_subparsers.add_parser("wooclap", parents=[common_parser, export_common_parser], help="Export to Wooclap CSV format.")
    export_subparsers.add_parser("none", parents=[common_parser, export_common_parser], help="Run export pre-processing without creating a final file.")

    # Pexams subparser
    parser_pexams = export_subparsers.add_parser("pexams", parents=[common_parser, export_common_parser], help="Export to pexams PDF format.")
    parser_pexams.add_argument("--num-models", type=int, default=1, help="Number of different exam models to generate (default: 4).")
    parser_pexams.add_argument("--exam-title", default="Final Exam", help="Title of the exam (default: \"Final Exam\").")
    parser_pexams.add_argument("--exam-course", help="Course name for the exam (optional).")
    parser_pexams.add_argument("--exam-date", help="Date of the exam (optional).")
    parser_pexams.add_argument("--columns", type=int, default=1, choices=[1, 2, 3], help="Number of columns for the questions (1, 2, or 3; default: 1).")
    parser_pexams.add_argument("--font-size", default="10pt", help="Base font size for the exam (e.g., '10pt', '12px'; default: '10pt').")
    parser_pexams.add_argument("--total-students", type=int, default=0, help="Total number of students for mass PDF generation (default: 0).")
    parser_pexams.add_argument("--extra-model-templates", type=int, default=0, help="Number of extra template sheets (answer sheet only) to generate per model (default: 0).")
    parser_pexams.add_argument("--lang", default=config.DEFAULT_LANGUAGE, help="Language for the answer sheet labels (e.g., 'en', 'es'; default: 'en').")
    parser_pexams.add_argument("--keep-html", action="store_true", help="If set, keeps the intermediate HTML files used for PDF generation.")
    parser_pexams.add_argument("--generate-fakes", type=int, default=0, help="Generates a number of simulated scans with fake answers for testing the correction process (default: 0).")
    parser_pexams.add_argument("--generate-references", action="store_true", help="If set, generates a reference scan with the correct answers marked for each model.")
    parser_pexams.add_argument("--custom-header", help="Markdown string or path to a Markdown file to insert before the questions (e.g., instructions).")

    # Rexams subparser
    export_subparsers.add_parser("rexams", parents=[common_parser, export_common_parser, exam_parser], help="Export to R/exams format.")

    parser_export.set_defaults(func=handle_export)

    # --- Correct Command ---
    parser_correct = subparsers.add_parser("correct", help="Correct scanned exams using pexams and update metadata.", parents=[common_parser])
    parser_correct.add_argument("input_md_path", help="Path to the original questions.md file (to update statistics in metadata.tsv).")
    parser_correct.add_argument("--input-path", required=False, help="Path to the scanned PDF or folder of images.")
    parser_correct.add_argument("--exam-dir", required=True, help="Path to the directory containing exam models (JSONs).")
    parser_correct.add_argument("--output-dir", required=True, help="Directory to save correction results.")
    parser_correct.add_argument("--evaluate-final", action="store_true", help="Run evaluator on the questions if not already evaluated.")
    parser_correct.add_argument("--evaluator-instructions", type=str, default=None, help="Custom instructions for the evaluator prompt.")
    parser_correct.add_argument("--lang", default=config.DEFAULT_LANGUAGE, help="Language for evaluation.")
    
    # Pexams arguments
    parser_correct.add_argument("--void-questions", default=None, help="Comma-separated list of question numbers to void.")
    parser_correct.add_argument("--void-questions-nicely", default=None, help="Comma-separated list of question IDs to void nicely.")
    parser_correct.add_argument("--input-csv", help="Path to input CSV for filling marks.")
    parser_correct.add_argument("--id-column", help="Column name for student IDs.")
    parser_correct.add_argument("--mark-column", help="Column name for marks.")
    parser_correct.add_argument("--name-column", help="Column name for student names.")
    parser_correct.add_argument("--simplify-csv", action="store_true", help="Simplify the output CSV.")
    parser_correct.add_argument("--fuzzy-id-match", type=int, default=100, help="Fuzzy matching threshold (0-100).")
    parser_correct.add_argument("--penalty", type=float, default=0.0, help="Penalty for incorrect answers (positive float).")
    parser_correct.add_argument("--input-encoding", default="utf-8", help="Encoding of input CSV.")
    parser_correct.add_argument("--input-sep", default=",", help="Separator for input CSV.")
    parser_correct.add_argument("--output-decimal-sep", default=".", help="Decimal separator for output marks.")
    parser_correct.add_argument("--only-analysis", action="store_true", help="Skip image processing and run analysis on existing results.")
    parser_correct.set_defaults(func=handle_correct)

    # --- Evaluate Command ---
    parser_evaluate = subparsers.add_parser("evaluate", help="Run evaluator on questions.", parents=[common_parser])
    parser_evaluate.add_argument("input_md_path", help="Path to the questions.md file.")
    parser_evaluate.add_argument("--stages", nargs='+', choices=['generated', 'reviewed', 'final'], default=['generated', 'reviewed', 'final'], help="Stages to evaluate.")
    parser_evaluate.add_argument("--evaluator-instructions", type=str, default=None, help="Custom instructions for the evaluator prompt.")
    parser_evaluate.add_argument("--language", default=config.DEFAULT_LANGUAGE, help="Language for evaluation.")
    parser_evaluate.add_argument("--missing-only", action="store_true", help="Only evaluate questions missing an evaluation.")
    parser_evaluate.set_defaults(func=handle_evaluate)


    # --- Split Command ---
    parser_split = subparsers.add_parser("split", help="Split a test into multiple parts.", parents=[common_parser])
    parser_split.add_argument("input_md_path", help="Path to the input questions.md file to split.")
    parser_split.add_argument("--splits",
                              nargs='+',
                              type=str,
                              required=True,
                              help="A list of integers (number of questions) or floats (proportion) defining the splits.")
    parser_split.add_argument("--output-dir", help="Directory to save the split files (optional, defaults to the input file's directory).")
    parser_split.add_argument("--shuffle-questions",
                              type=int,
                              metavar='SEED',
                              nargs='?',
                              const=random.randint(1, 10000),
                              default=None,
                              help="Shuffle questions before splitting. Provide an optional seed.")
    parser_split.set_defaults(func=handle_split_command)

    # --- Merge Command ---
    parser_merge = subparsers.add_parser("merge", help="Merge multiple tests into one.", parents=[common_parser])
    parser_merge.add_argument("input_md_paths", nargs='+', help="List of paths to the input questions.md files to merge.")
    parser_merge.add_argument("-o", "--output-md-path", required=True, help="Path to save the merged output markdown file.")
    parser_merge.set_defaults(func=handle_merge_command)

    # --- Shuffle Command ---
    parser_shuffle = subparsers.add_parser("shuffle", help="Shuffle questions in a markdown file in-place.", parents=[common_parser])
    parser_shuffle.add_argument("input_md_file", help="Path to the markdown file to shuffle.")
    parser_shuffle.add_argument("--seed", type=int, help="Optional integer seed for reproducible shuffling.")
    parser_shuffle.add_argument("-y", "--yes", action="store_true", help="Bypass the confirmation prompt and overwrite the file directly.")
    parser_shuffle.set_defaults(func=handle_shuffle_command)
    
    # --- Test Command ---
    parser_test = subparsers.add_parser("test", help="Run a full pipeline test to check for runtime errors.", parents=[common_parser])
    parser_test.set_defaults(func=handle_test)

    args = parser.parse_args()
    setup_logging(args.log_level) # Setup logging right after parsing args

    if hasattr(args, 'func'):
        try:
            args.func(args)
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}", exc_info=True)
            print(f"\n--- Error ---\nAn unexpected error occurred: {e}")
            # print traceback
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main() 