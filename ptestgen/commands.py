"""Handlers of ``ptestgen generate`` and ``ptestgen export``."""
import logging
import os
import sys

from ptestgen import artifacts, config


def _generate_config_override(args) -> dict:
    """Pipeline configuration from the ``generate`` flags: provider, the three models (the
    provider's defaults when not given), review flag, API key variable and effort."""
    provider = args.provider
    override = {"llm_provider": provider}
    model_maps = {
        "generator_model": config.GENERATOR_MODEL_MAP,
        "reviewer_model": config.REVIEWER_MODEL_MAP,
        "evaluator_model": config.EVALUATOR_MODEL_MAP,
    }
    for key, model_map in model_maps.items():
        override[key] = getattr(args, key) or model_map.get(provider, f"stub-{key}")
    # Override the review flag only if explicitly set
    if args.use_llm_review != config.DEFAULT_LLM_REVIEW_ENABLED:
        override["use_llm_review"] = args.use_llm_review
    override["api_key_env"] = args.api_key_env
    override["effort"] = args.effort
    return override


def _check_api_key(provider: str, api_key_env) -> None:
    """Exit with an error if a real provider is selected and its API key is not set."""
    if provider == "stub":
        return
    api_key_var = api_key_env or config.PROVIDER_API_KEY_MAP.get(provider)
    if not api_key_var or not os.getenv(api_key_var):
        print(f"Error: Provider '{provider}' selected, but its API key ({api_key_var}) was not found in .env or environment variables.", file=sys.stderr)
        sys.exit(1)


def handle_generate(args):
    """Handler for the 'generate' command."""
    logging.info("Running GENERATE command...")

    if not args.input_material and not args.generator_instructions:
        logging.warning("Generating without an input file or specific generator instructions. Relying on default prompts.")
        print("Warning: No input file or --generator-instructions provided. Generation might be generic.", file=sys.stderr)

    config_override = _generate_config_override(args)
    _check_api_key(args.provider, args.api_key_env)

    md_path, tsv_path = artifacts.get_artifact_paths(args.output_md_path)
    from ptestgen.pipeline import PTestGenPipeline
    pipeline = PTestGenPipeline(config_override=config_override)
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
        num_questions_per_image=args.num_questions_per_image,
        question_type=args.question_type,
        include_images=args.include_images,
    )


def _is_removed(record) -> bool:
    return any(change and change.status == "removed"
               for change in (record.changes_rev_to_man, record.changes_gen_to_rev))


def _export_options(args) -> dict:
    """Keyword arguments of ``PTestGenPipeline.export`` from the flags of any export format
    (the exam and pexams flags only exist for some formats)."""
    def opt(name, default=None):
        return getattr(args, name, default)

    return dict(
        output_formats=[args.format],
        shuffle_questions_seed=args.shuffle_questions,
        shuffle_answers_seed=args.shuffle_answers,
        num_final_questions=args.num_final_questions,
        evaluate_final=args.evaluate_final,
        evaluator_instructions=opt("evaluator_instructions"),
        exam_title=opt("exam_title"),
        exam_course=opt("exam_course"),
        exam_date=opt("exam_date"),
        exam_models=opt("num_models", opt("exam_models", 1)),
        language=opt("lang", opt("exam_language", config.DEFAULT_LANGUAGE)),
        font_size=opt("font_size", "9pt"),
        columns=opt("columns", 1),
        generate_fakes=opt("generate_fakes", 0),
        generate_references=opt("generate_references", False),
        total_students=opt("total_students", 0),
        extra_model_templates=opt("extra_model_templates", 0),
        keep_html=opt("keep_html", False) or opt("log_level") == 'DEBUG',
        max_image_width=opt("max_image_width"),
        max_image_height=opt("max_image_height"),
        custom_header=opt("custom_header"),
        mc_total_points=opt("mc_total_points"),
        fill_answer_space=opt("fill_answer_space", False),
        show_points=opt("show_points", "auto"),
    )


def handle_export(args):
    """Handler for the 'export' command."""
    logging.info(f"Running EXPORT command from file: {args.input_md_path}")

    md_path, tsv_path = artifacts.get_artifact_paths(args.input_md_path)
    if not os.path.exists(md_path):
        logging.error(f"Questions markdown file not found: {md_path}")
        sys.exit(1)

    # A hand-written markdown has no metadata yet: start from no records and let the
    # synchronization below add every question as new; the TSV is written at the end.
    if os.path.exists(tsv_path):
        records = artifacts.read_metadata_tsv(tsv_path)
    else:
        logging.info(f"Metadata file not found, it will be created from the markdown: {tsv_path}")
        records = []
    synced_records = artifacts.synchronize_artifacts(records, artifacts.read_questions_md(md_path))
    records_to_export = [rec for rec in synced_records if not _is_removed(rec)]

    if not records_to_export:
        logging.warning("No valid questions remaining after synchronization. Nothing to export.")
        artifacts.write_metadata_tsv(synced_records, tsv_path)
        return

    config_override = {}
    if getattr(args, "evaluator_model", None):
        config_override["evaluator_model"] = args.evaluator_model

    from ptestgen.pipeline import PTestGenPipeline
    pipeline = PTestGenPipeline(config_override=config_override)
    pipeline.export(records_to_export=records_to_export, input_md_path=md_path, **_export_options(args))

    artifacts.write_metadata_tsv(synced_records, tsv_path)
    print(f"Metadata file at '{tsv_path}' has been updated with manual review changes.")
