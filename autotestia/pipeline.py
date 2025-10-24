import os
from typing import List, Optional
import logging
import sys
import random
import shutil

from . import config
from .schemas import Question
from .input_parser import parser
from .agents.generator import QuestionGenerator
from .agents.reviewer import QuestionReviewer
from .agents.evaluator import QuestionEvaluator
from .output_formatter import markdown_writer, converters
from .rexams import generate_exams as rexams_wrapper
import pexams
from .output_formatter import pexams_adapter

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
            "evaluator_model": config.EVALUATOR_MODEL,
            "use_llm_review": config.DEFAULT_LLM_REVIEW_ENABLED,
            "api_keys": { # Pass collected keys
                 "openai": config.OPENAI_API_KEY,
                 "google": config.GOOGLE_API_KEY,
                 "anthropic": config.ANTHROPIC_API_KEY,
                 "replicate": config.REPLICATE_API_TOKEN,
                 "openrouter": config.OPENROUTER_API_KEY,
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
        self.evaluator = QuestionEvaluator(
            llm_provider=self.current_config["llm_provider"],
            model_name=self.current_config["evaluator_model"],
            api_keys=self.current_config["api_keys"]
        )
        logging.info(f"Pipeline initialized with use_llm_review={self.current_config['use_llm_review']}.")

    def run(self,
            input_material_path: Optional[str], # Can be None if resuming or generating from instructions
            output_md_path: Optional[str],      # Can be None if resuming
            resume_md_path: Optional[str] = None, # New arg for resuming
            image_paths: Optional[List[str]] = None,
            output_formats: Optional[List[str]] = None,
            num_questions: int = config.DEFAULT_NUM_QUESTIONS,
            extract_images_from_doc: bool = False,
            skip_manual_review: bool = False,
            language: str = config.DEFAULT_LANGUAGE,
            use_llm_review: Optional[bool] = None,
            generator_instructions: Optional[str] = None,
            reviewer_instructions: Optional[str] = None,
            evaluator_instructions: Optional[str] = None,
            evaluate_initial: bool = False,
            evaluate_reviewed: bool = False,
            evaluate_final: bool = False,
            shuffle_questions_seed: Optional[int] = None,
            shuffle_answers_seed: Optional[int] = 0,
            num_final_questions: Optional[int] = None,
            exam_title: Optional[str] = None,
            exam_course: Optional[str] = None,
            exam_date: Optional[str] = None,
            exam_models: int = 4,
            font_size: str = "11pt",
            pexams_columns: int = 1,
            pexams_id_length: int = 10,
            pexams_generate_fakes: int = 0,
            pexams_generate_references: bool = False
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
            output_formats: List of desired output formats ('moodle_xml', 'gift', 'wooclap', 'rexams', 'pexams', 'none').
                            Defaults to ['moodle_xml', 'gift'].
            num_questions: Desired number of questions (used only if not resuming).
            extract_images_from_doc: Attempt to extract images (used only if not resuming).
            skip_manual_review: Bypass manual review (used only if not resuming).
            language: Language of the test
            use_llm_review: Explicitly enable/disable LLM review (used only if not resuming).
            generator_instructions: Custom instructions for the QuestionGenerator agent.
            reviewer_instructions: Custom instructions for the QuestionReviewer agent.
            evaluator_instructions: Custom instructions for the QuestionEvaluator agent.
            evaluate_initial: Run evaluator on questions right after generation.
            evaluate_reviewed: Run evaluator on questions after review stage.
            evaluate_final: Run evaluator on questions parsed from the final markdown file.
            shuffle_questions_seed: Seed for shuffling the final question order. None means no shuffle.
            shuffle_answers_seed: Seed for shuffling answers within questions. 0 means shuffle randomly each run, None means no shuffle (default uses 0).
            num_final_questions: Number of questions to select randomly from the final set. None means use all.
            exam_title: Custom title for R/exams or pexams PDF output.
            exam_course: Custom course name for R/exams or pexams PDF output.
            exam_date: Custom date for R/exams or pexams PDF output.
            exam_models: Number of different exam models to generate.
            font_size: Font size for pexams PDF output.
            pexams_columns: Number of columns for questions in pexams PDF.
            pexams_id_length: Number of boxes for the student ID grid.
            pexams_generate_fakes: Generate a number of simulated scans with fake answers for testing the correction process.
            pexams_generate_references: Generate a reference scan with correct answers for each model.

        Returns:
            The path to the intermediate Markdown file.
        """
        print(f"\n--- Starting Pipeline Run ---")
        # Determine effective config for this run
        final_use_llm_review = self.current_config["use_llm_review"] if use_llm_review is None else use_llm_review

        # --- State variables ---
        generated_questions: List[Question] = []
        reviewed_questions: List[Question] = []
        final_questions_parsed: List[Question] = []
        questions_for_conversion: List[Question] = [] # Questions after shuffling/selection
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
            # --- Generation Mode (File or Instructions) --- #
            # Determine if we are generating from a file or just instructions/images
            is_generating_from_file = bool(input_material_path)

            if not is_generating_from_file and not image_paths and not generator_instructions:
                logging.warning("Pipeline started in generation mode without input file, images, or instructions. May produce generic results.")
                print("Warning: No input file, images, or generator instructions provided.", file=sys.stderr)

            if not output_md_path:
                 logging.error("Generation mode requires output_md_path.")
                 print("Error: Missing output_md_path for generation.", file=sys.stderr)
                 return ""

            print(f"Provider: {self.generator.llm_provider_name}")
            print(f"Generator: {self.generator.provider.model_name if self.generator.provider else 'N/A'}")
            if final_use_llm_review:
                print(f"Reviewer: {self.reviewer.provider.model_name if self.reviewer.provider else 'N/A'}")
            else:
                print("Reviewer: Rules Only (LLM Disabled)")

            print(f"Evaluator: {self.evaluator.provider.model_name if self.evaluator.provider else 'N/A'}")

            if is_generating_from_file:
                print(f"Input material: {input_material_path}")
            if image_paths:
                print(f"Input images: {', '.join(image_paths)}")
            if generator_instructions:
                print(f"Generator Instructions: Provided")
            if reviewer_instructions:
                print(f"Reviewer Instructions: Provided")


            # Update reviewer LLM usage if needed for this specific run
            if self.reviewer.use_llm != final_use_llm_review:
                logging.info(f"Updating reviewer LLM usage for this run to: {final_use_llm_review}")
                self.reviewer.use_llm = final_use_llm_review # Assuming direct modification is okay

            # 1. Parse Input Material (Optional)
            text_content = None
            doc_image_refs = []
            if is_generating_from_file:
                print("\nStep 1: Parsing input material...")
                logging.info(f"Pipeline starting parsing for: {input_material_path}")
                try:
                    text_content, doc_image_refs = parser.parse_input_material(
                        input_material_path, # This is guaranteed to be non-None here
                        extract_images=extract_images_from_doc
                    )
                    if not text_content and not doc_image_refs:
                         logging.warning(f"Parsing resulted in no text or image references for {input_material_path}.")
                    else:
                         logging.info(f"Successfully parsed text content (length: {len(text_content if text_content else '')}).")
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
            else:
                print("\nStep 1: Parsing input material... (Skipped - No input file provided)")


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

            # Generate from text OR instructions
            if text_content or generator_instructions:
                 log_source = f"extracted text ({len(text_content)} chars)" if text_content else "provided instructions"
                 logging.info(f"Generating questions from {log_source}.")
                 generated_questions.extend(
                     self.generator.generate_questions_from_text(
                         text_content=text_content, # Can be None
                         num_questions=num_questions,
                         num_options=num_options,
                         language=language,
                         custom_instructions=generator_instructions # Pass instructions
                     )
                 )
            else:
                 logging.warning("No text content or generator instructions provided. Cannot generate text/instruction-based questions.")

            # Generate from images
            image_question_id_start = (generated_questions[-1].id + 1) if generated_questions else 1
            for idx, img_path in enumerate(parsed_direct_images):
                 logging.info(f"Generating question for direct image input: {img_path}")
                 # Use text_content as context only if it exists, otherwise rely on image + instructions
                 context_for_image = text_content[:500] if text_content else None
                 img_question = self.generator.generate_question_from_image(
                     image_path=img_path,
                     context_text=context_for_image,
                     num_options=num_options,
                     custom_instructions=generator_instructions # Pass instructions
                     )
                 if img_question:
                     img_question.id = image_question_id_start + idx
                     generated_questions.append(img_question)

            # TODO: Handle doc_image_refs if extraction is implemented
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

            # --- Optional Evaluation Step: Initial ---
            if evaluate_initial and generated_questions:
                print("\nStep 2a: Evaluating initial questions...")
                generated_questions = self.evaluator.evaluate_questions(
                    generated_questions, 
                    stage='initial', 
                    custom_instructions=evaluator_instructions
                )
                print("Initial evaluation complete.")

            # 3. Review Questions (OE2)
            print("\nStep 3: Reviewing questions...")
            # Pass reviewer instructions to the reviewer method
            reviewed_questions = self.reviewer.review_questions(
                generated_questions,
                custom_instructions=reviewer_instructions # Pass instructions
            )
            print(f"Completed automated review for {len(reviewed_questions)} questions.")

            # --- Optional Evaluation Step: Reviewed ---
            if evaluate_reviewed and reviewed_questions:
                print("\nStep 3a: Evaluating reviewed questions...")
                reviewed_questions = self.evaluator.evaluate_questions(
                    reviewed_questions, 
                    stage='reviewed', 
                    custom_instructions=evaluator_instructions
                )
                print("Reviewed evaluation complete.")


            # 4. Write to Markdown for Manual Review (OE3)
            print("\nStep 4: Writing questions to Markdown...")
            try:
                # Ensure output dir exists
                output_md_dir = os.path.dirname(output_md_path)
                if output_md_dir: os.makedirs(output_md_dir, exist_ok=True)

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
            # Use the correct path (which is now output_md_path in generation mode)
            md_path_for_review = output_md_path if not resume_md_path else resume_md_path
            print(f"Please manually review and edit the generated Markdown file: {md_path_for_review}")
            print("Modify text, options, correct answers as needed.")
            print("Mark questions for deletion by changing 'DELETE=FALSE' to 'DELETE=TRUE'.")
            try:
                input(f"Press Enter after you have reviewed and saved the file '{md_path_for_review}'...")
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
            final_questions_parsed = markdown_writer.parse_reviewed_markdown(markdown_file_for_conversion)
            if not final_questions_parsed:
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

        print(f"Parsed {len(final_questions_parsed)} questions from Markdown.")

        # --- Optional Evaluation Step: Final ---
        if evaluate_final and final_questions_parsed:
            print("\nStep 5a: Evaluating final questions...")
            final_questions_parsed = self.evaluator.evaluate_questions(
                final_questions_parsed, 
                stage='final', 
                custom_instructions=evaluator_instructions
            )
            # Re-write the markdown file with the new evaluation data
            print("Re-writing Markdown file with evaluation results...")
            try:
                evaluated_final_md_path = markdown_file_for_conversion.replace(".md", "_evaluated-final.md")
                markdown_writer.write_questions_to_markdown(final_questions_parsed, evaluated_final_md_path)
                print(f"Updated Markdown with evaluation results: {evaluated_final_md_path}")
            except Exception as e:
                logging.error(f"Failed to re-write Markdown file with evaluation results: {e}", exc_info=True)
                print(f"Warning: Could not update Markdown with evaluation results: {e}")


        # --- Apply Post-Parsing Shuffling and Selection ---
        questions_for_conversion = list(final_questions_parsed) # Start with all parsed questions

        # 5a. Shuffle Questions
        if shuffle_questions_seed is not None:
            print(f"Shuffling question order using seed: {shuffle_questions_seed}...")
            random.Random(shuffle_questions_seed).shuffle(questions_for_conversion)
            logging.info(f"Shuffled {len(questions_for_conversion)} questions with seed {shuffle_questions_seed}.")

        # 5b. Select Subset
        if num_final_questions is not None and 0 < num_final_questions < len(questions_for_conversion):
            print(f"Selecting random subset of {num_final_questions} questions...")
            # Use the same seed as question shuffling if provided, otherwise None (truly random sample)
            sampling_seed = shuffle_questions_seed
            questions_for_conversion = random.Random(sampling_seed).sample(questions_for_conversion, num_final_questions)
            logging.info(f"Selected {len(questions_for_conversion)} questions randomly (seed: {sampling_seed}).")
            print(f"Selected {len(questions_for_conversion)} questions for final output.")
        elif num_final_questions is not None and num_final_questions >= len(questions_for_conversion):
            logging.warning(f"Requested {num_final_questions} final questions, but only {len(questions_for_conversion)} are available. Using all.")
        elif num_final_questions is not None and num_final_questions <= 0:
             logging.warning(f"Requested non-positive number of final questions ({num_final_questions}). Using all {len(questions_for_conversion)} questions.")


        if not questions_for_conversion:
             logging.warning("No questions remain after potential shuffling/selection. No final output files will be generated.")
             print("Warning: No questions available for conversion after selection/shuffling.")
             return markdown_file_for_conversion # Return MD path, but signal no conversion happened


        print(f"Proceeding to convert {len(questions_for_conversion)} final questions.")

        # --- Apply Answer Shuffling ---
        if shuffle_answers_seed is not None:
            print(f"Shuffling answers within questions (seed: {'Random each run' if shuffle_answers_seed == 0 else shuffle_answers_seed})...")
            logging.info(f"Applying answer shuffling (seed: {shuffle_answers_seed}).")

            # Create a single random instance if a specific seed is given
            answer_random = None
            if shuffle_answers_seed != 0:
                answer_random = random.Random(shuffle_answers_seed)

            for question in questions_for_conversion:
                # Use the single instance or create a new one for each question if seed is 0
                current_random = answer_random if answer_random else random.Random()
                # Shuffle the options list in place
                current_random.shuffle(question.options)
        else:
            # Note: If shuffle_answers_seed is None, answers retain their original order.
            logging.info("Skipping answer shuffling as shuffle_answers_seed is None.")


        # 6. Convert to Desired Formats (OE4)
        print("\nStep 6: Converting to final formats...")
        if output_formats is None:
            output_formats = ['moodle_xml', 'gift'] # Default formats

        # Ensure output directory exists relative to the *parsed* MD file
        output_dir_for_conversions = os.path.dirname(markdown_file_for_conversion)
        if not output_dir_for_conversions: output_dir_for_conversions = "." # Handle case where MD file is in current dir
        os.makedirs(output_dir_for_conversions, exist_ok=True)

        # Define base filename from the markdown file (without extension)
        base_filename = os.path.splitext(os.path.basename(markdown_file_for_conversion))[0]

        conversion_performed = False
        # Note: shuffle_answers_seed argument is removed from converter calls below
        # as shuffling is now handled centrally in the pipeline.

        if 'moodle_xml' in output_formats:
            moodle_path = os.path.join(output_dir_for_conversions, f"{base_filename}_moodle.xml")
            converters.convert_to_moodle_xml(questions_for_conversion, moodle_path) 
            conversion_performed = True

        if 'gift' in output_formats:
            gift_path = os.path.join(output_dir_for_conversions, f"{base_filename}.gift")
            converters.convert_to_gift(questions_for_conversion, gift_path) 
            conversion_performed = True

        if 'wooclap' in output_formats:
            # Use the updated default extension from config
            wooclap_path = os.path.join(output_dir_for_conversions, f"{base_filename}_wooclap.csv")
            converters.convert_to_wooclap(questions_for_conversion, wooclap_path) 
            conversion_performed = True

        if 'rexams' in output_formats:
            # Step 1: Prepare .Rmd files
            rexams_rmd_dir = os.path.join(output_dir_for_conversions, f"{base_filename}_rexams_rmd")

            # Check if rexams_rmd_dir exists and ask for deletion
            if os.path.exists(rexams_rmd_dir):
                print(f"Warning: R/exams Rmd directory '{rexams_rmd_dir}' already exists.")
                user_input = input(f"Do you want to delete the existing directory '{rexams_rmd_dir}' and continue? (yes/no): ").strip().lower()
                if user_input == 'yes':
                    try:
                        shutil.rmtree(rexams_rmd_dir)
                        logging.info(f"Deleted existing R/exams Rmd directory: {rexams_rmd_dir}")
                        print(f"Successfully deleted '{rexams_rmd_dir}'. It will be recreated for Rmd file preparation.")
                    except Exception as e:
                        logging.error(f"Failed to delete directory {rexams_rmd_dir}: {e}. Attempting to proceed anyway.")
                        print(f"Error: Could not delete directory {rexams_rmd_dir}. Will attempt Rmd preparation into the existing directory.", file=sys.stderr)
                else:
                    logging.info(f"User chose not to delete existing R/exams Rmd directory '{rexams_rmd_dir}'. Proceeding with existing directory.")
                    print(f"Proceeding with Rmd preparation into the existing directory '{rexams_rmd_dir}'. Files may be overwritten.")
            
            # Ensure the rexams_rmd_dir exists before preparing Rmd files.
            # If it was deleted, it's recreated. If it existed and wasn't deleted, this does nothing.
            # If it didn't exist initially, it's created.
            os.makedirs(rexams_rmd_dir, exist_ok=True)
            
            converters.prepare_for_rexams(questions_for_conversion, rexams_rmd_dir)
            conversion_performed = True 

            # Step 2: Call the R script wrapper
            rexams_pdf_output_dir = os.path.join(output_dir_for_conversions, f"{base_filename}_rexams_pdf_output")
            logging.info(f"Attempting to generate R/exams PDF exams from {rexams_rmd_dir} into {rexams_pdf_output_dir}")
            
            # Ensure the PDF output directory exists. No prompt here, just create if not present.
            os.makedirs(rexams_pdf_output_dir, exist_ok=True)

            # Prepare custom parameters for R script
            r_exam_custom_params = self.current_config.get("rexams_params", {}).copy()
            
            if exam_title is not None:
                r_exam_custom_params["exam-title"] = exam_title
            if exam_course is not None:
                r_exam_custom_params["course"] = exam_course
            if exam_date is not None:
                r_exam_custom_params["date"] = exam_date
            
            # Use the generic exam_models parameter
            r_exam_custom_params["n-models"] = str(exam_models)

            success = rexams_wrapper.generate_rexams_pdfs(
                questions_input_dir=rexams_rmd_dir,
                exams_output_dir=rexams_pdf_output_dir,
                language_str=language,
                num_models=exam_models,
                custom_r_params=r_exam_custom_params 
            )
            
            if success:
                logging.info(f"R/exams PDF generation successful. Output in {rexams_pdf_output_dir}")
                print(f"R/exams PDF outputs generated in: {os.path.abspath(rexams_pdf_output_dir)}")
            else:
                logging.error(f"R/exams PDF generation failed for Rmd files in {rexams_rmd_dir}. Output directory: {rexams_pdf_output_dir}")
                print(f"Warning: R/exams PDF generation failed. Check logs. Rmd files are available at {os.path.abspath(rexams_rmd_dir)}")

        if 'pexams' in output_formats:
            pexams_output_dir = os.path.join(output_dir_for_conversions, f"{base_filename}_pexams_output")
            logging.info(f"Attempting to generate pexams PDF exams into {pexams_output_dir}")
            os.makedirs(pexams_output_dir, exist_ok=True)
            
            # Convert autotestia questions to the portable pexams format
            pexam_questions = pexams_adapter.convert_autotestia_to_pexam(questions_for_conversion)

            # Pass the generic exam parameters to the pexams wrapper
            from pexams import generate_exams
            generate_exams.generate_exams(
                questions=pexam_questions,
                output_dir=pexams_output_dir,
                num_models=int(exam_models),
                exam_title=exam_title if exam_title is not None else "Final Exam",
                exam_course=exam_course,
                exam_date=exam_date,
                font_size=font_size,
                columns=pexams_columns,
                id_length=pexams_id_length,
                lang=language,
                generate_fakes=pexams_generate_fakes,
                generate_references=pexams_generate_references
            )
            conversion_performed = True
            print(f"Pexams (Python/Marp) outputs generated in: {os.path.abspath(pexams_output_dir)}")


        if conversion_performed:
            print(f"\nConversion outputs generated in directory: {os.path.abspath(output_dir_for_conversions)}")
        else:
            # This case should be handled by the 'none' check earlier, but as a fallback:
            logging.warning("No conversion formats were specified or matched.")
            print("\nNo conversion formats requested.")

        print("\n--- Pipeline Run Finished ---")
        # Always return the path of the markdown file that was processed or generated
        return markdown_file_for_conversion 