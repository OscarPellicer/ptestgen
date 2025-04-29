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
        self.current_config = {
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
            self.current_config.update(config_override)
            logging.info(f"Applying config overrides: {config_override}")


        # Initialize agents with potentially overridden config
        self.generator = QuestionGenerator(
            llm_provider=self.current_config["llm_provider"],
            model_name=self.current_config["generator_model"],
            api_keys=self.current_config["api_keys"]
        )
        self.reviewer = QuestionReviewer(
            use_llm=self.current_config["use_llm_review"],
            llm_provider=self.current_config["llm_provider"], # Reviewer uses same provider
            model_name=self.current_config["reviewer_model"],
            api_keys=self.current_config["api_keys"]
            # criteria can also be made configurable
        )
        logging.info(f"Pipeline initialized with use_llm_review={self.current_config['use_llm_review']}.")

    def run(self,
            input_material_path: Optional[str], # Can be None if resuming
            output_md_path: Optional[str],      # Can be None if resuming
            resume_md_path: Optional[str] = None, # New arg for resuming
            image_paths: Optional[List[str]] = None,
            output_formats: Optional[List[str]] = None,
            num_questions: int = config.DEFAULT_NUM_QUESTIONS,
            extract_images_from_doc: bool = False,
            skip_manual_review: bool = False,
            language: str = config.DEFAULT_LANGUAGE,
            use_llm_review: Optional[bool] = None # Added back to handle explicit None from main.py when resuming
            ) -> str:
        """
        Runs the AutoTestIA pipeline.
        Can start from input material OR resume from an existing Markdown file.

        Args:
            input_material_path: Path to the main input document. Required if not resuming.
            output_md_path: Path to save the intermediate Markdown file. Required if not resuming.
            resume_md_path: Path to an existing Markdown file to resume processing from.
                             If provided, input_material_path and related args are ignored.
            image_paths: Optional list of paths to images (used only if not resuming).
            output_formats: List of desired output formats ('moodle_xml', 'gift', 'wooclap', 'rexams', 'none').
                            Defaults to ['moodle_xml', 'gift'].
            num_questions: Desired number of questions (used only if not resuming).
            extract_images_from_doc: Attempt to extract images (used only if not resuming).
            skip_manual_review: Bypass manual review (used only if not resuming).
            language: Language for questions (used only if not resuming).
            use_llm_review: Explicitly enable/disable LLM review (used only if not resuming).

        Returns:
            The path to the intermediate Markdown file.
        """
        print(f"\n--- Starting Pipeline Run ---")
        # Determine effective config for this run
        final_use_llm_review = self.current_config["use_llm_review"] if use_llm_review is None else use_llm_review

        # --- State variables ---
        generated_questions: List[Question] = []
        reviewed_questions: List[Question] = []
        final_questions: List[Question] = []
        markdown_file_for_conversion: Optional[str] = None

        if resume_md_path:
            # --- Resume Mode --- #
            print(f"Resuming pipeline from: {resume_md_path}")
            logging.info(f"Pipeline resuming from specified Markdown: {resume_md_path}")
            if not os.path.exists(resume_md_path):
                logging.error(f"Resume Markdown file not found: {resume_md_path}")
                print(f"Error: Resume file not found: {resume_md_path}", file=sys.stderr)
                return ""
            markdown_file_for_conversion = resume_md_path
            # Skip steps 1-4
            print("Skipping Steps 1-4 (Generation and Initial Review) as resuming.")

        else:
            # --- Generation Mode --- #
            if not input_material_path or not output_md_path:
                 logging.error("Generation mode requires input_material_path and output_md_path.")
                 print("Error: Missing input_material_path or output_md_path for generation.", file=sys.stderr)
                 return ""

            print(f"Provider: {self.generator.llm_provider}, Generator: {self.generator.model_name}, Reviewer: {self.reviewer.model_name if final_use_llm_review else 'Rules Only'}")
            print(f"Input material: {input_material_path}")
            if image_paths:
                print(f"Input images: {', '.join(image_paths)}")

            # Ensure the reviewer reflects the potentially overridden flag for *this run*
            # (The instance's reviewer might have been init'd with a different value)
            # Note: This assumes QuestionReviewer can have its mode changed after init, or we re-init.
            # Let's check if the value differs from the initialized one and log/update if possible.
            if self.reviewer.use_llm != final_use_llm_review:
                logging.info(f"Updating reviewer LLM usage for this run to: {final_use_llm_review}")
                self.reviewer.use_llm = final_use_llm_review # Assuming direct modification is okay

            # 1. Parse Input Material (OE1 part 1)
            print("\nStep 1: Parsing input material...")
            logging.info(f"Pipeline starting parsing for: {input_material_path}")
            try:
                text_content, doc_image_refs = parser.parse_input_material(
                    input_material_path,
                    extract_images=extract_images_from_doc
                )
                if not text_content and not doc_image_refs:
                     logging.warning(f"Parsing resulted in no text or image references for {input_material_path}.")
                else:
                     logging.info(f"Successfully parsed text content (length: {len(text_content)}).")
                     if doc_image_refs:
                         logging.info(f"Found {len(doc_image_refs)} image references in document (extraction TBD).")

            except FileNotFoundError as e:
                logging.error(f"Input material file not found: {e}")
                print(f"Error: Input file not found: {input_material_path}", file=sys.stderr)
                return ""
            except Exception as e:
                logging.error(f"Error during input material parsing: {e}", exc_info=True)
                print(f"Error: Failed to parse input file {input_material_path}. Check logs for details.", file=sys.stderr)
                return ""

            # Handle explicitly provided images
            parsed_direct_images = []
            if image_paths:
                print("\nProcessing direct image inputs...")
                for img_path in image_paths:
                    try:
                        validated_img_path = parser.parse_image_input(img_path)
                        if validated_img_path:
                            parsed_direct_images.append(validated_img_path)
                            logging.info(f"Accepted direct image for processing: {img_path}")
                    except (FileNotFoundError, ValueError, Exception) as e:
                        logging.warning(f"Could not accept direct image input {img_path}: {e}")
                        print(f"Warning: Skipping direct image '{img_path}': {e}")

            # 2. Generate Questions (OE1 part 2)
            print("\nStep 2: Generating questions...")
            num_options = config.DEFAULT_NUM_OPTIONS

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
                 logging.warning("No text content extracted. Cannot generate text-based questions.")

            image_question_id_start = (generated_questions[-1].id + 1) if generated_questions else 1
            for idx, img_path in enumerate(parsed_direct_images):
                 logging.info(f"Generating question for direct image input: {img_path}")
                 context_for_image = text_content[:500] if text_content else None
                 img_question = self.generator.generate_question_from_image(
                     image_path=img_path,
                     context_text=context_for_image,
                     num_options=num_options
                     )
                 if img_question:
                     img_question.id = image_question_id_start + idx
                     generated_questions.append(img_question)

            if extract_images_from_doc and doc_image_refs:
                 logging.warning("Image extraction from documents requested but not implemented in generator.")

            if not generated_questions:
                logging.error("No questions were generated. Cannot proceed.")
                print("Error: Failed to generate any questions.", file=sys.stderr)
                # Try to create the output dir for the empty MD file anyway
                output_md_dir = os.path.dirname(output_md_path)
                if output_md_dir: os.makedirs(output_md_dir, exist_ok=True)
                # Write an empty MD file?
                with open(output_md_path, 'w') as f: f.write("<!-- No questions generated -->\n")
                return output_md_path # Return path to the (possibly empty) MD file

            print(f"Generated a total of {len(generated_questions)} questions.")

            # 3. Review Questions (OE2)
            print("\nStep 3: Reviewing questions...")
            # Ensure reviewer uses the correct setting for this run
            self.reviewer.use_llm = final_use_llm_review
            reviewed_questions = self.reviewer.review_questions(generated_questions)
            print(f"Completed automated review for {len(reviewed_questions)} questions.")

            # 4. Write to Markdown for Manual Review (OE3)
            print("\nStep 4: Writing questions to Markdown...")
            try:
                markdown_writer.write_questions_to_markdown(reviewed_questions, output_md_path)
                markdown_file_for_conversion = output_md_path
                print(f"Intermediate Markdown file saved to: {output_md_path}")
            except Exception as e:
                logging.error(f"Failed to write Markdown file to {output_md_path}: {e}", exc_info=True)
                print(f"Error: Could not write intermediate Markdown file to {output_md_path}. Check logs.", file=sys.stderr)
                return "" # Critical error, cannot continue

        # --- Check if only Markdown generation was requested --- #
        if output_formats == ['none']:
            print("\nOutput format 'none' selected. Skipping conversion steps.")
            logging.info("Output format 'none' specified, pipeline finished after Markdown generation/identification.")
            # Return the path to the generated/resumed MD file
            return markdown_file_for_conversion if markdown_file_for_conversion else ""

        # --- Conditional Manual Review Step --- #
        # Only relevant if we generated the markdown (not resuming) and didn't skip
        if not resume_md_path and not skip_manual_review:
            print(f"\n--- Manual Review Step (OE3) ---")
            print(f"Please manually review and edit the generated Markdown file: {output_md_path}")
            print("Modify text, options, correct answers as needed.")
            print("Mark questions for deletion by changing 'DELETE=FALSE' to 'DELETE=TRUE'.")
            try:
                input(f"Press Enter after you have reviewed and saved the file '{output_md_path}'...")
            except EOFError:
                 print("\nInput stream closed, proceeding without manual review confirmation.")
        elif not resume_md_path and skip_manual_review:
             print("\nSkipping manual review step as requested.")
             # Use the auto-reviewed questions directly from the file written in Step 4
             pass # We will parse output_md_path in the next step
        # If resuming, we assume the file provided is already reviewed/ready

        # --- Proceed to Conversion --- #
        if not markdown_file_for_conversion:
             # This should ideally not happen if logic above is correct
             logging.error("Markdown file path for conversion is missing.")
             print("Error: Internal state error - Cannot determine Markdown file for conversion.", file=sys.stderr)
             return ""

        # 5. Parse Markdown (Final or Reviewed)
        print(f"\nStep 5: Parsing final Markdown file: {markdown_file_for_conversion}...")
        try:
            final_questions = markdown_writer.parse_reviewed_markdown(markdown_file_for_conversion)
            if not final_questions:
                 # Handle case where parsing succeeds but yields no questions (e.g., all marked DELETE)
                 logging.warning(f"Parsing {markdown_file_for_conversion} resulted in zero valid questions after filtering.")
                 print("Warning: No valid questions found after parsing the Markdown file. No final output files will be generated.")
                 return markdown_file_for_conversion # Return MD path, but signal no conversion happened

        except FileNotFoundError:
            logging.error(f"Markdown file not found at {markdown_file_for_conversion}. Skipping conversion.")
            print(f"Error: Markdown file not found at {markdown_file_for_conversion}. Cannot proceed with conversion.", file=sys.stderr)
            return markdown_file_for_conversion # Return the path that failed
        except Exception as e:
            logging.error(f"Error parsing Markdown file '{markdown_file_for_conversion}': {e}", exc_info=True)
            print(f"Error parsing Markdown file: {e}. Skipping conversion.", file=sys.stderr)
            return markdown_file_for_conversion # Return the path that failed

        print(f"Proceeding to convert {len(final_questions)} final questions.")

        # 6. Convert to Desired Formats (OE4)
        print("\nStep 6: Converting to final formats...")
        if output_formats is None:
            output_formats = ['moodle_xml', 'gift'] # Default formats

        # Ensure output directory exists relative to the *parsed* MD file
        output_dir = os.path.dirname(markdown_file_for_conversion)
        if not output_dir: output_dir = "." # Handle case where MD file is in current dir
        os.makedirs(output_dir, exist_ok=True)

        # Define base filename from the markdown file (without extension)
        base_filename = os.path.splitext(os.path.basename(markdown_file_for_conversion))[0]

        conversion_performed = False
        if 'moodle_xml' in output_formats:
            moodle_path = os.path.join(output_dir, f"{base_filename}_moodle.xml")
            converters.convert_to_moodle_xml(final_questions, moodle_path)
            conversion_performed = True

        if 'gift' in output_formats:
            gift_path = os.path.join(output_dir, f"{base_filename}.gift")
            converters.convert_to_gift(final_questions, gift_path)
            conversion_performed = True

        if 'wooclap' in output_formats:
            wooclap_path = os.path.join(output_dir, f"{base_filename}_wooclap.xlsx")
            converters.convert_to_wooclap(final_questions, wooclap_path)
            conversion_performed = True

        if 'rexams' in output_formats:
            # R/exams output is a directory based on the base filename
            rexams_dir_path = os.path.join(output_dir, f"{base_filename}_rexams")
            converters.prepare_for_rexams(final_questions, rexams_dir_path)
            conversion_performed = True

        if conversion_performed:
            print(f"\nConversion outputs generated in directory: {os.path.abspath(output_dir)}")
        else:
            # This case should be handled by the 'none' check earlier, but as a fallback:
            logging.warning("No conversion formats were specified or matched.")
            print("\nNo conversion formats requested.")

        print("\n--- Pipeline Run Finished ---")
        # Always return the path of the markdown file that was processed or generated
        return markdown_file_for_conversion

    def run_from_file(self,
            input_material_path: str,
            image_paths: Optional[List[str]] = None,
            output_md_path: str = config.DEFAULT_OUTPUT_MD_FILE,
            output_formats: Optional[List[str]] = None,
            num_questions: int = config.DEFAULT_NUM_QUESTIONS,
            extract_images_from_doc: bool = False,
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