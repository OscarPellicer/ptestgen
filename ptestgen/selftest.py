"""``ptestgen test``: an end-to-end run of every command on generated questions, to check for
runtime errors. It writes everything to ``generated_test/`` and needs an OpenRouter API key."""
import logging
import os
import sys

from ptestgen import artifacts

OUTPUT_DIR = "generated_test"
PROVIDER = "openrouter"
MODEL = "google/gemini-3.8-flash"  # a quick model for testing
NUM_QUESTIONS = 2
IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "image.jpg")
INSTRUCTIONS = r"This is a TEST RUN for the PTestGen library, a library that allows you to generate test questions from text or images using LLMs. Generate questions about Python programming. MAKE SURE to include at least one instance of all the formatting options in the questions and answers: **bold text**, *italic text*, `code`, $LaTeX_expression$ (such as $\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$)."


def _cli_args(argv, **overrides):
    """The namespace the real CLI would build for ``argv``, with ``overrides`` set on it."""
    from ptestgen.cli import build_parser
    args = build_parser().parse_args([str(a) for a in argv])
    vars(args).update(overrides)
    return args


def step_generate(output_dir: str) -> str:
    print(f"\n--- Step 1: Generating questions ({PROVIDER}) ---")
    md_path = os.path.join(output_dir, "openrouter_questions.md")
    argv = ["generate", "-o", md_path, "--generator-instructions", INSTRUCTIONS,
            "-n", NUM_QUESTIONS, "--provider", PROVIDER, "--use-llm-review", "--language", "es",
            "--evaluate-initial", "--evaluate-reviewed", "--num-questions-per-image", 1,
            "--question-type", "multiple_choice"]
    for role in ("generator", "reviewer", "evaluator"):
        argv += [f"--{role}-model", MODEL]
    if IMAGE_PATH:
        argv += ["-i", IMAGE_PATH]
    args = _cli_args(argv)
    args.func(args)
    return md_path


def step_split_merge_shuffle(output_dir: str, md_path: str) -> str:
    """Split the questions in three parts, merge them back and shuffle the result in place."""
    print("\n--- Step 2: Splitting test ---")
    split_dir = os.path.join(output_dir, "splits")
    args = _cli_args(["split", md_path, "--splits", "1", "1", "-1", "--output-dir", split_dir])
    args.func(args)

    print("\n--- Step 3: Merging tests ---")
    merged_md_path = os.path.join(output_dir, "merged_questions.md")
    split_files = [os.path.join(split_dir, f) for f in os.listdir(split_dir) if f.endswith('.md')]
    args = _cli_args(["merge", *split_files, "-o", merged_md_path])
    args.func(args)

    print("\n--- Step 4: Shuffling test ---")
    args = _cli_args(["shuffle", merged_md_path, "--seed", 42, "-y"])
    args.func(args)
    return merged_md_path


def step_simulate_edits(md_path: str) -> None:
    """Rename the first question and append "(modified)" to the text of the second, as a teacher
    reviewing the markdown would."""
    print("\n--- Step 5: Simulating manual edits ---")
    records = artifacts.read_metadata_tsv(artifacts.get_artifact_paths(md_path)[1])
    if len(records) <= 1:
        print("Not enough questions to simulate edits, skipping.")
        return

    id_to_change = records[0].question_id
    id_to_modify = records[1].question_id
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace(f"## {id_to_change}", f"## {id_to_change}_modified")

    q_start = content.find(f"## {id_to_modify}")
    if q_start != -1:
        q_end = content.find("\n## ", q_start + 1)
        if q_end == -1:
            q_end = len(content)
        first_answer = content.find("\n* ", q_start, q_end)
        if first_answer != -1:
            content = content[:first_answer] + " (modified)" + content[first_answer:]

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Applied edits to markdown file.")


def step_export(md_path: str) -> None:
    """Export to Wooclap (with final evaluation), Moodle XML and pexams (with fake scans)."""
    print("\n--- Step 6: Exporting to final formats ---")
    # No answer shuffling seed: the pipeline's default (42) for Wooclap and Moodle XML.
    common = {'shuffle_answers': None, 'exam_title': 'Test Exam', 'exam_course': 'PTestGen Course', 'exam_date': '2025-01-01',
              'num_models': 1, 'lang': 'en', 'font_size': '11pt', 'columns': 2}

    print("Exporting to Wooclap...")
    args = _cli_args(["export", "wooclap", md_path, "--evaluate-final", "--max-image-height", 300], **common)
    args.func(args)

    print("Exporting to Moodle XML...")
    args = _cli_args(["export", "moodle_xml", md_path, "--max-image-height", 300], **common)
    args.func(args)

    print("Exporting to pexams (with fakes)...")
    args = _cli_args(["export", "pexams", md_path, "--max-image-height", 300,
                      "--generate-fakes", 1, "--generate-references"],
                     **{**common, 'font_size': '10pt',
                        'shuffle_answers': 42,  # explicitly test deterministic answer shuffling
                        'custom_header': '## Instructions\nAnswer the questions carefully.'})
    args.func(args)


def step_correct_pexams(output_dir: str, md_path: str) -> None:
    """Correct the simulated scans of the pexams export and check that the statistics reach the TSV."""
    print("\n--- Step 7: Correcting pexams scans via ptestgen correct ---")
    base_name = os.path.splitext(os.path.basename(md_path))[0]
    exam_dir = os.path.join(output_dir, f"{base_name}_pexams_output")
    args = _cli_args(["correct", "pexams", md_path,
                      "--input-path", os.path.join(exam_dir, "simulated_scans"),
                      "--exam-dir", exam_dir,
                      "--output-dir", os.path.join(exam_dir, "correction_results"),
                      "--evaluate-final",  # test the evaluation after correction
                      "--lang", "en",
                      "--id-reader", "trocr"])  # local header reading, no LLM
    args.func(args)

    records = artifacts.read_metadata_tsv(artifacts.get_artifact_paths(md_path)[1])
    if any(r.stats_total_answers is not None for r in records):
        print("Verified: Statistics have been updated in the metadata TSV.")
    else:
        print("WARNING: Statistics were NOT updated in the metadata TSV (this might be expected if pexams fakes were skipped, but fakes were enabled).")


def step_evaluate_missing(md_path: str) -> None:
    print("\n--- Step 8: Testing evaluate command ---")
    args = _cli_args(["evaluate", md_path, "--language", "en", "--missing-only"])
    args.func(args)


def _write_synthetic_questions(test_dir: str) -> str:
    """Two multiple-choice questions written without an LLM."""
    from ptestgen.schemas import QuestionContent, QuestionRecord, QuestionStageContent

    def reviewed(text, correct, distractors):
        return QuestionStageContent(content=QuestionContent(text=text, correct_answer=correct, distractors=distractors))

    records = [
        QuestionRecord(question_id="q_test_001", reviewed=reviewed("What is 2 + 2?", "4", ["3", "5", "22"])),
        QuestionRecord(question_id="q_test_002", reviewed=reviewed("Capital of France?", "Paris", ["Berlin", "Madrid", "Rome"])),
    ]
    md_path = os.path.join(test_dir, "questions.md")
    artifacts.write_artifacts(records, md_path, os.path.join(test_dir, "questions.tsv"))
    return md_path


def _correct_online(source: str, md_path: str, results, out_dir: str, *extra) -> None:
    """Run ``correct <source>`` on a results table and check that both students were graded."""
    import pandas as pd
    results_path = os.path.join(os.path.dirname(md_path), f"{source}_results.csv")
    pd.DataFrame(results).to_csv(results_path, index=False)
    args = _cli_args(["correct", source, md_path, "--results", results_path, "--output-dir", out_dir,
                      "--lang", "en", "--no-generate-report", *extra])
    args.func(args)

    correction_csv = os.path.join(out_dir, "correction_results.csv")
    label = source.capitalize()
    if not os.path.exists(correction_csv):
        raise RuntimeError(f"{label}: correction_results.csv was not created.")
    df = pd.read_csv(correction_csv)
    assert len(df) == 2, f"{label}: expected 2 students, got {len(df)}"
    print(f"{label} correction OK — {len(df)} student(s) processed.")


def step_correct_online(output_dir: str) -> None:
    print("\n--- Step 9: Testing online correction (wooclap & moodle) ---")
    test_dir = os.path.join(output_dir, "online_correction_test")
    os.makedirs(test_dir, exist_ok=True)
    md_path = _write_synthetic_questions(test_dir)

    _correct_online("wooclap", md_path, {
        "Alumno": ["1", "2"],
        "Q1 - What is 2 + 2? (1 pts)": ["V - 4", "X - 3"],
        "Q2 - Capital of France? (1 pts)": ["V - Paris", "X - Berlin"],
        "Total": ["2 / 2", "0 / 2"],
    }, os.path.join(test_dir, "wooclap_output"), "--fuzzy-threshold", 80)

    _correct_online("moodle", md_path, {
        "Cognoms": ["Smith", "Jones"],
        "Nom": ["Alice", "Bob"],
        "Resposta 1": ["4", "3"],
        "Resposta 2": ["Paris", "Berlin"],
    }, os.path.join(test_dir, "moodle_output"))


def handle_test(args):
    """Handler for the 'test' command."""
    logging.info("Running TEST command...")
    output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    print(f"Test artifacts will be saved in '{os.path.abspath(output_dir)}'")

    try:
        md_path = step_generate(output_dir)
        merged_md_path = step_split_merge_shuffle(output_dir, md_path)
        step_simulate_edits(merged_md_path)
        step_export(merged_md_path)
        step_correct_pexams(output_dir, merged_md_path)
        step_evaluate_missing(merged_md_path)
        step_correct_online(output_dir)
        print("\n--- Test command finished successfully! ---")
    except Exception as e:
        logging.error(f"Test command failed: {e}", exc_info=True)
        print(f"\n--- ERROR: Test command failed ---\n{e}\n")
        sys.exit(1)
