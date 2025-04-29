import argparse
import os
import sys
from dotenv import load_dotenv
import logging # Import logging

# Load .env file BEFORE importing config or pipeline
# This ensures environment variables are set when config is loaded
load_dotenv()

# Now import local modules
from autotestia.pipeline import AutoTestIAPipeline
from autotestia import config # Import config AFTER dotenv load

def main():
    parser = argparse.ArgumentParser(description="AutoTestIA: Generate quizzes from materials using LLMs.")

    # --- Input Arguments ---
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("input_material",
                             nargs='?', # Make optional within the group
                             help="Path to the input material file (e.g., .txt, .pdf) for new generation.")
    input_group.add_argument("--resume-from-md",
                             help="Path to an existing intermediate Markdown file to resume processing from (skips generation steps 1-4).")

    # --- Other Arguments ---
    parser.add_argument("-i", "--images",
                        nargs='+',
                        help="Optional paths to image files for image-based questions (used only with 'input_material').",
                        default=[])
    parser.add_argument("-n", "--num-questions",
                        type=int,
                        default=config.DEFAULT_NUM_QUESTIONS,
                        help=f"Number of questions to generate from text (default: {config.DEFAULT_NUM_QUESTIONS}, used only with 'input_material').")
    parser.add_argument("-o", "--output-md",
                        default=config.DEFAULT_OUTPUT_MD_FILE,
                        help=f"Path for the intermediate Markdown file (default: {config.DEFAULT_OUTPUT_MD_FILE}). If resuming, this argument is ignored.")
    parser.add_argument("-f", "--formats",
                        nargs='+',
                        choices=['moodle_xml', 'gift', 'wooclap', 'rexams', 'none'], # Added 'none'
                        default=['moodle_xml', 'gift'],
                        help="List of final output formats. Use 'none' to only generate the intermediate Markdown (default: moodle_xml gift).")
    parser.add_argument("--provider",
                        choices=config.GENERATOR_MODEL_MAP.keys(), # Use keys from config map
                        default=config.LLM_PROVIDER,
                        help=f"LLM provider to use (default: {config.LLM_PROVIDER} from env or config, used only with 'input_material').")
    parser.add_argument("--generator-model",
                         default=None, # Default is None, pipeline will use config default for provider
                         help="Specific model name for the generator agent (overrides default for provider, used only with 'input_material').")
    parser.add_argument("--reviewer-model",
                         default=None, # Default is None, pipeline will use config default for provider
                         help="Specific model name for the reviewer agent (overrides default for provider, used only with 'input_material').")
    parser.add_argument("--use-llm-review",
                        action=argparse.BooleanOptionalAction, # Creates --use-llm-review / --no-use-llm-review
                        default=config.DEFAULT_LLM_REVIEW_ENABLED,
                        help="Enable LLM-based review agent (default: set in config/env, used only with 'input_material').")
    parser.add_argument("--skip-manual-review",
                         action='store_true',
                         help="Skip the manual review step (used only with 'input_material').")
    parser.add_argument("--extract-doc-images",
                         action='store_true',
                         help="[Experimental] Attempt to extract images from input documents (used only with 'input_material').")
    parser.add_argument("--language",
                         default=config.DEFAULT_LANGUAGE,
                         help=f"Language for the questions (default: {config.DEFAULT_LANGUAGE}, used only with 'input_material').")

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
    if args.resume_from_md:
        logging.info(f"Resuming pipeline from Markdown file: {args.resume_from_md}")
        # When resuming, several arguments related to generation are ignored
        if args.images:
            logging.warning("--images argument ignored when using --resume-from-md")
        if args.num_questions != config.DEFAULT_NUM_QUESTIONS:
            logging.warning("--num-questions argument ignored when using --resume-from-md")
        # output_md is ignored, the input is the resume file
        # provider, models, llm_review, skip_manual_review, extract_doc_images, language are ignored
        if args.provider != config.LLM_PROVIDER:
            logging.warning("--provider argument ignored when using --resume-from-md")
        if args.generator_model:
            logging.warning("--generator-model argument ignored when using --resume-from-md")
        if args.reviewer_model:
             logging.warning("--reviewer-model argument ignored when using --resume-from-md")
        if args.use_llm_review != config.DEFAULT_LLM_REVIEW_ENABLED:
             logging.warning("--use-llm-review argument ignored when using --resume-from-md")
        if args.skip_manual_review:
             logging.warning("--skip-manual-review argument ignored when using --resume-from-md")
        if args.extract_doc_images:
             logging.warning("--extract-doc-images argument ignored when using --resume-from-md")
        if args.language != config.DEFAULT_LANGUAGE:
             logging.warning("--language argument ignored when using --resume-from-md")

        input_md_path = args.resume_from_md
        # Ensure the resume file exists
        if not os.path.exists(input_md_path):
            print(f"Error: Resume Markdown file not found: {input_md_path}", file=sys.stderr)
            sys.exit(1)
        # Clear generation-specific args for the pipeline call
        args.input_material = None
        args.images = []
        args.output_md = None # We use input_md_path for the pipeline resume step
        # Reset generation/review specific args to defaults or None as they aren't used
        config_override = {} # No config override needed for generation when resuming
        effective_provider = config.LLM_PROVIDER # Not relevant for resume
        # API key checks are not needed when resuming

    else: # Running generation from input material
        input_md_path = None # Not resuming
        # Use the provided output_md path
        output_md_path = args.output_md
        logging.info(f"Starting new generation from: {args.input_material}")
        logging.info(f"Intermediate Markdown will be saved to: {output_md_path}")

        # Ensure output directory exists for the markdown file
        output_md_dir = os.path.dirname(output_md_path)
        if output_md_dir:
            os.makedirs(output_md_dir, exist_ok=True)
        else:
             # Handle case where args.output_md is just a filename -> use current dir
             output_md_dir = "."

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
        # If resuming, config_override might be empty or only contain non-generation related overrides if any exist in future
        pipeline = AutoTestIAPipeline(config_override=config_override if config_override else None)

        pipeline.run(
            input_material_path=args.input_material, # Will be None if resuming
            image_paths=args.images,                 # Will be empty if resuming
            output_md_path=args.output_md,           # Will be None if resuming, used for output if generating
            resume_md_path=input_md_path,            # Pass the path to resume from, or None
            output_formats=args.formats,
            num_questions=args.num_questions,        # Ignored by pipeline if resuming
            extract_images_from_doc=args.extract_doc_images, # Ignored by pipeline if resuming
            skip_manual_review=args.skip_manual_review, # Ignored by pipeline if resuming
            language=args.language,                   # Ignored by pipeline if resuming
            use_llm_review=effective_llm_review if not args.resume_from_md else None # Pass LLM review flag only if generating
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
    main() 