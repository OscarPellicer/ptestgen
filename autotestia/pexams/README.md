# Pexams: Python Exam Generation and Correction

Pexams is a library for generating beautiful exam sheets from simple data structures and automatically correcting them from scans using computer vision. It is similar to R/exams, but written in Python and using [Playwright](https://playwright.dev/python/) for high-fidelity PDF generation instead of LaTeX. It has the following advantages:
- It uses Python and Playwright, which is fast and reliable.
- It is much easier to install, as it requires only Python and a single command to download browser binaries, which is much easier to manage than R + LaTeX.
- It is easier to customize (it's Python + HTML/CSS!).
- It is less prone to compilation errors (again, no LaTeX!).

## Installation

The library has been tested on Python 3.11

1.  **Install the library**

    For development, you can install it in editable mode:
    ```bash
    pip install -e .
    ```
    This will also install the necessary Python dependencies from `setup.py` and make the `pexams` command-line tool available.

2.  **Install Playwright Browsers**

    `pexams` uses Playwright to convert HTML to PDF. You need to download the necessary browser binaries by running:
    ```bash
    playwright install
    ```
    This command only needs to be run once.

## Usage

### Input Format (JSON)

The `generate` command expects a JSON file containing the exam questions. The JSON file must conform to the following schema:

- The root object should have a single key, `questions`, which is an array of question objects.
- Each question object has the following keys:
  - `id` (integer, required): A unique identifier for the question.
  - `text` (string, required): The question text, which can include Markdown.
  - `options` (array, required): A list of option objects.
    - Each option object has:
      - `text` (string, required): The option text.
      - `is_correct` (boolean, required): Must be `true` for exactly one option per question.
  - `image_source` (string, optional): A path to a local image, a URL, or a base64-encoded data URI.

**Example `questions.json`:**
```json
{
  "questions": [
    {
      "id": 1,
      "text": "What is the capital of France?\\n\\nSelect the correct option below.",
      "options": [
        { "text": "Berlin", "is_correct": false },
        { "text": "Madrid", "is_correct": false },
        { "text": "Paris", "is_correct": true },
        { "text": "Rome", "is_correct": false }
      ]
    },
    {
      "id": 2,
      "text": "Which of the following is a primary color?",
      "image_source": "path/to/your/image.png",
      "options": [
        { "text": "Green", "is_correct": false },
        { "text": "Blue", "is_correct": true },
        { "text": "Orange", "is_correct": false },
        { "text": "Purple", "is_correct": false }
      ]
    }
  ]
}
```

### Command Line

#### Generating Exams

To generate exam PDFs from a JSON file:

```bash
pexams generate --questions-json <path_to_questions.json> --output-dir <results_directory> [OPTIONS]
```

**Common Options:**
- `--num-models <int>`: Number of exam variations to generate (default: 4).
- `--exam-title <str>`: Title for the exam (default: "Final Exam").
- `--font-size <str>`: Base font size, e.g., '10pt' (default: '11pt').
- `--columns <int>`: Number of question columns (1, 2, or 3; default: 1).

#### Correcting Exams

To correct a set of scans of an exam:

```bash
pexams correct --scans-pdf <path_to_scans.pdf> --solutions-json <path_to_solutions.json> --output-dir <results_directory>
```

### API

You can also use the Python API to generate and correct exams.

#### Generating Exams

```python
from autotestia.pexams import generate_exams
from autotestia.pexams.schemas import PexamQuestion, PexamOption

# 1. Create your list of questions
questions = [
    PexamQuestion(
        id=1,
        text="What is the capital of France?",
        options=[
            PexamOption(text="Berlin", is_correct=False),
            PexamOption(text="Madrid", is_correct=False),
            PexamOption(text="Paris", is_correct=True),
            PexamOption(text="Rome", is_correct=False),
        ]
    ),
    # ... more questions
]

# 2. Generate the exam PDFs
generate_exams(
    questions=questions,
    output_dir="my_exams",
    num_models=4,
    exam_title="Geography Quiz",
    exam_course="GEO101",
    lang="en"
)
```

#### Correcting Exams
```python
from autotestia.pexams import correct_exams

# Define the solutions
solutions = {
    1: 2,  # Question 1, correct option is index 2 ('C')
    # ... more solutions
}

# Correct the scanned PDF
correct_exams(
    scanned_pdf_path="scans/all_scans.pdf",
    solutions=solutions,
    output_dir="results"
)

```
