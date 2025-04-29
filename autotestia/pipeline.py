import os
from typing import List, Optional
import logging # Import logging
import sys # Import sys for stderr

from . import config
from .schemas import Question
from .input_parser import parser
from .agents.generator import QuestionGenerator
from .agents.reviewer import QuestionReviewer
from .output_formatter import markdown_writer, converters

class AutoTestIAPipeline:
    """Orchestrates the AutoTestIA question generation process."""

    def __init__(self, config_override: Optional[dict] = None):
        """
        Initializes the pipeline and its components based on config or overrides.
        """
        print("Initializing AutoTestIA Pipeline...")

        # Apply overrides if provided (simple example)
        current_config = {
            "llm_provider": config.LLM_PROVIDER,
            "generator_model": config.GENERATOR_MODEL,
            "reviewer_model": config.REVIEWER_MODEL,
            "use_llm_review": config.DEFAULT_LLM_REVIEW_ENABLED,
            "api_keys": { # Pass collected keys
                 "openai": config.OPENAI_API_KEY,
                 "google": config.GOOGLE_API_KEY,
                 "anthropic": config.ANTHROPIC_API_KEY,
                 "replicate": config.REPLICATE_API_TOKEN,
            }
            # Add other configurable parameters here
        }
        if config_override:
            # Basic merge - overwrite default config with overrides
            current_config.update(config_override)
            print(f"Applying config overrides: {config_override}")


        # Initialize agents with potentially overridden config
        self.generator = QuestionGenerator(
            llm_provider=current_config["llm_provider"],
            model_name=current_config["generator_model"],
            api_keys=current_config["api_keys"]
        )
        self.reviewer = QuestionReviewer(
            use_llm=current_config["use_llm_review"],
            llm_provider=current_config["llm_provider"], # Reviewer uses same provider
            model_name=current_config["reviewer_model"],
            api_keys=current_config["api_keys"]
            # criteria can also be made configurable
        )
        print("Pipeline initialized.")

    def run(self,
            input_material_path: str,
            image_paths: Optional[List[str]] = None,
            output_md_path: str = config.DEFAULT_OUTPUT_MD_FILE,
            output_formats: Optional[List[str]] = None,
            num_questions: int = config.DEFAULT_NUM_QUESTIONS,
            extract_images_from_doc: bool = False, # New arg
            skip_manual_review: bool = False,
            language: str = config.DEFAULT_LANGUAGE
            ) -> str:
        """
        Runs the full pipeline: parse -> generate -> review -> write MD -> [manual review] -> parse MD -> convert.

        Args:
            input_material_path: Path to the main input document (txt, pdf, etc.).
            image_paths: Optional list of paths to images for image-specific questions.
            output_md_path: Path to save the intermediate Markdown file for review.
            output_formats: List of desired output formats ('moodle_xml', 'gift', 'wooclap', 'rexams').
                            Defaults to ['moodle_xml', 'gift'].
            num_questions: Desired number of questions to generate from text.
            extract_images_from_doc: If True, attempt to extract images from within the
                                     input document (currently not implemented).
            skip_manual_review: If True, bypass the manual review step and proceed directly
                                to conversion using the auto-reviewed questions.

        Returns:
            The path to the generated Markdown file (or an empty string on critical error).
        """
        print(f"\n--- Starting Pipeline Run ---")
        print(f"Provider: {self.generator.llm_provider}, Generator: {self.generator.model_name}, Reviewer: {self.reviewer.model_name if self.reviewer.use_llm else 'Rules Only'}")
        print(f"Input material: {input_material_path}")
        if image_paths:
            print(f"Input images: {', '.join(image_paths)}")

        # 1. Parse Input Material (OE1 part 1)
        print("\nStep 1: Parsing input material...")
        logging.info(f"Pipeline starting parsing for: {input_material_path}")
        try:
            # Pass the new argument and unpack the tuple
            text_content, doc_image_refs = parser.parse_input_material(
                input_material_path,
                extract_images=extract_images_from_doc # Pass the flag
            )
            if not text_content and not doc_image_refs:
                 logging.warning(f"Parsing resulted in no text or image references for {input_material_path}.")
                 # Decide if this is an error or just an empty file
                 # Let's continue but generation might fail.
            else:
                 logging.info(f"Successfully parsed text content (length: {len(text_content)}).")
                 if doc_image_refs: # Log if image refs were returned (even if placeholders)
                     logging.info(f"Found {len(doc_image_refs)} image references in document (extraction TBD).")

        except FileNotFoundError as e:
            logging.error(f"Input material file not found: {e}")
            print(f"Error: Input file not found: {input_material_path}", file=sys.stderr) # Also print user-friendly error
            return "" # Return empty path on critical error
        except Exception as e: # Catch broader parsing errors
            logging.error(f"Error during input material parsing: {e}", exc_info=True)
            print(f"Error: Failed to parse input file {input_material_path}. Check logs for details.", file=sys.stderr)
            return ""

        # Handle explicitly provided images (distinct from extracted ones)
        parsed_direct_images = []
        if image_paths:
            print("\nProcessing direct image inputs...")
            for img_path in image_paths:
                try:
                    # parse_image_input now validates and returns path or raises error
                    validated_img_path = parser.parse_image_input(img_path)
                    if validated_img_path:
                        parsed_direct_images.append(validated_img_path) # Store path
                        logging.info(f"Accepted direct image for processing: {img_path}")
                except (FileNotFoundError, ValueError, Exception) as e:
                    logging.warning(f"Could not accept direct image input {img_path}: {e}")
                    print(f"Warning: Skipping direct image '{img_path}': {e}")


        # 2. Generate Questions (OE1 part 2)
        print("\nStep 2: Generating questions...")
        generated_questions: List[Question] = []
        num_options = config.DEFAULT_NUM_OPTIONS # Get from config

        # Generate from text content if available
        if text_content:
             logging.info(f"Generating questions from extracted text ({len(text_content)} chars).")
             generated_questions.extend(
                 self.generator.generate_questions_from_text(
                     text_content,
                     num_questions=num_questions,
                     num_options=num_options,
                     language=language)
             )
        else:
             logging.warning("No text content extracted from input material. Cannot generate text-based questions.")

        # Generate questions for specific DIRECT images
        image_question_id_start = (generated_questions[-1].id + 1) if generated_questions else 1
        # Use parsed_direct_images which contains validated paths
        for idx, img_path in enumerate(parsed_direct_images):
             logging.info(f"Generating question for direct image input: {img_path}")
             # Provide some context if text exists
             context_for_image = text_content[:500] if text_content else None
             img_question = self.generator.generate_question_from_image(
                 image_path=img_path,
                 context_text=context_for_image,
                 num_options=num_options
                 )
             if img_question:
                 img_question.id = image_question_id_start + idx
                 generated_questions.append(img_question)

        # TODO: Future - Generate questions based on images extracted from documents (doc_image_refs)
        if extract_images_from_doc and doc_image_refs:
             logging.warning("Image extraction from documents is requested but not yet fully implemented in the generator.")
             # Add logic here later to call generator with extracted image data/paths


        if not generated_questions:
            logging.error("No questions were generated from text or images. Exiting.")
            print("Error: Failed to generate any questions.", file=sys.stderr)
            return output_md_path # Return MD path maybe, as it might exist but be empty

        print(f"Generated a total of {len(generated_questions)} questions.")

        # 3. Review Questions (OE2)
        print("\nStep 3: Reviewing questions...")
        reviewed_questions = self.reviewer.review_questions(generated_questions)
        print(f"Completed automated review for {len(reviewed_questions)} questions.")

        # 4. Write to Markdown for Manual Review (OE3) / Or Skip
        print("\nStep 4: Writing questions to Markdown...")
        markdown_writer.write_questions_to_markdown(reviewed_questions, output_md_path)

        if skip_manual_review:
             print("Skipping manual review step as requested.")
             final_questions = reviewed_questions # Use auto-reviewed questions directly
        else:
            # --- Manual Review Step ---
            print(f"\nMarkdown file ready for review: {output_md_path}")
            print("--- Manual Review Step (OE3) ---")
            print("Please manually review and edit the generated Markdown file.")
            print("Modify text, options, correct answers as needed.")
            print("Mark questions for deletion by changing 'DELETE=FALSE' to 'DELETE=TRUE'.")
            try:
                input(f"Press Enter after you have reviewed and saved the file '{output_md_path}'...")
            except EOFError:
                 # Handle cases where input is not available (e.g., running in a non-interactive environment)
                 print("\nInput stream closed, proceeding without manual review confirmation.")
                 # Decide if you should parse anyway or treat as skip. Let's parse.

            # 5. Parse Reviewed Markdown
            print("\nStep 5: Parsing reviewed Markdown file...")
            try:
                final_questions = markdown_writer.parse_reviewed_markdown(output_md_path)
            except FileNotFoundError:
                print(f"Error: Reviewed Markdown file not found at {output_md_path}. Skipping conversion.")
                # Return MD path even if parsing failed, as it was generated
                return output_md_path
            except Exception as e:
                print(f"Error parsing reviewed Markdown file: {e}. Skipping conversion.")
                return output_md_path


        if not final_questions:
            print("No valid questions found after review phase. No final output files generated.")
            return output_md_path

        print(f"Proceeding to convert {len(final_questions)} final questions.")

        # 6. Convert to Desired Formats (OE4)
        print("\nStep 6: Converting to final formats...")
        if output_formats is None:
            output_formats = ['moodle_xml', 'gift'] # Default formats

        # Ensure output directory exists relative to MD file
        output_dir = os.path.dirname(output_md_path)
        if not output_dir: output_dir = "." # Handle case where output_md is in current dir
        os.makedirs(output_dir, exist_ok=True) # Create it just in case

        if 'moodle_xml' in output_formats:
            # Construct path relative to the MD file's directory
            moodle_filename = os.path.basename(config.DEFAULT_OUTPUT_MOODLE_XML_FILE)
            moodle_path = os.path.join(output_dir, moodle_filename)
            converters.convert_to_moodle_xml(final_questions, moodle_path)

        if 'gift' in output_formats:
            gift_filename = os.path.basename(config.DEFAULT_OUTPUT_GIFT_FILE)
            gift_path = os.path.join(output_dir, gift_filename)
            converters.convert_to_gift(final_questions, gift_path)

        if 'wooclap' in output_formats:
            wooclap_filename = os.path.basename(config.DEFAULT_OUTPUT_WOOCLAP_FILE)
            wooclap_path = os.path.join(output_dir, wooclap_filename)
            converters.convert_to_wooclap(final_questions, wooclap_path)

        if 'rexams' in output_formats:
            # R/exams output is a directory
            rexams_dirname = os.path.basename(config.DEFAULT_OUTPUT_REXAMS_DIR.rstrip('/\\'))
            rexams_dir_path = os.path.join(output_dir, rexams_dirname)
            # converters.prepare_for_rexams will create the dir if needed
            converters.prepare_for_rexams(final_questions, rexams_dir_path)


        print("\n--- Pipeline Run Finished ---")
        return output_md_path 