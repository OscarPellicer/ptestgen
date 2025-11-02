# AutoTestIA

AutoTestIA is a Python-based tool designed to assist educators in generating multiple-choice quizzes (tests) from educational materials or specific instructions using Large Language Models (LLMs). It aims to streamline the quiz creation process, saving time and potentially improving question quality.

## Project Goal

To develop and evaluate an AI-powered tool (AutoTestIA) for semi-automatic generation of multiple-choice questions via intelligent agents, integrated into an efficient, user-friendly Python pipeline adaptable to various educational platforms (Moodle, Wooclap, [pexams](https://github.com/OscarPellicer/pexams), R/exams).

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
*   **Format Conversion (OE4):** Converts the finalized questions into formats compatible with Moodle (XML/GIFT), Wooclap, pexams (PDF), and R/exams (.Rmd structure).
*   **Question Shuffling & Selection:**
    *   Shuffle the order of generated questions (`--shuffle-questions`).
    *   Shuffle the order of answers within each question (`--shuffle-answers`).
    *   Select a random subset of the final questions (`--num-final-questions`).
*   **Integrated Pipeline (OE5):** A cohesive Python script orchestrates the entire process.
*  **Evaluation Agent (OE6)**
*   *(Future)* Dynamic Question Support (OE7)
*   *(Future)* Humorous Distractor Option (OE8)

## Setup

The library has been tested on Python 3.11.

1.  Clone the repository:
    ```bash
    git clone https://github.com/OscarPellicer/AutoTestIA.git
    cd AutoTestIA
    ```
2.  (Recommended) Create and activate a virtual environment:
    
    **Option A: Using `conda` (recommended):**
    ```bash
    conda create -n autotestia python=3.11
    conda activate autotestia
    ```
    
    **Option B: Using `venv`:**
    ```bash
    python -m venv autotestia
    # On Windows: autotestia\Scripts\activate
    # On macOS/Linux: source autotestia/bin/activate
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
6.  **(Recommended) Setup for `pexams` (Python-based PDF exams)**

    `pexams` is a pure Python library for generating and correcting scannable multiple-choice exams, similar to R/exams. It is the recommended engine for PDF exam generation within AutoTestIA as it does not require installing R or LaTeX.

    For more details, please visit the official repository: [https://github.com/OscarPellicer/pexams](https://github.com/OscarPellicer/pexams)

    1.  **Install the `pexams` library:**

        `pexams` is already installed as a dependency of AutoTestIA, but you can install it manually too:

        ```bash
        pip install pexams
        ```

    2.  **Install Playwright Browsers:**

        `pexams` uses Playwright to render HTML to PDF. You must install the required browser binaries:
        ```bash
        playwright install chromium
        ```

7.  **(DEPRECATED) Setup for R/exams**
    > **Warning**
    > The `rexams` export format and correction command are deprecated in favor of the pure Python `pexams` engine. Support for `rexams` will be removed in a future version. It is recommended to use `pexams` for generating PDF exams as it does not require installing R or LaTeX, and is much less prone to frustrating errors.

    To utilize the R/exams output format, you must have R and a LaTeX distribution installed.
    *   **Install R:** [The Comprehensive R Archive Network (CRAN)](https://cran.r-project.org/).
    *   **Install LaTeX:** We recommend [TinyTeX](https://yihui.org/tinytex/).
    *   **Install Required R Packages:**
        ```R
        install.packages(c("exams", "optparse", "knitr", "qpdf"))
        ```

**Note on parsing `.pptx` files (WIP)**

Unfortunately, the `python-pptx` library in charge of parsing `.pptx` files does not correctly parse MathML equations. This has been solved in my fork of the library: https://github.com/OscarPellicer/python-pptx.

To use it, you need to install this version of `python-pptx` manually AFTER installing everything else:

```bash
pip install git+https://github.com/OscarPellicer/python-pptx.git
```

## Usage

The `autotestia` command-line tool is organized into several sub-commands to manage the lifecycle of test creation.

**Core Workflow:**

1.  **`generate`**: Create a new set of questions from a document or instructions. This produces a human-readable `questions.md` file for manual review and a `metadata.tsv` file that tracks all question data.
2.  **(Manual Step)**: Edit the `questions.md` file to correct, improve, add, or delete questions.
3.  **`export <format>`**: Read the (potentially edited) `questions.md` and its corresponding `metadata.tsv` to export the final questions into a specific format like Moodle XML, pexams, Wooclap, etc.

**Other Commands:**

*   `autotestia split`: Split a test into multiple smaller tests. This is useful for creating two exams (e.g. final and make-up) from the same set of questions. While this could also be done manually, using the command ensures that the final `.tsv` file is updated to contain the metainformation from the complete lifecycle of the questions.
*   `autotestia merge`: Combine multiple tests into a single one. This is useful for merging questions from different topics into a single exam. Similar to `split`, using the command ensures that the final `.tsv` is updated to contain the metainformation from the complete lifecycle of the questions.
*   `autotestia shuffle`: Shuffle questions in a markdown file.
*   `autotestia correct`: Correct scanned exam sheets, with sub-commands for `pexams` and `rexams`.
*   `autotestia test`: Run a full pipeline test to check for runtime errors.

---

### `autotestia generate`: Create questions

Use this command to start the process. It generates the initial set of questions from a source document or from instructions you provide.

**1. Generate from Document:**
```bash
autotestia generate path/to/presentation.pptx -o generated/my-exam.md --num-questions 10
```
*   This reads `presentation.pptx` and creates two files: `generated/my-exam.md` and `generated/my-exam.tsv`.

**2. Generate from Instructions:**
```bash
autotestia generate --generator-instructions "Create questions about Python regular expressions..." -o generated/regex-exam
```
*   This generates questions based on the provided instructions without needing a source file.

#### Examples for `autotestia generate`

**Generate questions from a PowerPoint with LLM review and evaluation:**
```bash
# Make sure OPENROUTER_API_KEY is in .env
autotestia generate path/to/presentation.pptx \
    -o generated/topic_questions.md \
    -n 10 \
    --provider openrouter \
    --generator-model google/gemini-2.5-pro \
    --reviewer-model google/gemini-2.5-flash \
    --evaluator-model google/gemini-2.5-flash \
    --use-llm-review \
    --evaluate-initial \
    --evaluate-reviewed \
    --language Spanish \
    --generator-instructions "Focus on topics related to LDA, LSA / LSI"
```
*   Creates `generated/topic_questions.md` and `generated/topic_questions.tsv`.
*   It specifies the LLM provider as well as the specific models to use for each agent.
*   It uses the `--use-llm-review` flag to enable the LLM-based review of the questions after generation.
*   It uses the `--evaluate-initial` and `--evaluate-reviewed` flags to run the evaluator on the questions after generation and review.
*   It uses the `--language` flag to set the language for the questions to Spanish.
*   The process stops here, awaiting manual review of the `questions.md` file and a subsequent `export` command.
*   In this example, specific generator instructions are provided to focus on topics related to LDA, LSA / LSI, but instructions can be omitted.

---

### `autotestia export <format>`: Convert questions to final formats

After you have manually reviewed and saved the `questions.md` file, use this command to generate the final exam files. The export command is structured with subparsers for each format.

**1. Export to Wooclap with shuffling:**
```bash
autotestia export wooclap generated/topic_questions.md \
    --shuffle-questions 123 \
    --shuffle-answers 123 \
    --evaluate-final
```
*   Reads `generated/topic_questions.md` and `generated/topic_questions.tsv`.
*   (automatically processeses your manual edits to update the `.tsv` file).
*   Creates a `generated/topic_questions_wooclap.csv` file that is ready to be imported into Wooclap.
*   It uses the `--shuffle-questions` flag to shuffle the order of the questions.
*   It uses the `--shuffle-answers` flag to shuffle the order of the answers within each question. **This is very important for Wooclap in particular, as it does not automatically shuffle the answers for you!**
*   It uses the `--evaluate-final` flag to run the evaluator on the final set of questions.

**2. Export to `pexams` PDF format:**
```bash
autotestia export pexams generated/exam_questions.md \
    --exam-title "Sistemas Informáticos - Examen Parcial" \
    --exam-course "Máster de ejemplo" \
    --exam-date "2025-10-22" \
    --exam-models 4 \
    --shuffle-answers 123
```
*   Creates 4 PDF exam models of the questions in `generated/exam_questions.md` using the `pexams` engine.
*   For more information on the available arguments, please visit the `pexams` repository: [https://github.com/OscarPellicer/pexams](https://github.com/OscarPellicer/pexams)

---

### Command Line Options

#### `autotestia generate`
*   `input_material`: (Optional) Path to the input file (e.g., `.txt`, `.pdf`).
*   `-o, --output-dir`: Directory to save the generated `questions.md` and `metadata.tsv` files.
*   `--generator-instructions`: Custom instructions for the generator prompt.
*   `--reviewer-instructions`: Custom instructions for the reviewer prompt.
*   `-i, --images`: Optional path(s) to image file(s) to generate questions from.
*   `-n, --num-questions`: Number of questions to generate (default: 5).
*   `--provider`: LLM provider (`openai`, `google`, `openrouter`, etc.).
*   `--generator-model`, `--reviewer-model`, `--evaluator-model`: Specify models for each agent.
*   `--use-llm-review` / `--no-use-llm-review`: Enable/disable LLM-based review.
*   `--evaluate-initial`, `--evaluate-reviewed`: Run evaluator on questions after generation/review.
*   `--language`: Language for questions (default: `en`).

#### `autotestia export <format>`
This command uses subparsers for each format (`pexams`, `wooclap`, `moodle_xml`, `gift`, `none`).

*   `input_md_path`: (Positional) Path to the `questions.md` file.
*   `--shuffle-questions [SEED]`: Shuffle the order of questions.
*   `--shuffle-answers [SEED]`: Shuffle the order of answers within each question.
*   `--num-final-questions N`: Randomly select `N` questions.
*   `--evaluate-final`: Run the evaluator on the final set of questions (after manual review).

**`pexams` and `rexams` specific options:**
*   `--exam-title`: Title for the exam.
*   `--exam-course`: Course name for the exam.
*   `--exam-date`: Date for the exam.
*   `--exam-models`: Number of different exam versions to generate.
*   `--exam-language`: Language for the exam: `es`, `en`, `ca`, `de`, `fr`, `it`, `pt`, `ru`, `zh`, etc.

**`pexams` only options:**
*   `--exam-font-size`: Font size for the exam.
*   `--exam-columns`: Number of columns for the exam.
*   `--exam-id-length`: Length of the student ID (e.g. 9 digits for DNI).
*   `--exam-generate-fakes`: Generate fake answer sheets for the exam (used for testing the correction process).
*   `--exam-generate-references`: Generate references for the exam (used for teachers' reference).

For more information on the available arguments for `pexams`, please visit the `pexams` repository: [https://github.com/OscarPellicer/pexams](https://github.com/OscarPellicer/pexams)

---

### `autotestia split`: Split a test into multiple smaller tests
```bash
autotestia split generated/all_questions.md \
    --splits 0.5 3 -1 \
    --output-dir generated/splits \
    --shuffle-questions 123
```
*   Splits `generated/all_questions.md` into three parts:
    - `0.5`: 50% of the questions
    - `3`: the following 3 questions
    - `-1`: the remaining questions
*   Creates:
    - `generated/splits/all_questions_1.md` (and `all_questions_1.tsv`)
    - `generated/splits/all_questions_2.md` (and `all_questions_2.tsv`)
    - `generated/splits/all_questions_3.md` (and `all_questions_3.tsv`)

---

### `autotestia merge`: Combine multiple tests
```bash
autotestia merge generated/splits/part_1.md generated/splits/part_2.md -o generated/part_1_all.md
```
*   Combines the questions from `part_1.md` and `part_2.md`.
*   Creates a new questions file `generated/part_1_all.md` (and accompanying `.tsv`).

---

### `autotestia shuffle`: Shuffle a standalone markdown file

This command is a simple utility to shuffle the questions within a single `questions.md` file. It does not read or modify the `questions.tsv`, since it is not needed for this operation (the IDs do not change)

```bash
autotestia shuffle generated/my_test/questions.md --seed 42 --yes
```
*   Shuffles the questions in `questions.md` and saves the result to a new file.
*   Uses a seed for reproducible shuffling.
*   Uses the `--yes` flag to bypass the confirmation prompt and overwrite the file directly.
---

### `autotestia test`: Run a pipeline test

Use this command to run a full, unattended test of the core library features to ensure everything is working correctly. It does not verify the correctness of the LLM outputs, but it checks that all commands run without crashing.

The test workflow is as follows:
1.  **Generate** 3 questions using the `openrouter` provider with default models (as defined in `setup.py`).
2.  **Generate** another 3 questions using the `openai` provider with default models (as defined in `setup.py`).
3.  **Split** the first test into three parts.
4.  **Merge** the split parts and the second test back into a single file.
5.  **Shuffle** the merged file.
6.  **Simulate manual edits** on the markdown file (changing a question ID and content).
7.  **Export** the final questions to Wooclap, Moodle XML, and `pexams` formats.
8.  For `pexams`, it generates simulated scan sheets.
9.  **Correct** the simulated `pexams` scans.

All artifacts from this command are saved in the `generated_test/` directory, which is ignored by git.

**Example:**
```bash
# Ensure your API keys are set in the .env file
autotestia test --log-level INFO
```

---

### `autotestia correct`: Correct exam scans

This command consolidates the correction workflows for both `pexams` and `rexams`.

#### `autotestia correct pexams`

Corrects exams generated by the `pexams` engine.

**Example:**
```bash
autotestia correct pexams \
    --input-path generated/my_exam_pexams_output/simulated_scans \
    --exam-dir generated/my_exam_pexams_output \
    --output-dir generated/my_exam_pexams_output/correction_results
```

**Options:**
*   `--input-path`: Path to the scanned PDF or a folder of scanned images.
*   `--exam-dir`: Path to the directory containing the generated `pexams` files (e.g., `exam_model_..._questions.json`).
*   `--output-dir`: Directory where the correction results will be saved.
*   `--void-questions`: Comma-separated list of question numbers to exclude from scoring.

#### `autotestia correct rexams`
> **Warning**
> The `rexams` correction command is deprecated, and may be removed in a future version. Please use `pexams` instead.

Corrects exams generated by the R/exams framework. This command is a wrapper around the original R scripts and provides extensive options for PDF processing and scoring.