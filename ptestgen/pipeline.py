import os
from typing import List, Optional
import logging
import sys
import random
import copy

from . import config
from .schemas import QuestionRecord, QuestionStage
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


def _parse_input_materials(paths: List[str], output_dir: str):
    """Text of every input file (joined by separators) and the images extracted from them."""
    texts: List[str] = []
    images: List[str] = []
    for path in paths:
        logging.info(f"Parsing input material: {path}")
        try:
            parsed_text, extracted_images = parser.parse_input_material(path, output_dir=output_dir)
            if extracted_images:
                images.extend(extracted_images)
                logging.info(
                    "Extracted %d image asset(s) referenced from intermediate Markdown for %s. "
                    "They are only sent as context images when --include-images is used.",
                    len(extracted_images),
                    path,
                )
            if parsed_text:
                texts.append(parsed_text)
            else:
                logging.warning(f"No text content extracted from '{path}'. Skipping.")
        except Exception as e:
            logging.error(f"Failed to parse input material {path}: {e}", exc_info=True)
    return "\n\n---\n\n".join(texts), images


# Exporters of the formats other than pexams: (questions, output base path, markdown folder) -> path written.
def _export_rexams(questions, output_base, md_base_dir):
    output_dir = f"{output_base}_rexams"  # rexams needs a directory
    os.makedirs(output_dir, exist_ok=True)
    pexams_rexams.prepare_for_rexams(questions, output_dir, base_dir=md_base_dir)
    print(f"R/exams files generated in: {os.path.abspath(output_dir)}")


def _export_wooclap(questions, output_base, md_base_dir):
    output_file = f"{output_base}_wooclap.csv"
    pexams_wooclap.convert_to_wooclap(questions, output_file)
    print(f"Wooclap file generated at: {os.path.abspath(output_file)}")


def _export_gift(questions, output_base, md_base_dir):
    output_file = f"{output_base}.gift"
    pexams_gift.convert_to_gift(questions, output_file, base_dir=md_base_dir)
    print(f"GIFT file generated at: {os.path.abspath(output_file)}")


def _export_moodle_xml(questions, output_base, md_base_dir):
    output_file = f"{output_base}_moodle.xml"
    pexams_moodle.convert_to_moodle_xml(questions, output_file, base_dir=md_base_dir)
    print(f"Moodle XML file generated at: {os.path.abspath(output_file)}")


FILE_EXPORTERS = {
    'rexams': _export_rexams,
    'wooclap': _export_wooclap,
    'gift': _export_gift,
    'moodle_xml': _export_moodle_xml,
}


class PTestGenPipeline:
    """Orchestrates the PTestGen question generation process."""

    def __init__(self, config_override: Optional[dict] = None):
        """
        Initializes the pipeline and its components based on config or overrides.
        """
        print("Initializing PTestGen Pipeline...")

        # Apply overrides if provided
        self.current_config = {
            "llm_provider": config.LLM_PROVIDER,
            "generator_model": config.GENERATOR_MODEL,
            "reviewer_model": config.REVIEWER_MODEL,
            "evaluator_model": config.EVALUATOR_MODEL,
            "use_llm_review": config.DEFAULT_LLM_REVIEW_ENABLED,
            # Variable holding the API key of the selected provider (None: config.PROVIDER_API_KEY_MAP).
            "api_key_env": None,
            # "effort" sets all three agents; the per-agent keys take precedence.
            "effort": None,
            "generator_effort": config.GENERATOR_EFFORT,
            "reviewer_effort": config.REVIEWER_EFFORT,
            "evaluator_effort": config.EVALUATOR_EFFORT,
        }
        if config_override:
            self.current_config.update(config_override)
            logging.info(f"Applying config overrides: {config_override}")

        cfg = self.current_config

        def agent_llm(role):
            return {
                "llm_provider": cfg["llm_provider"],
                "model_name": cfg[f"{role}_model"],
                "api_key_env": cfg.get("api_key_env"),
                "effort": (config_override or {}).get(f"{role}_effort") or cfg.get("effort") or cfg.get(f"{role}_effort"),
            }

        # Initialize agents with potentially overridden config. Clients connect on first use.
        self.generator = QuestionGenerator(**agent_llm("generator"))
        self.reviewer = QuestionReviewer(use_llm=cfg["use_llm_review"], **agent_llm("reviewer"))
        self.evaluator = QuestionEvaluator(**agent_llm("evaluator"))
        logging.info(f"Pipeline initialized with use_llm_review={self.current_config['use_llm_review']}.")

    def _providers(self):
        agents = (("generator", self.generator), ("reviewer", self.reviewer), ("evaluator", self.evaluator))
        return {role: agent.provider for role, agent in agents if getattr(agent, "provider", None) is not None}

    def start_llm_log(self, output_dir: str, command: str, inputs=()) -> None:
        """Log every LLM call of this run to ``<output_dir>/llm_calls.jsonl`` and write
        ``run_manifest.json`` (command, package versions, models, input hashes), as pexams and
        pevaluate do."""
        providers = self._providers()
        if not providers:
            return
        output_dir = output_dir or "."
        for provider in providers.values():
            provider.log_path = os.path.join(output_dir, "llm_calls.jsonl")
        try:
            from pexams.llm import write_run_manifest

            write_run_manifest(
                output_dir,
                "ptestgen",
                inputs=[path for path in inputs if path],
                extra={"subcommand": command, "llm": {role: provider.describe() for role, provider in providers.items()}},
            )
        except Exception as e:  # provenance must never stop a run
            logging.warning(f"Could not write run_manifest.json: {e}")


    def _evaluate_stage(self, records, stage, enabled, title, done, instructions, language):
        """Run the evaluator on ``records`` at ``stage`` if ``enabled``, printing the step."""
        if not enabled:
            print(f"\n{title}... (Skipped)")
            return
        print(f"\n{title}...")
        self.evaluator.evaluate_records(
            records,
            stage=stage,
            custom_instructions=instructions,
            language=language
        )
        print(done)

    def _generate_records(self, text_content, image_paths, extracted_image_paths, input_material_paths,
                          num_questions, language, generator_instructions, num_questions_per_image,
                          question_type, include_images) -> List[QuestionRecord]:
        """Questions from the text (and instructions), then the questions from each image."""
        print("\nStep 2: Generating questions...")
        records = self.generator.generate_questions_from_text(
            text_content=text_content,
            num_questions=num_questions,
            language=language,
            custom_instructions=generator_instructions,
            source_material_path=", ".join(input_material_paths) if input_material_paths else None,
            question_type=question_type,
            context_image_paths=extracted_image_paths if include_images else [],
        )

        if image_paths:
            print("\nStep 2b: Generating questions from images...")
            image_records = self.generator.generate_questions_from_images(
                image_paths=image_paths,
                context_text=None,
                custom_instructions=generator_instructions,
                language=language,
                num_questions_per_image=num_questions_per_image,
                question_type=question_type,
            )
            if image_records:
                print(f"Generated {len(image_records)} questions from images.")
                records.extend(image_records)
            else:
                print("No questions were generated from the provided images.")
        return records

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
                 num_questions_per_image: int = 1,
                 question_type: str = "multiple_choice",
                 include_images: bool = False):
        """
        Runs the full question generation and review pipeline.
        """
        print("\n--- Starting Generation Pipeline ---")
        output_dir = os.path.dirname(os.path.abspath(output_md_path))
        self.start_llm_log(output_dir, "generate", inputs=list(input_material_paths or []) + list(image_paths or []))

        # 1. Parse Input Material
        text_content = ""
        extracted_image_paths: List[str] = []
        if input_material_paths:
            print("\nStep 1: Parsing input material...")
            text_content, extracted_image_paths = _parse_input_materials(input_material_paths, output_dir)

        # If there's no text, no images and no generator instructions, there's nothing to work with
        if not text_content and not image_paths and not generator_instructions:
            logging.critical("No text could be extracted from input files, no images were provided, and no generator instructions were given. Cannot generate questions.")
            sys.exit(1)

        if not text_content:
            source = "images" if image_paths else "generator instructions"
            print(f"\nStep 1: Parsing input material... (No text content found, proceeding with {source} only)")

        # 2. Generate Questions
        question_records = self._generate_records(
            text_content, image_paths, extracted_image_paths, input_material_paths, num_questions, language,
            generator_instructions, num_questions_per_image, question_type, include_images)

        if not question_records:
            logging.error("No questions were generated. Halting pipeline.")
            print("Error: Failed to generate any questions.", file=sys.stderr)
            artifacts.write_artifacts([], output_md_path, output_tsv_path) # Write empty artifacts
            raise RuntimeError("Failed to generate any questions.")

        print(f"Generated {len(question_records)} questions.")

        # 3. Initial Evaluation
        self._evaluate_stage(question_records, QuestionStage.GENERATED, evaluate_initial,
                             "Step 3: Evaluating initial questions", "Initial evaluation complete.",
                             evaluator_instructions, language)

        # 4. Review Questions
        print("\nStep 4: Reviewing questions...")
        question_records = self.reviewer.review_questions(
            question_records,
            custom_instructions=reviewer_instructions
        )
        print("Automated review complete.")

        # 5. Reviewed Evaluation
        self._evaluate_stage(question_records, QuestionStage.REVIEWED, evaluate_reviewed,
                             "Step 5: Evaluating reviewed questions", "Reviewed evaluation complete.",
                             evaluator_instructions, language)

        # 7. Write final artifacts
        print("\nStep 7: Writing artifacts...")
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
               font_size: str = '9pt',
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
               custom_header: Optional[str] = None,
               mc_total_points: Optional[float] = None,
               fill_answer_space: bool = False,
               show_points: str = "auto"
               ):
        """
        Runs the export part of the pipeline.
        """
        print(f"\n--- Starting Export Pipeline from {input_md_path} ---")

        if evaluate_final:
            self.start_llm_log(os.path.dirname(os.path.abspath(input_md_path)), "export --evaluate-final", inputs=[input_md_path])
        self._evaluate_stage(records_to_export, QuestionStage.FINAL, evaluate_final,
                             "Evaluating final questions", "Final evaluation complete.",
                             evaluator_instructions, language)

        questions_for_conversion = records_to_export
        if num_final_questions is not None and 0 < num_final_questions < len(questions_for_conversion):
            print(f"Selecting random subset of {num_final_questions} questions...")
            # Use seed if provided for deterministic selection, otherwise global random
            rng = random.Random(shuffle_questions_seed) if shuffle_questions_seed is not None else random
            questions_for_conversion = rng.sample(questions_for_conversion, num_final_questions)

        if output_formats == ["none"]:
            print("Output format is 'none', skipping file generation.")
            print("\n--- Export Pipeline Finished ---")
            return

        base_filename = os.path.splitext(os.path.basename(input_md_path))[0]
        output_dir_for_conversions = os.path.dirname(input_md_path) or "."
        md_base_dir = os.path.dirname(os.path.abspath(input_md_path))

        pexam_questions_base = pexams_converter.convert_ptestgen_to_pexam(
            records=questions_for_conversion,
            input_md_path=input_md_path,
            max_image_width=max_image_width,
            max_image_height=max_image_height
        )

        # Every format of this run uses the same seeds. No question seed means "keep the author's
        # order" (as documented and as pexams interprets None).
        effective_a_seed = shuffle_answers_seed if shuffle_answers_seed is not None else 42

        for fmt in output_formats:
            print(f"Exporting to format: {fmt}")
            utils.set_seeds(seed_questions=shuffle_questions_seed, seed_answers=effective_a_seed)
            # Always work on a copy to avoid side effects (e.g. pexams modifying the list in place)
            questions_to_export = copy.deepcopy(pexam_questions_base)

            if fmt == 'pexams':
                output_dir = os.path.join(output_dir_for_conversions, f"{base_filename}_pexams_output")
                os.makedirs(output_dir, exist_ok=True)
                # generate_exams shuffles internally using the global seeds
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
                    custom_header=custom_header,
                    markdown_asset_base_dir=md_base_dir,
                    mc_total_points=mc_total_points,
                    fill_answer_space=fill_answer_space,
                    show_points=show_points,
                )
                print(f"Pexams outputs generated in: {os.path.abspath(output_dir)}")
                continue

            exporter = FILE_EXPORTERS.get(fmt)
            if exporter is None:
                logging.error(f"Unknown format: {fmt}")
                continue
            # The other formats are shuffled here
            utils.shuffle_questions_list(questions_to_export)
            for q in questions_to_export:
                utils.shuffle_options_for_question(q)
            exporter(questions_to_export, os.path.join(output_dir_for_conversions, base_filename), md_base_dir)

        print("\n--- Export Pipeline Finished ---")
