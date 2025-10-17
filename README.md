# AutoTestIA

AutoTestIA is a Python-based tool designed to assist educators in generating multiple-choice quizzes (tests) from educational materials or specific instructions using Large Language Models (LLMs). It aims to streamline the quiz creation process, saving time and potentially improving question quality.

## Project Goal

To develop and evaluate an AI-powered tool (AutoTestIA) for semi-automatic generation of multiple-choice questions via intelligent agents, integrated into an efficient, user-friendly Python pipeline adaptable to various educational platforms (Moodle, Wooclap, R/exams).

## Core Features

*   **LLM Integration:** Supports multiple providers:
    *   **OpenRouter (Recommended):** Access a wide variety of models from different providers with a single API key. Simplifies configuration and allows for easy model switching.
    *   **Ollama (e.g., Llama 3.1):** Supports structured output.
    *   OpenAI (e.g., GPT-4o, GPT-5)
    *   Google (e.g., Gemini 2.5 Pro, Gemini 2.5 Flash)
    *   Anthropic (e.g., Claude 4.5 Sonnet, Claude 4.5 Haiku): *Discouraged due to structured output not being supported.*
    *   Replicate (e.g., Llama 3.2): *Discouraged due to structured output not being supported.*
*   **Flexible Input:**
    *   **Document-Based Generation (OE1):** Generate questions from text documents (**TXT, MD, PDF, DOCX, PPTX, RTF supported for text extraction**) and images (PNG, JPG, GIF, BMP). PDF/DOCX/PPTX parsing requires installing optional dependencies. Image extraction *from within documents* is experimental.
    *   **Instruction-Based Generation:** Generate questions based on specific instructions provided via the command line, without requiring an input document.
*   **Customizable Prompts:** Add custom instructions to the underlying LLM prompts for generation and review using `--generator-instructions` and `--reviewer-instructions`.
*   **Automated Review (OE2):** An LLM-based agent refines questions for clarity, correctness, and adherence to pedagogical best practices.
*   **Automated Evaluation (OE6):** An optional, separate LLM-based agent evaluates questions against multiple criteria:
    *   **Difficulty Score:** How challenging the question is.
    *   **Pedagogical Value:** How well it tests key concepts.
    *   **Clarity:** How clear the question and options are.
    *   **Distractor Plausibility:** How convincing the incorrect answers are.
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
    OPENROUTER_API_KEY="sk-or-..." # Recommended, can handle most models with a single API key
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
6.  **(For R/exams Users) Install R, LaTeX, and Required R Packages:**
    To utilize the R/exams output format (which produces `.pdf` files) or to use the `autotestia_correct` command for correcting R/exams NOPS scans, you must have R and a LaTeX distribution installed on your system. The helper R scripts also require specific R packages.

    *   **Install R:** Download and install R from [The Comprehensive R Archive Network (CRAN)](https://cran.r-project.org/).
    *   **Install LaTeX:** A LaTeX distribution is required for R/exams to compile `.Rmd` files into PDF documents.
        *   We recommend [TinyTeX](https://yihui.org/tinytex/), a lightweight and easy-to-install LaTeX distribution. You can install it from within R by first installing the `tinytex` R package (`install.packages("tinytex")`) and then running `tinytex::install_tinytex()`.
        *   Alternatively, you can use other LaTeX distributions like MiKTeX (Windows), MacTeX (macOS), or TeX Live (Linux).
    *   **Install Required R Packages:** After installing R, open the R console and install the following packages. While the provided R scripts (`autotestia/rexams/generate_exams.R` and `autotestia/rexams/run_autocorrection.R`) attempt to install missing packages, it's best to install them beforehand:
        ```R
        install.packages(c("exams", "optparse", "knitr", "qpdf"))
        ```
        *   `exams`: The core package for all R/exams functionality.
        *   `optparse`: Used by the helper R scripts for parsing command-line arguments.
        *   `knitr`: Used by `autotestia/rexams/generate_exams.R` (for R/exams PDF generation) for processing R Markdown files.
        *   `qpdf`: Used by `autotestia/rexams/run_autocorrection.R` (for `autotestia_correct`) for splitting PDF files if R handles the splitting.
        *   The `autotestia_correct` command (and its underlying Python PDF processing option `--split-pages`) also has Python dependencies like `PyPDF2`, `pdf2image`, and `opencv-python` which are part of the main package install, but Poppler is an external dependency for `pdf2image`.

**Note on parsing `.pptx` files (untested, WIP)**

Unfortunately, the `python-pptx` library in charge of parsing `.pptx` files does not correctly parse MathML equations. This has been solved in my fork of the library: https://github.com/OscarPellicer/python-pptx.

To use it, you need to install this version AFTER installing everything else:

```bash
pip install git+https://github.com/OscarPellicer/python-pptx.git
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

1.  **Generate questions from PowerPoint presentation with custom instructions:**
    ```bash
    # Make sure OPENROUTER_API_KEY is in .env
    autotestia path/to/presentation.pptx \
        -n 4 \
        --provider openrouter \
        --generator-model google/gemini-2.5-pro \
        --reviewer-model google/gemini-2.5-flash \
        --evaluator-model google/gemini-2.5-flash \
        --evaluate-initial \
        --evaluate-reviewed \
        --use-llm-review \
        -f none \
        -o generated/topic_questions.md \
        --language Spanish \
        --generator-instructions "Create questions about the specifics of LDA, LSA / LSI"
    ```
    *   Creates `generated/topic_questions.md` with 4 questions focused on specific topics.
    *   Uses LLM review for quality assurance.
    *   Create only the intermediate Markdown file: you will need to run the pipeline again to get the final output (see below)

2.  **Generate questions from Markdown file with custom instructions:**
    ```bash
    # Make sure ANTHROPIC_API_KEY is in .env
    autotestia path/to/course_notes.md \
        -n 10 \
        --provider openrouter \
        --generator-model google/gemini-2.5-pro \
        --reviewer-model google/gemini-2.5-flash \
        --evaluator-model google/gemini-2.5-flash \
        --evaluate-initial \
        --evaluate-reviewed \
        --use-llm-review \
        -f none \
        -o generated/course_questions.md \
        --language Spanish \
        --reviewer-model claude-sonnet-4-5 \
        --language Spanish \
        --generator-instructions "Create questions about the specifics of LDA, LSA / LSI"
    ```
    *   Creates `generated/course_questions.md` with 10 questions from course material.
    *   Uses both generator and reviewer models for quality control and evaluation.

3.  **Generate questions based only on instructions (no input file):**
    ```bash
    # Make sure ANTHROPIC_API_KEY is in .env
    autotestia \
        -n 6 \
        -o generated/python_regex_questions.md \
        --provider openrouter \
        --generator-instructions "Generate multiple-choice questions specifically about Python regular expressions using the 're' module. Focus on questions requiring either synthesis (writing a regex pattern based on a description) or analysis (determining what a given regex pattern matches or does). Cover common concepts like character classes, quantifiers, grouping, anchors, lookarounds, and standard 're' functions (e.g., search, match, findall, sub)." \
        --use-llm-review \
        --reviewer-instructions "Ensure questions accurately test Python regex synthesis or analysis as requested. Verify the correctness of regex patterns, expected matches, and explanations. Ensure distractors are plausible but incorrect applications or interpretations of regex concepts." \
        --language Spanish \
        -f none
    ```
    *   Creates `generated/python_regex_questions.md` with 6 Python regex questions.
    *   Uses custom instructions for both generation and review.
    *   Questions are generated in Spanish.

4.  **Resume from Markdown file and convert to Wooclap format:**
    ```bash
    autotestia \
        --resume-from-md generated/questions.md \
        -f wooclap \
        --shuffle-questions 123 \
        --shuffle-answers 123
        --evaluate-final
    ```
    *   Parses existing `generated/questions.md` file.
    *   Creates Wooclap-compatible output with shuffled questions and answers.
    *   Uses fixed seed (123) for reproducible shuffling.

5.  **Resume from Markdown file and convert to R/Exams format:**
    ```bash
    autotestia \
        --resume-from-md generated/exam_questions.md \
        -f rexams \
        --rexams-title "Natural Language Processing - Final Exam" \
        --rexams-course "Data Science Degree" \
        --shuffle-answers 123 \
        --log-level DEBUG \
        --rexams-date "2025-06-05"
    ```
    *   Parses existing `generated/exam_questions.md` file.
    *   Creates R/Exams format with custom title, course, and date.
    *   Shuffles answers with fixed seed for consistency.

6.  **Other example (would not use this in practice): generate questions with image input and R/exams output directly without reviewing:**
    ```bash
    # Make sure OPENROUTER_API_KEY is in .env
    autotestia course_material.txt \
        -n 3 \
        -i diagram.png \
        --provider openrouter \
        --use-llm-review \
        --skip-manual-review \
        -f rexams \
        -o generated/openrouter_review.md
    ```
    *   Uses an image input
    *   Creates `generated/openrouter_review.md`.
    *   Immediately creates R/exams files in `generated/rexams/`.

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
    *   `--provider`: LLM provider (choices: `openai`, `google`, `anthropic`, `replicate`, `openrouter`, `stub`, default: from `.env` or `openrouter`).
    *   `--generator-model`: Override default generator model for the provider.
    *   `--reviewer-model`: Override default reviewer model for the provider.
    *   `--evaluator-model`: Override default evaluator model for the provider.
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
*   **Evaluation Control:**
    *   `--evaluator-instructions`: Custom instructions to add to the evaluator prompt.
    *   `--evaluate-initial`: Run the evaluator on questions immediately after they are generated.
    *   `--evaluate-reviewed`: Run the evaluator on questions after they have been processed by the reviewer agent.
    *   `--evaluate-final`: Run the evaluator on the final set of questions (either from a resumed Markdown file or after the manual review step).
*   **General Options:**
    *   `--log-level`: Set logging verbosity (choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, default: `WARNING`).

*   **R/exams Options:**
    *   `--rexams-title`: Custom title for R/exams PDF output. If not set, uses R script's default.
    *   `--rexams-course`: Custom course name for R/exams PDF output. If not set, uses R script's default.

### `autotestia_split`: Split a question file into multiple smaller files

**Split questions into equal parts with shuffling:**
```bash
autotestia_split generated/all_questions.md \
    --splits 0.5 0.5 \
    --output-dir generated/splits \
    --shuffle-questions 123
```
*   Splits `generated/all_questions.md` into two equal parts (50% each).
*   Output files will be named `all_questions_1.md`, `all_questions_2.md` in `generated/splits/`.
*   Questions are shuffled with seed 123 before splitting.

**Split with mixed proportions:**
```bash
autotestia_split all_questions.md \
    --splits 10 0.25 -1 \
    --output-dir output/custom_splits \
    --shuffle-questions 123
```
*   First file: 10 questions
*   Second file: 25% of remaining questions (shuffled)
*   Third file: all remaining questions

### `autotestia_correct`: Correct R/exams NOPS Scans

The `autotestia_correct` command (wrapping `autotestia/rexams/correct_exams.py`) provides a command-line interface to automate the correction of scanned R/exams NOPS answer sheets. It wraps an R script (`autotestia/rexams/run_autocorrection.R`) that performs the core operations: scanning marks using `nops_scan()`, preparing student registration data, and evaluating exams using `nops_eval()`. 

This Python wrapper can also optionally handle PDF splitting and page rotation using its own image processing capabilities (OpenCV, pdf2image) if you use the `--split-pages` flag and related options, before passing the processed scan data to the R script. This provides more control over the pre-processing steps directly within Python.

By default, for the categorical marks generated by `nops_eval` (which appear in the HTML reports and a "mark" column in the CSV/RDS files), the R script uses a Spanish grading system with descriptive labels (e.g., "Suspenso Muy Deficiente", "Aprobado", "Matrícula de Honor") and percentage thresholds like `0.099, 0.199, ..., 0.949`. You can customize this or omit these marks entirely using specific command-line options.

#### Examples for `autotestia_correct`:

**Correct exams from PDF scans with Python processing:**
```bash
# Ensure R and necessary R packages (exams, qpdf, optparse) are installed.
autotestia_correct \
    --all-scans-pdf generated/splits/exam_scans.pdf \
    --student-info-csv generated/splits/student_register.csv \
    --solutions-rds generated/splits/exam_output/exam.rds \
    --output-path generated/splits/exam_corrected \
    --language es \
    --partial-eval \
    --negative-points -0.333333 \
    --scale-mark-to 10.0 \
    --student-csv-id-col "Número ID" \
    --student-csv-reg-col "DNI" \
    --student-csv-name-col "Nom" \
    --student-csv-surname-col "Cognoms" \
    --student-csv-encoding UTF-8 \
    --registration-format "%08s" \
    --python-rotate \
    --python-split \
    --max-score 30 \
    --log-level INFO \
    --python-bw-threshold 170
```
*   Processes PDF scans with Python-based splitting and rotation.
*   Uses Spanish language for evaluation.
*   Applies partial scoring with -1/3 penalty for wrong answers.
*   Scales final marks to 10.0 scale.
*   Customizes CSV column mappings for student data.

**Correct exams from manually corrected CSV:**
```bash
autotestia_correct \
    --corrected-answers-csv generated/splits/manual_corrections.csv \
    --solutions-rds generated/splits/exam_output/exam.rds \
    --output-path generated/splits/manual_corrected \
    --partial-eval \
    --negative-points -0.333333 \
    --max-score 30 \
    --scale-mark-to 10.0
```
*   Uses pre-corrected answers from CSV file.
*   Applies same scoring rules as above.
*   Useful when manual correction is preferred over automated scanning.

**Basic correction workflow:**
```bash
# Ensure R and necessary R packages (exams, qpdf, optparse) are installed.
autotestia_correct \
    --all-scans-pdf path/to/your/all_scans_concatenated.pdf \
    --split-pages \
    --student-info-csv path/to/your/student_data.csv \
    --solutions-rds path/to/your/generated_rexams_output/exam.rds \
    --output-path ./correction_output \
    --language en \
    --max-score 45 \
    --scale-mark-to 10
```

These commands would:
1.  Split `all_scans_concatenated.pdf` into individual page PDFs (potentially also rotating them) within a subdirectory of `./correction_output/`.
2.  The R script then scans these pages.
3.  Process `student_data.csv` to match the format required by `nops_eval`.
4.  Evaluate the exams using solutions from `exam.rds`.
5.  Save results (e.g., `exam_corrected_results.csv`) in `./correction_output/`.
6.  Scale the marks based on a maximum possible score of 45 to a new scale up to 10.
7.  Generate a histogram of scores and other statistics (if `--max-score` is provided).

#### Command Line Options for `autotestia_correct`:

*   **Input Files/Directories:**
    *   `--all-scans-pdf`: Path to a single PDF containing all scanned exam sheets (required if Python's `--split-pages` is used, or if R is to split pages).
    *   `--student-info-csv`: Path to your CSV file containing student information. (Required)
    *   `--solutions-rds`: Path to the `exam.rds` file generated during R/exams creation. (Required)
    *   `--output-path`: Main directory for all outputs (e.g., `results/my_exam_corrected` will produce `results/my_exam_corrected/exam_corrected_results.csv`, etc.). (Required)
*   **R Environment & Language:**
    *   `--r-executable`: Path to the `Rscript` executable. If omitted, the script attempts to find it automatically.
    *   `--language`: Language for `nops_eval` (e.g., `en`, `es`, `ca`; default: `en`).
*   **Scanning & Evaluation Parameters:**
    *   `--scan-thresholds`: Comma-separated pair for scan thresholds (e.g., `"0.04,0.42"`).
    *   `--partial-eval` / `--no-partial-eval`: Enable/disable partial scoring (default: enabled).
    *   `--negative-points`: Penalty for incorrect answers (default: -1/3).
    *   `--max-score`: Maximum raw score of the exam (e.g., 44). Needed if you want to scale the final mark or run analysis.
    *   `--scale-mark-to`: Target score to scale the final mark to (e.g., 10; default: 10.0).
*   **PDF Processing Controls (Python vs R):**
    *   `--split-pages` / `--no-split-pages` (`dest="split_pages_python_control"` in the script): Enable PDF splitting & rotation by the Python script (default: False). If True, Python converts the `--all-scans-pdf` into individual processed page PDFs (using OpenCV for rotation and `pdf2image`) in `output-path/scanned_pages/` before calling R.
    *   `--force-split` / `--no-force-split` (`dest="force_split_python_control"` in the script): Force overwrite for PDF splitting (applies to Python splitting if `--split-pages` is on, or to R's splitting if `--split-pages` is off but R is expected to split).
    *   `--python-rotate` / `--no-python-rotate` (`dest="python_rotate_control"` in the script): Enable actual image rotation by Python if Python's `--split-pages` is active (default: True). If False, Python splits but does not rotate.
    *   `--rotate-scans` / `--no-rotate-scans` (`dest="rotate_scans_r_control"` in the script): Enable image rotation by R's `nops_scan` (only relevant if Python's `--split-pages` is off). (default: False)
*   **Execution Flow Control:**
    *   `--force-r-eval`: Force R script evaluation even if results CSV exists (default: False).
    *   `--force-nops-scan / --no-force-nops-scan`: Force R's `nops_scan` to re-run (default: `--no-force-nops-scan`).
*   **Consistency Check Control (Python):**
    *   `--run-consistency-check-on-fail` / `--no-run-consistency-check-on-fail`: Run Python-based consistency check if R script fails (default: True).
    *   `--always-run-consistency-check`: Always run Python-based consistency check after R script attempt (default: False).
*   **Analysis Control (Python):**
    *   `--run-analysis` / `--no-run-analysis`: Run Python-based results analysis (histogram, stats) if results CSV exists/is created (default: True).
*   **Question Voiding (for Analysis):**
    *   `--void-questions`: Comma-separated list of question numbers (e.g., "3,4") to remove from score calculation during analysis.
    *   `--void-questions-nicely`: Comma-separated list of question numbers (e.g., "5,6") to void if incorrect/NA, but count if correct, during analysis.
*   **Student CSV Customization (for R script):**
    *   `--student-csv-id-col`: Column name for the unique student ID (e.g., username, default: "ID.Usuario").
    *   `--student-csv-reg-col`: Column name for the registration number (ID written on the exam sheet, default: "Número.de.Identificación").
    *   `--student-csv-name-col`: Column name for student's first name (default: "Nombre").
    *   `--student-csv-surname-col`: Column name for student's surname (default: "Apellidos").
    *   `--student-csv-encoding`: Encoding of your input student CSV file (default: `UTF-8`).
    *   `--registration-format`: `sprintf`-style format string for the registration number (default: `"%08s"`).
*   **PNG Generation Control:**
    *   `--force-png-generation`: Force regeneration of PNGs from student HTML reports (if available) even if they already exist (default: False).
*   **Logging Control:**
    *   `--log-level`: Set the log level (choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, default: `INFO`).

## Next Steps / TODO

*   Test all the output formats (only Wooclap and R/Exams have been tested so far)
*   Test robust parsing for PDF, DOCX in `input_parser/parser.py` (only PPTX and text formats have been tested so far)
*   Test image extraction from documents
*   Test passing custom images for questions
*   Add structured output support (JSON). Right now I'm using JSON, but sometimes the parsing fails.
*   Develop evaluation metrics and agent (OE6).
*   Explore dynamic questions (OE7) and humorous distractors (OE8).
*   Consider adding support for self-hosted models.
*   Refactor, e.g. shared LLM logic (client init, retry, parsing) into a utility module.
