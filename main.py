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

    parser.add_argument("input_material",
                        help="Path to the input material file (e.g., .txt, .pdf).")
    parser.add_argument("-i", "--images",
                        nargs='+',
                        help="Optional paths to image files for image-based questions.",
                        default=[])
    parser.add_argument("-n", "--num-questions",
                        type=int,
                        default=config.DEFAULT_NUM_QUESTIONS,
                        help=f"Number of questions to generate from text (default: {config.DEFAULT_NUM_QUESTIONS}).")
    parser.add_argument("-o", "--output-md",
                        default=config.DEFAULT_OUTPUT_MD_FILE,
                        help=f"Path for the intermediate Markdown file (default: {config.DEFAULT_OUTPUT_MD_FILE}).")
    parser.add_argument("-f", "--formats",
                        nargs='+',
                        choices=['moodle_xml', 'gift', 'wooclap', 'rexams'],
                        default=['moodle_xml', 'gift'],
                        help="List of final output formats (default: moodle_xml gift).")
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
                         help="Skip the manual review step and convert directly after auto-review.")
    parser.add_argument("--extract-doc-images",
                         action='store_true',
                         help="[Experimental] Attempt to extract images from input documents (PDF, DOCX, etc.) for processing (feature incomplete).")
    parser.add_argument("--language",
                         default=config.DEFAULT_LANGUAGE,
                         help=f"Language for the questions (default: {config.DEFAULT_LANGUAGE}).")

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
    # Include values only if they differ from the initial config state
    # or if they were explicitly set by args that don't have a direct config equivalent (like model names when provider changes)
    config_override = {}
    if effective_provider != config.LLM_PROVIDER:
        config_override["llm_provider"] = effective_provider

    # Always include models in override if provider changed OR if model was explicitly set
    if effective_provider != config.LLM_PROVIDER or args.generator_model:
         if effective_generator_model:
              config_override["generator_model"] = effective_generator_model
         else: # Handle case where provider has no default in map
             print(f"Warning: No default generator model found for provider '{effective_provider}'. Using stub.", file=sys.stderr)
             config_override["generator_model"] = "stub-generator-model"

    if effective_provider != config.LLM_PROVIDER or args.reviewer_model:
         if effective_reviewer_model:
             config_override["reviewer_model"] = effective_reviewer_model
         else: # Handle case where provider has no default in map
             print(f"Warning: No default reviewer model found for provider '{effective_provider}'. Using stub.", file=sys.stderr)
             config_override["reviewer_model"] = "stub-reviewer-model"

    # Override review flag if explicitly set via CLI (value is determined by args.use_llm_review directly)
    if args.use_llm_review != config.DEFAULT_LLM_REVIEW_ENABLED:
         config_override["use_llm_review"] = effective_llm_review


    # Ensure output directory exists for the markdown file
    output_md_dir = os.path.dirname(args.output_md)
    if output_md_dir:
        os.makedirs(output_md_dir, exist_ok=True)
    else:
         # Handle case where args.output_md is just a filename -> use current dir
         output_md_dir = "."


    # Check for API keys ONLY IF a non-stub provider is selected
    # Use the final effective provider for this check
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


    # Initialize and run the pipeline
    try:
        pipeline = AutoTestIAPipeline(config_override=config_override if config_override else None)

        pipeline.run(
            input_material_path=args.input_material,
            image_paths=args.images,
            output_md_path=args.output_md,
            output_formats=args.formats,
            num_questions=args.num_questions,
            extract_images_from_doc=args.extract_doc_images,
            skip_manual_review=args.skip_manual_review,
            language=args.language
        )
    except Exception as e:
        print(f"\n--- Pipeline Error ---", file=sys.stderr)
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        # Add more detailed error logging here if needed
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 