import argparse
import os
import sys
from dotenv import load_dotenv
import logging # Import logging
import random # Add random import

# Load .env file BEFORE importing config or pipeline
# This ensures environment variables are set when config is loaded
load_dotenv()

# Now import local modules
from autotestia.pipeline import AutoTestIAPipeline
from autotestia import config # Import config AFTER dotenv load

def main():
    parser = argparse.ArgumentParser(description="AutoTestIA: Generate quizzes from materials using LLMs.")

    # --- Input Arguments ---
    parser.add_argument("input_material",
                             nargs='?', # Make optional
                             default=None, # Default to None if not provided
                             help="Path to the input material file (e.g., .txt, .pdf). If omitted, generation relies on instructions.")
    parser.add_argument("--resume-from-md",
                             default=None, # Default to None
                             help="Path to an existing intermediate Markdown file to resume processing from (skips generation steps 1-4).")

    # --- Custom Instructions ---
    parser.add_argument("--generator-instructions",
                        type=str,
                        default=None,
                        help="Custom instructions to add to the generator prompt.")
    parser.add_argument("--reviewer-instructions",
                        type=str,
                        default=None,
                        help="Custom instructions to add to the reviewer prompt.")

    # --- Other Arguments ---
    parser.add_argument("-i", "--images",
                        nargs='+',
                        help="Optional paths to image files for image-based questions.",
                        default=[])
    parser.add_argument("-n", "--num-questions",
                        type=int,
                        default=config.DEFAULT_NUM_QUESTIONS,
                        help=f"Number of questions to generate (default: {config.DEFAULT_NUM_QUESTIONS}).")
    parser.add_argument("-o", "--output-md",
                        default=config.DEFAULT_OUTPUT_MD_FILE,
                        help=f"Path for the intermediate Markdown file (default: {config.DEFAULT_OUTPUT_MD_FILE}). Ignored if resuming.")
    parser.add_argument("-f", "--formats",
                        nargs='+',
                        choices=['moodle_xml', 'gift', 'wooclap', 'rexams', 'none'], # Added 'none'
                        default=['moodle_xml', 'gift'],
                        help="List of final output formats. Use 'none' to only generate the intermediate Markdown (default: moodle_xml gift).")
    parser.add_argument("--provider",
                        choices=config.GENERATOR_MODEL_MAP.keys(), # Use keys from config map
                        default=config.LLM_PROVIDER,
                        help=f"LLM provider to use (default: {config.LLM_PROVIDER} from env or config).")
    parser.add_argument("--generator-model",
                         default=None, # Default is None, pipeline will use config default for provider
                         help="Specific model name for the generator agent (overrides default for provider).")
    parser.add_argument("--reviewer-model",
                         default=None, # Default is None, pipeline will use config default for provider
                         help="Specific model name for the reviewer agent (overrides default for provider).")
    parser.add_argument("--use-llm-review",
                        action=argparse.BooleanOptionalAction, # Creates --use-llm-review / --no-use-llm-review
                        default=config.DEFAULT_LLM_REVIEW_ENABLED,
                        help="Enable LLM-based review agent (default: set in config/env).")
    parser.add_argument("--skip-manual-review",
                         action='store_true',
                         help="Skip the manual review step.")
    parser.add_argument("--extract-doc-images",
                         action='store_true',
                         help="[Experimental] Attempt to extract images from input documents (requires 'input_material').")
    parser.add_argument("--language",
                         default=config.DEFAULT_LANGUAGE,
                         help=f"Language for the questions (default: {config.DEFAULT_LANGUAGE}).")

    # --- Shuffling and Selection Arguments ---
    parser.add_argument("--shuffle-questions",
                         type=int,
                         metavar='SEED',
                         nargs='?', # Make the value optional
                         const=random.randint(1, 10000), # Use a random seed if flag is present without value
                         default=None, # No shuffling if flag is absent
                         help="Shuffle the order of questions after parsing the final Markdown. Provide an optional integer seed for reproducibility.")
    parser.add_argument("--shuffle-answers",
                         type=int,
                         metavar='SEED',
                         nargs='?', # Make the value optional
                         const=random.randint(1, 10000), # Use a random seed if flag is present without value
                         default=0, # Default behavior: shuffle answers (seed 0 indicates random shuffle per run)
                         help="Shuffle the order of answers (correct + distractors) within each question. Provide an optional integer seed for reproducibility. If omitted or provided without a value, answers are shuffled randomly.")
    parser.add_argument("--num-final-questions",
                        type=int,
                        default=None, # Default: use all questions
                        help="Select a specific number of questions randomly from the final set (after potential question shuffling).")

    # --- R/exams Specific Arguments ---
    parser.add_argument("--rexams-title",
                        type=str,
                        default=None,
                        help="Custom title for R/exams PDF output. If not set, uses R script's default.")
    parser.add_argument("--rexams-course",
                        type=str,
                        default=None,
                        help="Custom course name for R/exams PDF output. If not set, uses R script's default.")

    # --- Logging Argument ---
    parser.add_argument("--log-level",
                         default='WARNING', # Default to WARNING
                         choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                         help="Set the logging level (default: WARNING).")

    args = parser.parse_args()

    # --- Configure Logging --- Must happen early!
    log_level_name = args.log_level.upper()
    logging.basicConfig(level=log_level_name,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logging.info(f"Logging level set to: {log_level_name}")

    # --- Argument Validation and Processing ---

    # Mutual Exclusivity Check
    if args.input_material and args.resume_from_md:
        print("Error: Cannot specify both 'input_material' and '--resume-from-md'.", file=sys.stderr)
        sys.exit(1)

    # Determine mode: Resume, Generate from file, or Generate from instructions
    mode = None
    if args.resume_from_md:
        mode = "resume"
        logging.info(f"Mode: Resuming pipeline from Markdown file: {args.resume_from_md}")
    elif args.input_material:
        mode = "generate_from_file"
        logging.info(f"Mode: Starting new generation from file: {args.input_material}")
    else:
        mode = "generate_from_instructions"
        logging.info("Mode: Starting new generation from instructions (no input file).")
        if not args.generator_instructions:
            logging.warning("Generating without an input file or specific generator instructions. Relying on default prompts.")
            print("Warning: No input file or --generator-instructions provided. Generation might be generic.", file=sys.stderr)

    # --- Mode-Specific Logic and Warnings ---

    input_md_path = None
    output_md_path = args.output_md # Default output path
    config_override = {}
    effective_provider = args.provider # Assume provider might be needed even without input file
    effective_generator_model = None
    effective_reviewer_model = None
    effective_llm_review = args.use_llm_review
    # Carry over shuffle/selection arguments regardless of mode
    shuffle_questions_seed = args.shuffle_questions
    shuffle_answers_seed = args.shuffle_answers
    num_final_questions = args.num_final_questions

    if mode == "resume":
        input_md_path = args.resume_from_md
        output_md_path = None # Output MD path is irrelevant when resuming

        # Ensure the resume file exists
        if not os.path.exists(input_md_path):
            print(f"Error: Resume Markdown file not found: {input_md_path}", file=sys.stderr)
            sys.exit(1)

        # Warn about ignored arguments
        ignored_args_resume = []
        if args.input_material: ignored_args_resume.append("input_material") # Should be caught earlier, but belt-and-suspenders
        if args.images: ignored_args_resume.append("--images")
        if args.num_questions != config.DEFAULT_NUM_QUESTIONS: ignored_args_resume.append("--num-questions")
        if args.output_md != config.DEFAULT_OUTPUT_MD_FILE: ignored_args_resume.append("--output-md") # This specific value is ignored
        if args.provider != config.LLM_PROVIDER: ignored_args_resume.append("--provider")
        if args.generator_model: ignored_args_resume.append("--generator-model")
        if args.reviewer_model: ignored_args_resume.append("--reviewer-model")
        if args.use_llm_review != config.DEFAULT_LLM_REVIEW_ENABLED: ignored_args_resume.append("--use-llm-review")
        if args.skip_manual_review: ignored_args_resume.append("--skip-manual-review") # Manual review choice happens *before* resume point
        if args.extract_doc_images: ignored_args_resume.append("--extract-doc-images")
        if args.language != config.DEFAULT_LANGUAGE: ignored_args_resume.append("--language")
        if args.generator_instructions: ignored_args_resume.append("--generator-instructions")
        if args.reviewer_instructions: ignored_args_resume.append("--reviewer-instructions")
        # Shuffle/select args are NOT ignored

        if ignored_args_resume:
            logging.warning(f"The following arguments are ignored when using --resume-from-md: {', '.join(ignored_args_resume)}")

        # Reset generation-specific args for the pipeline call
        args.input_material = None
        args.images = []
        args.output_md = None
        # Reset generation/review specific args to defaults or None as they aren't used
        config_override = {} # No config override needed for generation when resuming
        effective_provider = config.LLM_PROVIDER # Not relevant for resume
        # API key checks are not needed when resuming

    else: # Generate from file OR instructions
        input_md_path = None # Not resuming
        # Use the provided output_md path
        logging.info(f"Intermediate Markdown will be saved to: {output_md_path}")

        # Ensure output directory exists for the markdown file
        output_md_dir = os.path.dirname(output_md_path)
        if output_md_dir:
            os.makedirs(output_md_dir, exist_ok=True)
        else:
             # Handle case where args.output_md is just a filename -> use current dir
             output_md_dir = "."

        # Validate arguments incompatible with "generate_from_instructions" mode
        if mode == "generate_from_instructions":
            ignored_args_instr = []
            if args.extract_doc_images: ignored_args_instr.append("--extract-doc-images")
            # Keep images? Might want image questions without text context.
            # Keep language? Might want to specify language for generation.
            # Keep num_questions? Yes.
            if ignored_args_instr:
                 logging.warning(f"The following arguments are ignored when no 'input_material' is provided: {', '.join(ignored_args_instr)}")
                 args.extract_doc_images = False # Force disable

        # Determine the final configuration values based on config and CLI args
        effective_provider = args.provider
        effective_generator_model = config.GENERATOR_MODEL_MAP.get(effective_provider)
        effective_reviewer_model = config.REVIEWER_MODEL_MAP.get(effective_provider)
        effective_llm_review = args.use_llm_review

        # Override models only if explicitly provided via CLI
        if args.generator_model:
            effective_generator_model = args.generator_model
        if args.reviewer_model:
            effective_reviewer_model = args.reviewer_model

        # Construct the config override dictionary for the pipeline
        config_override = {}
        if effective_provider != config.LLM_PROVIDER:
            config_override["llm_provider"] = effective_provider

        # Always include models in override if provider changed OR if model was explicitly set
        if effective_provider != config.LLM_PROVIDER or args.generator_model:
             if effective_generator_model:
                  config_override["generator_model"] = effective_generator_model
             else: # Handle case where provider has no default in map
                 print(f"Warning: No default generator model found for provider '{effective_provider}'. Using stub.", file=sys.stderr)
                 config_override["generator_model"] = "stub-generator-model" # Keep stub logic

        if effective_provider != config.LLM_PROVIDER or args.reviewer_model:
             if effective_reviewer_model:
                 config_override["reviewer_model"] = effective_reviewer_model
             else: # Handle case where provider has no default in map
                 print(f"Warning: No default reviewer model found for provider '{effective_provider}'. Using stub.", file=sys.stderr)
                 config_override["reviewer_model"] = "stub-reviewer-model" # Keep stub logic

        # Override review flag if explicitly set via CLI
        if args.use_llm_review != config.DEFAULT_LLM_REVIEW_ENABLED:
             config_override["use_llm_review"] = effective_llm_review

        # Check for API keys ONLY IF a non-stub provider is selected
        selected_provider = effective_provider
        if selected_provider != "stub":
            api_key_missing = False
            if selected_provider == "openai" and not config.OPENAI_API_KEY:
                print("Error: OpenAI provider selected, but OPENAI_API_KEY not found in .env or environment variables.", file=sys.stderr)
                api_key_missing = True
            elif selected_provider == "google" and not config.GOOGLE_API_KEY:
                print("Error: Google provider selected, but GOOGLE_API_KEY not found in .env or environment variables.", file=sys.stderr)
                api_key_missing = True
            elif selected_provider == "anthropic" and not config.ANTHROPIC_API_KEY:
                 print("Error: Anthropic provider selected, but ANTHROPIC_API_KEY not found in .env or environment variables.", file=sys.stderr)
                 api_key_missing = True
            elif selected_provider == "replicate" and not config.REPLICATE_API_TOKEN:
                 print("Error: Replicate provider selected, but REPLICATE_API_TOKEN not found in .env or environment variables.", file=sys.stderr)
                 api_key_missing = True

            if api_key_missing:
                print("Please create a .env file (from .env.example) and add the required API key.", file=sys.stderr)
                sys.exit(1) # Exit if key is missing for selected provider

    # --- Run Pipeline ---
    try:
        # Pass relevant args to pipeline constructor or run method
        # If resuming, config_override might be empty
        pipeline = AutoTestIAPipeline(config_override=config_override if config_override else None)

        pipeline.run(
            input_material_path=args.input_material, # None if resuming or generating from instructions
            image_paths=args.images,                 # Used unless resuming
            output_md_path=output_md_path,           # None if resuming
            resume_md_path=input_md_path,            # Path to resume from, or None
            output_formats=args.formats,
            num_questions=args.num_questions,        # Used unless resuming
            extract_images_from_doc=args.extract_doc_images, # Used only if input_material provided
            skip_manual_review=args.skip_manual_review, # Used unless resuming
            language=args.language,                   # Used unless resuming
            use_llm_review=effective_llm_review if mode != "resume" else None, # Pass LLM review flag only if generating
            # Pass custom instructions (will be None if not provided)
            generator_instructions=args.generator_instructions if mode != "resume" else None,
            reviewer_instructions=args.reviewer_instructions if mode != "resume" else None,
            # Pass shuffling and selection arguments
            shuffle_questions_seed=shuffle_questions_seed,
            shuffle_answers_seed=shuffle_answers_seed,
            num_final_questions=num_final_questions,
            # R/exams specific
            rexams_title=args.rexams_title,
            rexams_course=args.rexams_course
        )
    except Exception as e:
        logging.error(f"Pipeline execution failed: {e}", exc_info=True) # Log with traceback
        print(f"\n--- Pipeline Error ---", file=sys.stderr)
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        # Add more detailed error logging here if needed
        import traceback
        traceback.print_exc(file=sys.stderr) # Print traceback to stderr
        sys.exit(1)


if __name__ == "__main__":
    # Example usage:
    # Assuming 'all.md' exists in the 'output' directory:
    # python main.py --resume-from-md output/all.md --formats wooclap --shuffle-questions 42 --shuffle-answers 42 --num-final-questions 10 -o output/ignored_but_needed_placeholder.md
    # Note: -o is technically ignored in resume mode but might be required by argparse depending on setup.
    #       The actual output CSV will be named based on the input MD: output/all_wooclap.csv
    # To get output/all_subset.csv, you might need to rename manually or adjust the pipeline's output naming logic.
    # For now, the output name derives from the source MD.

    # Example generate, shuffle, select, wooclap only:
    # python main.py input.txt -n 20 --formats wooclap --shuffle-questions 123 --shuffle-answers 123 --num-final-questions 10 -o output/subset_questions.md
    main() 