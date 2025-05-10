# AutoTestIA

AutoTestIA is a Python-based tool designed to assist educators in generating multiple-choice quizzes (tests) from educational materials or specific instructions using Large Language Models (LLMs). It aims to streamline the quiz creation process, saving time and potentially improving question quality.

## Project Goal

To develop and evaluate an AI-powered tool (AutoTestIA) for semi-automatic generation of multiple-choice questions via intelligent agents, integrated into an efficient, user-friendly Python pipeline adaptable to various educational platforms (Moodle, Wooclap, R/exams).

## Core Features

*   **LLM Integration:** Supports multiple providers:
    *   OpenAI (e.g., GPT-4o)
    *   Google (e.g., Gemini 2.5)
    *   Anthropic (e.g., Claude 3.7 Sonnet, Claude 3.7 Haiku)
    *   Replicate (e.g., Llama 3.2)
*   **Flexible Input:**
    *   **Document-Based Generation (OE1):** Generate questions from text documents (**TXT, MD, PDF, DOCX, PPTX, RTF supported for text extraction**) and images (PNG, JPG, GIF, BMP). PDF/DOCX/PPTX parsing requires installing optional dependencies. Image extraction *from within documents* is experimental.
    *   **Instruction-Based Generation:** Generate questions based on specific instructions provided via the command line, without requiring an input document.
*   **Customizable Prompts:** Add custom instructions to the underlying LLM prompts for generation and review using `--generator-instructions` and `--reviewer-instructions`.
*   **Automated Review (OE2):** Rule-based checks and optional LLM-based review for quality criteria (clarity, distractor plausibility, etc.).
*   **Manual Review Workflow (OE3):** Outputs questions in a clean Markdown format for easy verification and editing by the educator. Can be skipped via CLI flag.
*   **Format Conversion (OE4):** Converts the finalized questions into formats compatible with Moodle (XML/GIFT), Wooclap (Placeholder), and R/exams (.Rmd structure).
*   **Question Shuffling & Selection:**
    *   Shuffle the order of generated questions (`--shuffle-questions`).
    *   Shuffle the order of answers within each question (`--shuffle-answers`).
    *   Select a random subset of the final questions (`--num-final-questions`).
*   **Integrated Pipeline (OE5):** A cohesive Python script orchestrates the entire process.
*   *(Future)* Evaluation Agent (OE6)
*   *(Future)* Dynamic Question Support (OE7)
*   *(Future)* Humorous Distractor Option (OE8)

## Current Status

Core pipeline implemented with support for major LLM providers. Text parsing handles various formats. Image-based generation and LLM review are functional. Output converters for Moodle XML, GIFT, and R/exams structure are implemented. Wooclap is a placeholder. Instruction-based generation, shuffling, and selection are implemented. Error handling is basic.

## Setup

1.  Clone the repository:
    ```bash
    git clone https://github.com/OscarPellicer/AutoTestIA.git
    cd AutoTestIA
    ```
2.  (Recommended) Create and activate a virtual environment:
    ```bash
    python -m venv venv
    # On Windows: venv\Scripts\activate
    # On macOS/Linux: source venv/bin/activate
    ```
3.  Install required dependencies and the package in editable mode:
    ```bash
    # Core dependencies will be installed by the next command
    pip install -e .
    ```
4.  **Configure API Keys:**
    *   Rename the `.env.example` file to `.env`.
    *   Edit the `.env` file and add your API keys for the LLM providers you intend to use.
    ```dotenv
    # .env file contents example
    OPENAI_API_KEY="sk-..."
    GOOGLE_API_KEY="AIza..."
    ANTHROPIC_API_KEY="sk-ant-..."
    REPLICATE_API_TOKEN="r8_..."
    ```
    *   **IMPORTANT:** Do not commit the `.env` file to version control. The `.gitignore` file is configured to prevent this.
5.  (Optional) You can set the default provider and models directly in the `.env` file as well (though this can also be done via arguments when running `autotestia`):
    ```dotenv
    # Optional defaults in .env
    LLM_PROVIDER="openai"
    OPENAI_GENERATOR_MODEL="gpt-4o"
    # etc.
    ```

## Usage

**Commands:**

*   `autotestia`: Main command to generate questions from documents or instructions.
*   `autotestia_split`: Command to split an existing Markdown question file into multiple smaller files.
*   `autotestia_correct`: Command to correct R/exams NOPS scans.

### `autotestia`: Generate questions from a document or instructions

1.  **Generate from Document:**
    ```bash
    autotestia <input_material_path> [options]
    ```
    Use this mode to generate questions from a source document.

2.  **Generate from Instructions:**
    ```bash
    autotestia --generator-instructions "Create questions about..." [options]
    ```
    Use this mode when you don't have a specific document but want to generate questions based on a topic or instructions. The `input_material_path` argument is omitted.

3.  **Resume from Markdown:**
    ```bash
    autotestia --resume-from-md <existing_markdown_path> [options]
    ```
    Use this mode to continue processing from an existing intermediate Markdown file (e.g., after manual review or if the process was interrupted). This skips the initial generation, LLM review, and manual review steps.

#### Examples for `autotestia`

1.  **Generate 5 questions using OpenAI from a text file, output to default paths, request Moodle XML and GIFT:**
    ```bash
    # Make sure OPENAI_API_KEY is in .env
    autotestia path/to/your/notes.txt -n 5
    ```
    *   Creates `output/questions.md`. Press Enter after reviewing (unless `--skip-manual-review`).
    *   Then creates `output/moodle_questions.xml` and `output/gift_questions.gift`.

2.  **Generate 3 questions using Google Gemini, include an image, enable LLM review, skip manual review, output R/exams format:**
    ```bash
    # Make sure GOOGLE_API_KEY is in .env
    autotestia course_material.txt -n 3 -i diagram.png --provider google --use-llm-review --skip-manual-review -f rexams -o generated/google_review.md
    ```
    *   Creates `generated/google_review.md`.
    *   Immediately creates R/exams files in `generated/rexams/`.

3.  **Generate 10 questions based *only* on instructions using Anthropic, shuffle questions and answers (fixed seed), select 5 final questions, output to GIFT:**
    ```bash
    # Make sure ANTHROPIC_API_KEY is in .env
    autotestia --generator-instructions "Generate multiple-choice questions about the main features of Python 3.12." -n 10 --provider anthropic --shuffle-questions 42 --shuffle-answers 42 --num-final-questions 5 -f gift -o output/python_features.md
    ```
    *   Creates `output/python_features.md` (containing 10 questions).
    *   Creates `output/python_features.gift` (containing 5 randomly selected, shuffled questions).

4.  **Generate only the intermediate Markdown file from a PDF, adding custom instructions:**
    ```bash
    autotestia study_guide.pdf -n 15 -f none -o draft_questions.md --generator-instructions "Focus on chapter 3."
    ```
    *   Creates `draft_questions.md` and stops.

5.  **Resume processing from a previously generated/edited Markdown file, shuffle questions (random seed), convert to GIFT:**
    ```bash
    autotestia --resume-from-md draft_questions.md -f gift --shuffle-questions
    ```
    *   Parses `draft_questions.md`.
    *   Creates `draft_questions.gift` in the same directory containing all questions from the MD file but in a shuffled order.

#### Command Line Options for `autotestia`

*   **Input Control:**
    *   `input_material`: (Optional) Path to the input file (e.g., `.txt`, `.pdf`) for *new generation*. If omitted, generation relies on 
    `--generator-instructions`. Cannot be used with `--resume-from-md`.
    *   `--resume-from-md`: Path to an existing intermediate Markdown file to *resume processing from* (skips generation and initial review steps). 
    Cannot be used with `input_material`.

*   **Generation Input & Control (Ignored if resuming):**
    *   `--generator-instructions`: Custom instructions to add to the generator prompt. Essential if `input_material` is omitted.
    *   `--reviewer-instructions`: Custom instructions to add to the reviewer prompt (if LLM review is enabled).
    *   `-i`, `--images`: Optional path(s) to image file(s).
    *   `-n`, `--num-questions`: Number of questions to generate (default: 5).
    *   `-o`, `--output-md`: Path for the intermediate Markdown file (default: `output/questions.md`).
    *   `--provider`: LLM provider (choices: `openai`, `google`, `anthropic`, `replicate`, `stub`, default: from `.env` or `stub`).
    *   `--generator-model`: Override default generator model for the provider.
    *   `--reviewer-model`: Override default reviewer model for the provider.
    *   `--use-llm-review` / `--no-use-llm-review`: Enable/disable LLM-based review agent.
    *   `--skip-manual-review`: Skip the pause for manual Markdown editing.
    *   `--extract-doc-images`: [Experimental] Attempt to extract images from documents (requires `input_material`).
    *   `--language`: Language for questions (default: `en`).
*   **Output & Formatting Control:**
    *   `-f`, `--formats`: Final output format(s) (choices: `moodle_xml`, `gift`, `wooclap`, `rexams`, `none`. Default: `moodle_xml gift`). Use `none` to 
    only output the intermediate Markdown.
    *   `--shuffle-questions [SEED]`: Shuffle the order of questions after Markdown parsing. Provide an optional integer seed for reproducibility. If 
    seed is omitted, uses a random seed.
    *   `--shuffle-answers [SEED]`: Shuffle the order of answers within each question. Provide an optional integer seed. If omitted or 0, shuffles 
    randomly per run.
    *   `--num-final-questions N`: Randomly select `N` questions from the final set (after potential shuffling). If omitted, all questions are used.
*   **General Options:**
    *   `--log-level`: Set logging verbosity (choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, default: `WARNING`).

*   **R/exams Options:**
    *   `--rexams-title`: Custom title for R/exams PDF output. If not set, uses R script's default.
    *   `--rexams-course`: Custom course name for R/exams PDF output. If not set, uses R script's default.

### `autotestia_split`: Split a question file into multiple smaller files

Split `all_questions.md` into three files: the first with 10 questions, the second with 25% of the total questions (shuffled), and the third with all remaining questions. Output files will be named `all_questions_1.md`, `all_questions_2.md`, etc., in the `output/custom_splits` directory.
```bash
autotestia_split all_questions.md --splits 10 0.25 -1 --output-dir output/custom_splits --shuffle-questions 123
```

### `autotestia_correct`: Correct R/exams NOPS Scans

The `autotestia_correct` command (wrapping `autotestia/rexams/correct_exams.py`) provides a command-line interface to automate the correction of scanned R/exams NOPS answer sheets. It wraps an R script (`run_autocorrection.R`) that performs the core operations: PDF splitting (optional), scanning marks using `nops_scan()`, preparing student registration data, and evaluating exams using `nops_eval()`.

#### Example for `autotestia_correct`:

```bash
# Ensure R and necessary R packages (exams, qpdf, optparse) are installed.
autotestia_correct \
    --all-scans-pdf path/to/your/all_scans_concatenated.pdf \
    --split-pages \
    --scans-dir ./scanned_exam_pages \
    --student-info-csv path/to/your/student_data.csv \
    --solutions-rds path/to/your/generated_rexams_output/exam.rds \
    --output-basename ./correction_output/exam_results \
    --language en \
    --max-score 45 \
    --scale-mark-to 10
```

This command would:
1.  Split `all_scans_concatenated.pdf` into individual page PDFs in `./scanned_exam_pages/`.
2.  Scan these pages.
3.  Process `student_data.csv` to match the format required by `nops_eval`.
4.  Evaluate the exams using solutions from `exam.rds`.
5.  Save results (e.g., `exam_results.csv`, `exam_results.rds`, `exam_results_scaled_to_10.csv`) in `./correction_output/`.
6.  Scale the marks based on a maximum possible score of 45 to a new scale up to 10.

#### Command Line Options for `autotestia_correct`:

*   **Input Files/Directories:**
    *   `--all-scans-pdf`: Path to a single PDF containing all scanned exam sheets (required if `--split-pages` is used).
    *   `--scans-dir`: Directory for individual scanned exam pages (output of splitting, input for `nops_scan`). (Required)
    *   `--student-info-csv`: Path to your CSV file containing student information. (Required)
        *   The script expects certain column names by default (e.g., `'Número.de.Identificación'`, `'Nombre'`, `'Apellidos'`, `'ID.Usuario'`). These can be configured using `--student-csv-*` arguments.
        *   The student registration number read from this CSV will be formatted using `--registration-format` (default: `"%08s"`) before matching with scanned data.
    *   `--solutions-rds`: Path to the `exam.rds` file generated during R/exams creation (e.g., by `exams2nops` or the `generate_exams.R` script). (Required)
*   **Output Configuration:**
    *   `--output-basename`: Basename for the output files (e.g., `results/my_exam_corrected` will produce `results/my_exam_corrected.csv`, `.rds`, etc.). (Required)
    *   `--processed-register-filename`: Filename for the intermediate student registration CSV created by the script (default: `processed_student_register.csv`).
*   **R Environment & Language:**
    *   `--r-executable`: Path to the `Rscript` executable. If omitted, the script attempts to find it automatically.
    *   `--language`: Language for `nops_eval` (e.g., `en`, `es`, `ca`; default: `en`).
*   **Scanning & Evaluation Parameters:**
    *   `--scan-thresholds`: Comma-separated pair for scan thresholds (e.g., `"0.04,0.42"`).
    *   `--partial-eval` / `--no-partial-eval`: Enable/disable partial scoring (default: enabled).
    *   `--negative-points`: Penalty for incorrect answers (default: -1/3).
    *   `--max-score`: Maximum raw score of the exam (e.g., 44). Needed if you want to scale the final mark.
    *   `--scale-mark-to`: Target score to scale the final mark to (e.g., 10; default: 10.0).
*   **PDF Splitting:**
    *   `--split-pages` / `--no-split-pages`: Enable splitting of `--all-scans-pdf` (default: disabled).
    *   `--force-split` / `--no-force-split`: If splitting, force overwrite of existing split pages (default: disabled).
*   **Student CSV Customization:**
    *   `--student-csv-id-col`: Column name for the unique student ID (e.g., username).
    *   `--student-csv-reg-col`: Column name for the registration number (ID written on the exam sheet).
    *   `--student-csv-name-col`: Column name for student's first name.
    *   `--student-csv-surname-col`: Column name for student's surname.
    *   `--student-csv-encoding`: Encoding of your input student CSV file (default: `UTF-8`).
    *   `--registration-format`: `sprintf`-style format string for the registration number (default: `"%08s"`).

## Next Steps / TODO

*   Test all the output formats (only Wooclap and R/Exams have been tested so far)
*   Test robust parsing for PDF, DOCX in `input_parser/parser.py` (only PPTX and text formats have been tested so far)
*   Test image extraction from documents
*   Test passing custom images for questions
*   Develop evaluation metrics and agent (OE6).
*   Explore dynamic questions (OE7) and humorous distractors (OE8).
*   Consider adding support for self-hosted models.
*   Refactor, e.g. shared LLM logic (client init, retry, parsing) into a utility module.
