import os
from typing import List, Optional
import logging
import sys
import random
import shutil
import copy

from . import config
from .schemas import QuestionRecord, QuestionStage, QuestionContent, EvaluationData
from .input_parser import parser
from .agents.generator import QuestionGenerator
from .agents.reviewer import QuestionReviewer
from .agents.evaluator import QuestionEvaluator
from . import pexams_converter
from . import artifacts

from pexams import generate_exams, utils
from pexams.io import (
    gift_converter as pexams_gift,
    moodle_xml_converter as pexams_moodle,
    rexams_converter as pexams_rexams,
    wooclap_converter as pexams_wooclap
)

# The old Question dataclass is needed for compatibility with existing converters.
# This should be phased out eventually.
from dataclasses import dataclass
@dataclass
class LegacyQuestion:
    id: int
    text: str
    correct_answer: str
    distractors: List[str]
    source_material: Optional[str] = None
    image_reference: Optional[str] = None
    explanation: Optional[str] = None
    initial_evaluation: Optional[EvaluationData] = None
    reviewed_evaluation: Optional[EvaluationData] = None
    
    @property
    def options(self) -> List[str]:
        return [self.correct_answer] + self.distractors

logger = logging.getLogger(__name__)

class AutoTestIAPipeline:
    """Orchestrates the AutoTestIA question generation process."""

    def __init__(self, config_override: Optional[dict] = None):
        """
        Initializes the pipeline and its components based on config or overrides.
        """
        print("Initializing AutoTestIA Pipeline...")

        # Apply overrides if provided
        self.current_config = {
            "llm_provider": config.LLM_PROVIDER,
            "generator_model": config.GENERATOR_MODEL,
            "reviewer_model": config.REVIEWER_MODEL,
            "evaluator_model": config.EVALUATOR_MODEL,
            "use_llm_review": config.DEFAULT_LLM_REVIEW_ENABLED,
            "api_keys": {
                 "openai": config.OPENAI_API_KEY,
                 "google": config.GOOGLE_API_KEY,
                 "anthropic": config.ANTHROPIC_API_KEY,
                 "replicate": config.REPLICATE_API_TOKEN,
                 "openrouter": config.OPENROUTER_API_KEY,
            }
        }
        if config_override:
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
            llm_provider=self.current_config["llm_provider"],
            model_name=self.current_config["reviewer_model"],
            api_keys=self.current_config["api_keys"]
        )
        self.evaluator = QuestionEvaluator(
            llm_provider=self.current_config["llm_provider"],
            model_name=self.current_config["evaluator_model"],
            api_keys=self.current_config["api_keys"]
        )
        logging.info(f"Pipeline initialized with use_llm_review={self.current_config['use_llm_review']}.")

    def generate(self,
                 input_material_paths: Optional[List[str]],
                 image_paths: Optional[List[str]] = None,
                 output_md_path: str = "generated_questions.md",
                 output_tsv_path: str = "generated_questions.tsv",
                 num_questions: int = config.DEFAULT_NUM_QUESTIONS,
                 language: str = config.DEFAULT_LANGUAGE,
                 generator_instructions: Optional[str] = None,
                 reviewer_instructions: Optional[str] = None,
                 evaluator_instructions: Optional[str] = None,
                 evaluate_initial: bool = False,
                 evaluate_reviewed: bool = False,
                 num_questions_per_image: int = 1):
        """
        Runs the full question generation and review pipeline.
        """
        print("\n--- Starting Generation Pipeline ---")
        question_records: List[QuestionRecord] = []

        # 1. Parse Input Material
        text_content = ""
        if input_material_paths:
            print("\nStep 1: Parsing input material...")
            all_text_content = []
            for path in input_material_paths:
                logging.info(f"Parsing input material: {path}")
                try:
                    # NOTE: Image extraction from docs is not fully supported in this refactor pass
                    parsed_text, _ = parser.parse_input_material(path)
                    if parsed_text:
                        all_text_content.append(parsed_text)
                    else:
                        logging.warning(f"No text content extracted from '{path}'. Skipping.")
                except Exception as e:
                    logging.error(f"Failed to parse input material {path}: {e}", exc_info=True)
            
            text_content = "\n\n---\n\n".join(all_text_content)

        # If there's no text, no images and no generator instructions, there's nothing to work with
        if not text_content and not image_paths and not generator_instructions:
            logging.critical("No text could be extracted from input files, no images were provided, and no generator instructions were given. Cannot generate questions.")
            sys.exit(1)

        if not text_content:
            if image_paths:
                print("\nStep 1: Parsing input material... (No text content found, proceeding with images only)")
            else:
                # We may still proceed if generator_instructions is provided (e.g. CLI '--generator-instructions')
                print("\nStep 1: Parsing input material... (No text content found, proceeding with generator instructions only)")
        
        # 2. Generate Questions
        print("\nStep 2: Generating questions...")
        question_records = self.generator.generate_questions_from_text(
            text_content=text_content,
            num_questions=num_questions,
            language=language,
            custom_instructions=generator_instructions,
            source_material_path=", ".join(input_material_paths) if input_material_paths else None
        )
        
        # Add image-based questions
        if image_paths:
            print("\nStep 2b: Generating questions from images...")
            image_records = self.generator.generate_questions_from_images(
                image_paths=image_paths,
                context_text=None, #text_content, # Provide text as context
                custom_instructions=generator_instructions,
                language=language,
                num_questions_per_image=num_questions_per_image
            )
            if image_records:
                print(f"Generated {len(image_records)} questions from images.")
                question_records.extend(image_records)
            else:
                print("No questions were generated from the provided images.")


        if not question_records:
            logging.error("No questions were generated. Halting pipeline.")
            print("Error: Failed to generate any questions.", file=sys.stderr)
            artifacts.write_artifacts([], output_md_path, output_tsv_path) # Write empty artifacts
            raise RuntimeError("Failed to generate any questions.")

        print(f"Generated {len(question_records)} questions.")

        # 3. Initial Evaluation
        if evaluate_initial:
            print("\nStep 3: Evaluating initial questions...")
            self.evaluator.evaluate_records(
                question_records,
                stage=QuestionStage.GENERATED,
                custom_instructions=evaluator_instructions,
                language=language
            )
            print("Initial evaluation complete.")
        else:
            print("\nStep 3: Evaluating initial questions... (Skipped)")

        # 4. Review Questions
        print("\nStep 4: Reviewing questions...")
        question_records = self.reviewer.review_questions(
            question_records,
            custom_instructions=reviewer_instructions
        )
        print("Automated review complete.")

        # 5. Reviewed Evaluation
        if evaluate_reviewed:
            print("\nStep 5: Evaluating reviewed questions...")
            self.evaluator.evaluate_records(
                question_records,
                stage=QuestionStage.REVIEWED,
                custom_instructions=evaluator_instructions,
                language=language
            )
            print("Reviewed evaluation complete.")
        else:
            print("\nStep 5: Evaluating reviewed questions... (Skipped)")

        # 7. Write final artifacts
        print(f"\nStep 7: Writing artifacts...")
        artifacts.write_artifacts(
            records=question_records,
            md_path=output_md_path,
            tsv_path=output_tsv_path
        )
        print(f"Intermediate markdown written to: {os.path.abspath(output_md_path)}")
        print("\n--- Generation Pipeline Finished ---")
        print(f"Ready for manual review. Please edit: {os.path.join(output_md_path)}")

    def export(self,
               records_to_export: List[QuestionRecord],
               input_md_path: str,
               output_formats: List[str],
               shuffle_questions_seed: Optional[int] = None,
               shuffle_answers_seed: Optional[int] = None,
               num_final_questions: Optional[int] = None,
               exam_title: Optional[str] = None,
               exam_course: Optional[str] = None,
               exam_date: Optional[str] = None,
               exam_models: int = 1,
               language: str = 'en',
               font_size: str = '11pt',
               columns: int = 1,
               generate_fakes: int = 0,
               generate_references: bool = False,
               total_students: int = 0,
               extra_model_templates: int = 0,
               keep_html: bool = False,
               evaluate_final: bool = False,
               evaluator_instructions: Optional[str] = None,
               max_image_width: Optional[int] = None,
               max_image_height: Optional[int] = None,
               custom_header: Optional[str] = None
               ):
        """
        Runs the export part of the pipeline.
        """
        print(f"\n--- Starting Export Pipeline from {input_md_path} ---")

        if evaluate_final:
            print("\nEvaluating final questions...")
            self.evaluator.evaluate_records(
                records_to_export,
                stage=QuestionStage.FINAL,
                custom_instructions=evaluator_instructions,
                language=language
            )
            print("Final evaluation complete.")
        else:
            print("\nEvaluating final questions... (Skipped)")
        
        questions_for_conversion = records_to_export

        # Subset Selection
        if num_final_questions is not None and 0 < num_final_questions < len(questions_for_conversion):
            print(f"Selecting random subset of {num_final_questions} questions...")
            # Use seed if provided for deterministic selection, otherwise global random
            rng = random.Random(shuffle_questions_seed) if shuffle_questions_seed is not None else random
            questions_for_conversion = rng.sample(questions_for_conversion, num_final_questions)

        if output_formats == ["none"]:
            print("Output format is 'none', skipping file generation.")
            print("\n--- Export Pipeline Finished ---")
            return

        # --- 5. Convert to final formats ---
        base_filename = os.path.splitext(os.path.basename(input_md_path))[0]
        output_dir_for_conversions = os.path.dirname(input_md_path)

        # Convert to PexamQuestion objects
        pexam_questions_base = pexams_converter.convert_autotestia_to_pexam(
            records=questions_for_conversion,
            input_md_path=input_md_path,
            max_image_width=max_image_width,
            max_image_height=max_image_height
        )

        # Set fixed seeds for this export run to ensure consistency across formats
        # If no seed provided, generate one random seed to use for ALL formats in this run
        effective_q_seed = shuffle_questions_seed
        if effective_q_seed is None:
            # Generate a random seed if none provided, so all formats get SAME random shuffle
            effective_q_seed = random.randint(0, 2**32 - 1)
            logging.info(f"No shuffle seed provided. Using generated seed {effective_q_seed} for consistency across formats.")

        effective_a_seed = shuffle_answers_seed if shuffle_answers_seed is not None else 42

        for fmt in output_formats:
            print(f"Exporting to format: {fmt}")
            
            # Determine output directory or file path based on format
            suffix = f"_{fmt}_output" if fmt == 'pexams' else ""
            output_base = os.path.join(output_dir_for_conversions, f"{base_filename}{suffix}")
            
            # Set global seeds for this iteration to ensure consistency/determinism
            utils.set_seeds(seed_questions=effective_q_seed, seed_answers=effective_a_seed)

            # Always work on a copy to avoid side effects (e.g. pexams modifying list in-place)
            questions_to_export = copy.deepcopy(pexam_questions_base)

            if fmt == 'pexams':
                output_dir = output_base
                os.makedirs(output_dir, exist_ok=True)
                
                # generate_exams handles shuffling internally using the global seeds
                generate_exams.generate_exams(
                    questions=questions_to_export,
                    output_dir=output_dir,
                    num_models=int(exam_models),
                    exam_title=exam_title if exam_title is not None else "Final Exam",
                    exam_course=exam_course,
                    exam_date=exam_date,
                    font_size=font_size,
                    columns=columns,
                    lang=language,
                    generate_fakes=generate_fakes,
                    generate_references=generate_references,
                    keep_html=keep_html,
                    total_students=total_students,
                    extra_model_templates=extra_model_templates,
                    # shuffle_questions removed, handled via utils.set_seeds
                    # seed_answers removed, handled via utils.set_seeds
                    custom_header=custom_header
                )
                print(f"Pexams outputs generated in: {os.path.abspath(output_dir)}")

            else:
                # For other formats, we must shuffle manually
                # (questions_to_export is already a copy)
                
                # Apply shuffling
                utils.shuffle_questions_list(questions_to_export)
                for q in questions_to_export:
                    utils.shuffle_options_for_question(q)

                if fmt == 'rexams':
                    # rexams needs a directory
                    output_dir = f"{output_base}_rexams"
                    os.makedirs(output_dir, exist_ok=True)
                    pexams_rexams.prepare_for_rexams(questions_to_export, output_dir)
                    print(f"R/exams files generated in: {os.path.abspath(output_dir)}")
                
                elif fmt == 'wooclap':
                    output_file = f"{output_base}_wooclap.csv"
                    pexams_wooclap.convert_to_wooclap(questions_to_export, output_file)
                    print(f"Wooclap file generated at: {os.path.abspath(output_file)}")

                elif fmt == 'gift':
                    output_file = f"{output_base}.gift"
                    pexams_gift.convert_to_gift(questions_to_export, output_file)
                    print(f"GIFT file generated at: {os.path.abspath(output_file)}")

                elif fmt == 'moodle_xml':
                    output_file = f"{output_base}_moodle.xml"
                    pexams_moodle.convert_to_moodle_xml(questions_to_export, output_file)
                    print(f"Moodle XML file generated at: {os.path.abspath(output_file)}")
                
                else:
                    logging.error(f"Unknown format: {fmt}")


        print("\n--- Export Pipeline Finished ---") 