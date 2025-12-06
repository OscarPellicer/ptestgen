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
from autotestia.correct import handle_correct_command
from autotestia.shuffle import handle_shuffle_command


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
            evaluate_initial=True, evaluate_reviewed=True
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
            evaluate_initial=True, evaluate_reviewed=True
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
            'exam_date': '2025-01-01', 'exam_models': 1, 'language': 'en',
            'font_size': '11pt', 'pexams_columns': 2, 'pexams_id_length': 10,
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
            'exam_generate_fakes': 1,
            'exam_generate_references': True,
            'pexams_columns': 2,
            'pexams_font_size': '10pt',
            'pexams_id_length': 10,
        })
        args_export_pexams = argparse.Namespace(format='pexams', **pexams_export_args)
        handle_export(args_export_pexams)

        # --- 7. Correct ---
        print("\n--- Step 7: Correcting pexams scans ---")
        base_name = os.path.splitext(os.path.basename(merged_md_path))[0]
        pexams_output_dir = os.path.join(output_dir, f"{base_name}_pexams_output")
        simulated_scans_dir = os.path.join(pexams_output_dir, "simulated_scans")
        correction_dir = os.path.join(pexams_output_dir, "correction_results")
        
        if os.path.exists(simulated_scans_dir):
            args_correct = argparse.Namespace(
                correct_type='pexams',
                input_path=simulated_scans_dir,
                exam_dir=pexams_output_dir,
                output_dir=correction_dir,
                void_questions=None
            )
            handle_correct_command(args_correct)
        else:
            print(f"Could not find simulated scans directory: {simulated_scans_dir}. Skipping correction.")
        
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
        input_material_path=args.input_material,
        image_paths=args.images,
        output_md_path=md_path,
        output_tsv_path=tsv_path,
        num_questions=args.num_questions,
        language=args.language,
        generator_instructions=args.generator_instructions,
        reviewer_instructions=args.reviewer_instructions,
        evaluator_instructions=args.evaluator_instructions,
        evaluate_initial=args.evaluate_initial,
        evaluate_reviewed=args.evaluate_reviewed
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
        exam_models=getattr(args, 'exam_models', 1),
        language=getattr(args, 'exam_language', config.DEFAULT_LANGUAGE),
        # Safely access pexams-specific args
        font_size=getattr(args, 'exam_font_size', "11pt"),
        columns=getattr(args, 'exam_columns', 1),
        id_length=getattr(args, 'exam_id_length', 10),
        generate_fakes=getattr(args, 'exam_generate_fakes', 0),
        generate_references=getattr(args, 'exam_generate_references', False),
        max_image_width=getattr(args, 'max_image_width', None),
        max_image_height=getattr(args, 'max_image_height', None)
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
                                 nargs='?',
                                 default=None,
                                 help="Path to the input material file (e.g., .txt, .pdf). If omitted, generation relies on instructions.")
    parser_generate.add_argument("-o", "--output-md-path", default="generated/questions.md", help="Path to save the output markdown file. A .tsv file will be created alongside it.")
    parser_generate.add_argument("--generator-instructions", type=str, default=None, help="Custom instructions for the generator prompt.")
    parser_generate.add_argument("--reviewer-instructions", type=str, default=None, help="Custom instructions for the reviewer prompt.")
    parser_generate.add_argument("--evaluator-instructions", type=str, default=None, help="Custom instructions for the evaluator prompt.")
    parser_generate.add_argument("-i", "--images", nargs='+', help="Optional paths to image files.", default=[])
    parser_generate.add_argument("-n", "--num-questions", type=int, default=config.DEFAULT_NUM_QUESTIONS, help=f"Number of questions to generate (default: {config.DEFAULT_NUM_QUESTIONS}).")
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
    parser_pexams = export_subparsers.add_parser("pexams", parents=[common_parser, export_common_parser, exam_parser], help="Export to pexams PDF format.")
    parser_pexams.add_argument("--exam-font-size", default="11pt", help="Font size for pexams PDF.")
    parser_pexams.add_argument("--exam-columns", type=int, default=1, choices=[1, 2], help="Number of columns for questions.")
    parser_pexams.add_argument("--exam-id-length", type=int, default=10, help="Number of boxes for the student ID grid.")
    parser_pexams.add_argument("--exam-generate-fakes", type=int, default=0, help="Generate N simulated scans with fake answers.")
    parser_pexams.add_argument("--exam-generate-references", action="store_true", help="Generate a reference scan with correct answers.")

    # Rexams subparser
    export_subparsers.add_parser("rexams", parents=[common_parser, export_common_parser, exam_parser], help="[DEPRECATED] Export to R/exams format.")

    parser_export.set_defaults(func=handle_export)

    # --- Correct Command ---
    # This parser is just a container for the type subparsers
    parser_correct = subparsers.add_parser("correct", help="Correct exams.")
    correct_subparsers = parser_correct.add_subparsers(dest="correct_type", required=True, help="The type of exam to correct.")

    # PEXAMS correct subparser
    parser_pexams_correct = correct_subparsers.add_parser("pexams", parents=[common_parser], help="Correct a pexam.")
    parser_pexams_correct.add_argument("--input-path", required=True, help="Path to the scanned PDF or a folder of scanned images.")
    parser_pexams_correct.add_argument("--exam-dir", required=True, help="Path to the generated pexams output directory.")
    parser_pexams_correct.add_argument("--output-dir", required=True, help="Directory to save correction results.")
    parser_pexams_correct.add_argument("--void-questions", type=str, help="Comma-separated list of question numbers to void.")
    
    # REXAMS correct subparser
    parser_rexams_correct = correct_subparsers.add_parser("rexams", parents=[common_parser], help="Correct an R/exams scan.")
    parser_rexams_correct.add_argument("--all-scans-pdf", required=True, help="Path to the single PDF containing all scanned exam sheets.")
    parser_rexams_correct.add_argument("--student-info-csv", type=str, required=True, help="Path to the input CSV with student information.")
    parser_rexams_correct.add_argument("--solutions-rds", type=str, required=True, help="Path to the exam.rds file from R/exams.")
    parser_rexams_correct.add_argument("--output-path", type=str, required=True, help="Main directory for all outputs.")
    parser_rexams_correct.add_argument("--r-executable", type=str, default=None, help="Path to Rscript.")
    parser_rexams_correct.add_argument("--exam-language", type=str, default="en", help="Language for nops_eval.")
    parser_rexams_correct.add_argument("--scan-thresholds", type=str, default="0.04,0.42", help="Scan thresholds for nops_scan.")
    parser_rexams_correct.add_argument("--partial-eval", action=argparse.BooleanOptionalAction, default=True, help="Enable partial scoring.")
    parser_rexams_correct.add_argument("--negative-points", type=float, default=-1/3, help="Penalty for incorrect answers.")
    parser_rexams_correct.add_argument("--max-score", type=float, default=None, help="Maximum raw score.")
    parser_rexams_correct.add_argument("--scale-mark-to", type=float, default=10.0, help="Target score for scaling.")
    parser_rexams_correct.add_argument("--python-split", action=argparse.BooleanOptionalAction, default=False, dest="split_pages_python_control")
    parser_rexams_correct.add_argument("--python-rotate", action=argparse.BooleanOptionalAction, default=False, dest="python_rotate_control")
    parser_rexams_correct.add_argument("--python-bw-threshold", type=int, default=97)
    parser_rexams_correct.add_argument("--force-overwrite", action="store_true", default=False)
    parser_rexams_correct.add_argument("--student-csv-id-col", type=str, default="ID.Usuario")
    parser_rexams_correct.add_argument("--student-csv-reg-col", type=str, default="Número.de.Identificación")
    parser_rexams_correct.add_argument("--student-csv-name-col", type=str, default="Nombre")
    parser_rexams_correct.add_argument("--student-csv-surname-col", type=str, default="Apellidos")
    parser_rexams_correct.add_argument("--student-csv-encoding", type=str, default="UTF-8")
    parser_rexams_correct.add_argument("--registration-format", type=str, default="%08s")
    parser_rexams_correct.add_argument("--void-questions", type=str, default=None)
    parser_rexams_correct.add_argument("--void-questions-nicely", type=str, default=None)
    # Add other rexams-specific arguments here

    parser_correct.set_defaults(func=handle_correct_command)

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