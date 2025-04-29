# AutoTestIA

AutoTestIA is a Python-based tool designed to assist educators in generating multiple-choice quizzes (tests) from educational materials using Large Language Models (LLMs). It aims to streamline the quiz creation process, saving time and potentially improving question quality.

## Project Goal

To develop and evaluate an AI-powered tool (AutoTestIA) for semi-automatic generation of multiple-choice questions via intelligent agents, integrated into an efficient, user-friendly Python pipeline adaptable to various educational platforms (Moodle, Wooclap, R/exams).

## Core Features

*   **LLM Integration:** Supports multiple providers:
    *   OpenAI (e.g., GPT-4o)
    *   Google (e.g., Gemini 1.5 Pro)
    *   Anthropic (e.g., Claude 3.5 Sonnet, Claude 3 Haiku)
    *   Replicate (e.g., Llama 3.1 - *proxy for 3.2*)
*   **Question Generation (OE1):** Generate questions from text documents (**TXT, MD, PDF, DOCX, PPTX, RTF supported for text extraction**) and images (PNG, JPG, GIF, BMP) using selected LLM. PDF/DOCX/PPTX parsing requires installing optional dependencies (see Setup). Image extraction *from within documents* is planned but not yet implemented.
*   **Automated Review (OE2):** Rule-based checks and optional LLM-based review for quality criteria (clarity, distractor plausibility, etc.).
*   **Manual Review Workflow (OE3):** Outputs questions in a clean Markdown format for easy verification and editing by the educator. Can be skipped via CLI flag.
*   **Format Conversion (OE4):** Converts the finalized questions into formats compatible with Moodle (XML/GIFT), Wooclap (Placeholder), and R/exams (.Rmd structure).
*   **Integrated Pipeline (OE5):** A cohesive Python script orchestrates the entire process.
*   *(Future)* Evaluation Agent (OE6)
*   *(Future)* Dynamic Question Support (OE7)
*   *(Future)* Humorous Distractor Option (OE8)

## Current Status

Core pipeline implemented with support for major LLM providers. Text parsing is basic (.txt only). Image generation and LLM review are functional. Output converters for Moodle XML, GIFT, and R/exams structure are implemented. Wooclap is a placeholder. Error handling is basic.

## Setup

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd AutoTestIA
    ```
2.  (Recommended) Create and activate a virtual environment:
    ```bash
    python -m venv venv
    # On Windows: venv\Scripts\activate
    # On macOS/Linux: source venv/bin/activate
    ```
3.  Install required dependencies:
    ```bash
    # Core dependencies
    pip install -r requirements.txt

    # Optional: For parsing PDF, DOCX, PPTX, RTF files, Pillow is also needed
    # These are included in requirements.txt but you can install separately:
    # pip install pypdf python-docx python-pptx striprtf Pillow
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
5.  (Optional) You can set the default provider and models directly in the `.env` file as well:
    ```dotenv
    # Optional defaults in .env
    LLM_PROVIDER="openai"
    OPENAI_GENERATOR_MODEL="gpt-4o"
    # etc.
    ```

## Usage

```bash
python main.py <input_material_path> [options]
```

**Examples:**

1.  **Generate 5 questions using OpenAI (default provider if not set in `.env`) from a text file, output to default paths, request Moodle XML and GIFT:**
    ```bash
    # Make sure OPENAI_API_KEY is in .env
    python main.py path/to/your/notes.txt -n 5
    ```
    *   This will create `output/questions.md`. Press Enter after reviewing.
    *   Then creates `output/moodle_questions.xml` and `output/gift_questions.gift`.

2.  **Generate 3 questions using Google Gemini, include an image, enable LLM review, skip manual review, output R/exams format:**
    ```bash
    # Make sure GOOGLE_API_KEY is in .env
    python main.py course_material.txt -n 3 -i diagram.png --provider google --use-llm-review --skip-manual-review -f rexams -o generated/google_review.md
    ```
    *   Creates `generated/google_review.md`.
    *   Immediately creates R/exams files in `generated/rexams/`.

3.  **Generate 10 questions using Anthropic Claude 3.5 Sonnet (specify model) from text:**
    ```bash
    # Make sure ANTHROPIC_API_KEY is in .env
    python main.py lecture_notes.txt -n 10 --provider anthropic --generator-model claude-3-5-sonnet-20240620
    ```

**Command Line Options:**

*   `input_material`: Path to the input text file (supports `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`, `.rtf`).
*   `-i`, `--images`: (Optional) Path(s) to image file(s).
*   `-n`, `--num-questions`: Number of text-based questions (default: 5).
*   `-o`, `--output-md`: Path for the intermediate Markdown file (default: `output/questions.md`).
*   `-f`, `--formats`: Output format(s) (choices: `moodle_xml`, `gift`, `wooclap`, `rexams`, default: `moodle_xml gift`).
*   `--provider`: LLM provider (choices: `openai`, `google`, `anthropic`, `replicate`, `stub`, default: from `.env` or `stub`).
*   `--generator-model`: Override default generator model for the provider.
*   `--reviewer-model`: Override default reviewer model for the provider.
*   `--use-llm-review` / `--no-use-llm-review`: Enable/disable LLM-based review agent.
*   `--skip-manual-review`: Skip the pause for manual Markdown editing.
*   `--extract-doc-images`: [Experimental] Attempt to extract images from documents (feature incomplete).

## Next Steps

*   Implement robust parsing for PDF, DOCX, PPTX in `input_parser/parser.py`.
*   Implement actual Wooclap export in `output_formatter/converters.py`.
*   Refine prompt engineering in `config.py` for better quality and consistency.
*   Improve error handling and add logging.
*   Develop evaluation metrics and agent (OE6).
*   Explore dynamic questions (OE7) and humorous distractors (OE8).
*   Consider adding support for more LLM providers or self-hosted models.
*   Refactor shared LLM logic (client init, retry, parsing) into a utility module.
