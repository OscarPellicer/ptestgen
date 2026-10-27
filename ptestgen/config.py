# Configuration settings for PTestGen

import os

from pexams.env import load_project_dotenv

# Load environment variables from project .env files (current folder, ptestgen and their parents).
load_project_dotenv(__file__)

# --- LLM Configuration ---
# Calls go through pexams.llm.LLMClient (shared with pexams and pevaluate). The model id decides
# the route: a bare Anthropic id ("claude-sonnet-5-5") calls the Anthropic API, any other id
# ("google/gemini-3.1-pro-preview", "anthropic/claude-sonnet-5-5") goes to OpenRouter.
# --provider (or LLM_PROVIDER) picks the default models below: "openrouter", "anthropic" or "stub"
# (placeholder questions, no API calls; for tests).
SUPPORTED_PROVIDERS = ("openrouter", "anthropic", "stub")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
if LLM_PROVIDER not in SUPPORTED_PROVIDERS:
    import logging as _logging

    _logging.warning(f"LLM_PROVIDER={LLM_PROVIDER!r} is no longer supported (use openrouter, anthropic or stub); using openrouter.")
    LLM_PROVIDER = "openrouter"

# Environment variable holding each route's API key. Override the name to reuse another variable,
# e.g. PTESTGEN_ANTHROPIC_API_KEY_ENV=CLAUDE_KEY.
PROVIDER_API_KEY_MAP = {
    "anthropic": os.getenv("PTESTGEN_ANTHROPIC_API_KEY_ENV", "ANTHROPIC_API_KEY"),
    "openrouter": os.getenv("PTESTGEN_OPENROUTER_API_KEY_ENV", "OPENROUTER_API_KEY"),
}

# --- Model Selection ---
GENERATOR_MODEL_MAP = {
    "openrouter": os.getenv("OPENROUTER_GENERATOR_MODEL", "google/gemini-3.1-pro-preview"),
    "anthropic": os.getenv("ANTHROPIC_GENERATOR_MODEL", "claude-sonnet-5-5"),
    "stub": "stub-generator-model",
}
REVIEWER_MODEL_MAP = {
    "openrouter": os.getenv("OPENROUTER_REVIEWER_MODEL", "google/gemini-3.8-flash"),
    "anthropic": os.getenv("ANTHROPIC_REVIEWER_MODEL", "claude-haiku-5-5"),
    "stub": "stub-reviewer-model",
}
EVALUATOR_MODEL_MAP = {
    "openrouter": os.getenv("OPENROUTER_EVALUATOR_MODEL", "google/gemini-3.8-flash"),
    "anthropic": os.getenv("ANTHROPIC_EVALUATOR_MODEL", "claude-haiku-5-5"),
    "stub": "stub-evaluator-model",
}

# Models for the selected provider.
GENERATOR_MODEL = GENERATOR_MODEL_MAP[LLM_PROVIDER]
REVIEWER_MODEL = REVIEWER_MODEL_MAP[LLM_PROVIDER]
EVALUATOR_MODEL = EVALUATOR_MODEL_MAP[LLM_PROVIDER]

# Optional effort per agent (low, medium, high, xhigh, max); empty = the model's default
# (Gemini Flash on OpenRouter then gets "minimal"). PTESTGEN_EFFORT sets all three.
_EFFORT = os.getenv("PTESTGEN_EFFORT") or None
GENERATOR_EFFORT = os.getenv("PTESTGEN_GENERATOR_EFFORT") or _EFFORT
REVIEWER_EFFORT = os.getenv("PTESTGEN_REVIEWER_EFFORT") or _EFFORT
EVALUATOR_EFFORT = os.getenv("PTESTGEN_EVALUATOR_EFFORT") or _EFFORT


# --- Agent Settings ---
DEFAULT_NUM_QUESTIONS = 5
DEFAULT_NUM_OPTIONS = 4 # Including the correct answer
# Flag to enable LLM-based review (can be overridden by CLI arg)
DEFAULT_LLM_REVIEW_ENABLED = True

# --- Reviewer Criteria (Example) ---
# These would be used by the reviewer agent (OE2)
REVIEWER_CRITERIA = {
    "min_option_length": 3,
    "max_option_length": 150,
    "check_grammar": True, # Rule-based check placeholder
    "avoid_absolute_statements": ["always", "never"],
    "ensure_plausible_distractors": True, # This would primarily be handled by LLM review if enabled
}

# --- File Paths ---
DEFAULT_OUTPUT_MD_FILE = "output/questions.md"
DEFAULT_OUTPUT_MOODLE_XML_FILE = "output/moodle_questions.xml"
DEFAULT_OUTPUT_GIFT_FILE = "output/gift_questions.gift"
DEFAULT_OUTPUT_WOOCLAP_FILE = "output/wooclap_questions.csv" # Changed extension to csv
DEFAULT_OUTPUT_REXAMS_DIR = "output/rexams/" # Directory for R/exams output files
DEFAULT_LANGUAGE = "Spanish"

_LANGUAGE_CODES = {"spanish": "es", "español": "es", "castellano": "es", "english": "en", "inglés": "en",
                   "catalan": "ca", "català": "ca", "valencian": "ca", "valencià": "ca"}


def language_code(language: str) -> str:
    """'Spanish' -> 'es': pexams labels the answer sheets by language code."""
    return _LANGUAGE_CODES.get(str(language).strip().lower(), str(language))

# --- Prompting ---
GENERATION_SYSTEM_PROMPT = """
You are an AI assistant specialized in creating high-quality test questions for university students, given the provided context or instructions. Base the questions strictly on the provided context if available. Try to generate at least one question for each topic that is covered in the context. You can use a variety of markdown formatting options (don't use any formatting option that is not listed here): *italic text*, **bold text**, `code`, $LaTeX_expression$ (such as $\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$; don't use $$). DO NOT use newlines in the question text, answers, distractors, expected answer, or rubric.

For multiple-choice questions, set "question_type" to "multiple_choice" and provide:
- The question text.
- The correct answer.
- A list of distractors.

For open-answer questions, set "question_type" to "open_answer" and provide:
- The question text.
- "expected_answer": a concise model answer.
- "rubric": a concise scoring rubric with point allocation.
- "answer_lines": the number of answer lines to reserve, usually 6-12.

{custom_generator_instructions}

Output the questions as a JSON object with key "questions" (list of objects). OUTPUT ONLY THE JSON OBJECT, NOTHING ELSE.
"""

IMAGE_GENERATION_SYSTEM_PROMPT = """
You are an AI assistant specialized in creating educational test questions based on images.
Given the provided image and optional context text, generate test questions that require understanding the image content. You can use a variety of markdown formatting options (don't use any formatting option that is not listed here): *italic text*, **bold text**, `code`, $LaTeX_expression$ (such as $\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$; don't use $$).
DO NOT use newlines in the question text, answers, distractors, expected answer, or rubric.
For multiple-choice questions, set "question_type" to "multiple_choice" and provide the question text, correct answer, and distractors.
For open-answer questions, set "question_type" to "open_answer" and provide the question text, expected_answer, rubric, and answer_lines.

{custom_generator_instructions}

Output the questions as a JSON object with key "questions" (list of objects). Focus the questions on interpreting the visual information in the image, potentially using the context text for background. OUTPUT ONLY THE JSON OBJECT, NOTHING ELSE.
"""

REVIEW_SYSTEM_PROMPT = """
You are an AI assistant expert in evaluating the quality of multiple-choice questions and improving them if needed. You must also check that the correct answer cannot be easily differentiated from the distractors.
Review the following question based on clarity, correctness, plausibility of distractors, grammatical correctness, and adherence to good question design principles.
Take special care to ensure that all options are of similar length, and that the level of complexity of the wrong answers is similar to that of the correct answer.
Make sure that neither the correct answer nor the distractors end with a period.
If possible, avoid absolutes in the confounders, such as: never, always, exclusively, etc.

{custom_reviewer_instructions}

If changes are needed, provide the corrected question (including the question text, the correct answer and the confounders) in the same JSON format as the input question, under the key "reviewed_question". If no changes are needed, return the original question under the "reviewed_question" key.

Input Question (JSON format):

{question_json}

Output your review as a JSON object with a single key: "reviewed_question", which contains a JSON object with keys: "text", "correct_answer", "distractors". OUTPUT ONLY THE JSON OBJECT, NOTHING ELSE.
"""

EVALUATION_SYSTEM_PROMPT = """
You are an AI assistant expert in evaluating the quality of multiple-choice questions based on multiple pedagogical criteria.
From the provided list of `options`, first identify and select the 1-based index of the answer you believe is correct.
Then, for the question as a whole, provide a score from 0.0 to 1.0 for each of the following criteria:
- difficulty_score: How difficult is the question for a university student? (0.0 = very easy, 1.0 = very difficult)
- pedagogical_value: How well does the question assess understanding of a key concept? (0.0 = very low value, 1.0 = very high value)
- clarity: How clear and unambiguous is the question and its options? (0.0 = very unclear, 1.0 = very clear)
- distractor_plausibility: How plausible are the incorrect options (distractors)? (0.0 = not plausible at all, 1.0 = very plausible)

Finally, provide a brief, one-sentence constructive comment explaining your scores.

{custom_evaluator_instructions}

Input Question (JSON format):

{question_json}

Output your evaluation as a JSON object with keys: "guessed_correct_answer" (int), "difficulty_score" (float), "pedagogical_value" (float), "clarity" (float), "distractor_plausibility" (float), and "evaluation_comment" (string). OUTPUT ONLY THE JSON OBJECT, NOTHING ELSE.
"""


# --- Other ---
# Timeout for LLM API calls (in seconds, per read; Anthropic calls stream)
LLM_TIMEOUT = 180
# Hard wall-clock limit per attempt. The client timeout is a per-read timeout, so a
# server that keeps the connection alive (e.g. OpenRouter keep-alive padding) can hang forever.
LLM_HARD_TIMEOUT = int(os.getenv("PTESTGEN_LLM_HARD_TIMEOUT", "300"))
# Max retries for LLM API calls (by the SDK for HTTP errors, then by ptestgen for any failure)
LLM_MAX_RETRIES = 2
# Base delay for retries (in seconds), will be subject to exponential backoff
RETRY_DELAY_BASE = 2 # Added for retry logic
