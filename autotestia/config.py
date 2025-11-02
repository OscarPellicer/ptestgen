# Configuration settings for AutoTestIA

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- LLM Configuration ---
# Select the provider: "openai", "google", "anthropic", "replicate", "stub"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")

# API Keys from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

PROVIDER_API_KEY_MAP = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "replicate": "REPLICATE_API_TOKEN",
    "openrouter": "OPENROUTER_API_KEY",
    # ollama is local, no key needed
}

# Ollama Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")


# --- Model Selection ---
# Define models for each provider (using requested models or sensible defaults)
# Check provider documentation for the latest/most appropriate model names.
GENERATOR_MODEL_MAP = {
    "openai": os.getenv("OPENAI_GENERATOR_MODEL", "gpt-4o"),
    "google": os.getenv("GOOGLE_GENERATOR_MODEL", "gemini-2.5-pro"),
    "anthropic": os.getenv("ANTHROPIC_GENERATOR_MODEL", "claude-sonnet-4-5"),
    "replicate": os.getenv("REPLICATE_GENERATOR_MODEL", "unsloth/meta-llama-3.3-70b-instruct"),
    "openrouter": os.getenv("OPENROUTER_GENERATOR_MODEL", "google/gemini-2.5-pro"),
    "ollama": os.getenv("OLLAMA_GENERATOR_MODEL", "gemma3:4b"),
    "stub": "stub-generator-model"
}

REVIEWER_MODEL_MAP = { # Potentially use a cheaper model for review
    "openai": os.getenv("OPENAI_REVIEWER_MODEL", "gpt-4o"),
    "google": os.getenv("GOOGLE_REVIEWER_MODEL", "gemini-2.5-flash"),
    "anthropic": os.getenv("ANTHROPIC_REVIEWER_MODEL", "claude-haiku-4-5"), 
    "replicate": os.getenv("REPLICATE_REVIEWER_MODEL", "unsloth/meta-llama-3.3-70b-instruct"),
    "openrouter": os.getenv("OPENROUTER_REVIEWER_MODEL", "google/gemini-2.5-flash"),
    "ollama": os.getenv("OLLAMA_REVIEWER_MODEL", "gemma3:4b"),
    "stub": "stub-reviewer-model"
}

# TODO: Add Evaluator Model Map (OE6)
EVALUATOR_MODEL_MAP = { # Potentially use a cheaper model for review
    "openai": os.getenv("OPENAI_EVALUATOR_MODEL", "gpt-4o"),
    "google": os.getenv("GOOGLE_EVALUATOR_MODEL", "gemini-2.5-flash"),
    "anthropic": os.getenv("ANTHROPIC_EVALUATOR_MODEL", "claude-haiku-4-5"), 
    "replicate": os.getenv("REPLICATE_EVALUATOR_MODEL", "unsloth/meta-llama-3.3-70b-instruct"),
    "openrouter": os.getenv("OPENROUTER_EVALUATOR_MODEL", "google/gemini-2.5-flash"),
    "ollama": os.getenv("OLLAMA_EVALUATOR_MODEL", "gemma3:4b"),
    "stub": "stub-evaluator-model"
}


# Get the actual model names based on the selected provider
GENERATOR_MODEL = GENERATOR_MODEL_MAP.get(LLM_PROVIDER, "stub-generator-model")
REVIEWER_MODEL = REVIEWER_MODEL_MAP.get(LLM_PROVIDER, "stub-reviewer-model")
EVALUATOR_MODEL = EVALUATOR_MODEL_MAP.get(LLM_PROVIDER, "stub-evaluator-model")


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

# --- Prompting ---
# Basic prompt templates (can be refined)
GENERATION_SYSTEM_PROMPT = """
You are an AI assistant specialized in creating multiple-choice questions of high quality and difficulty for university students, given the provided context or instructions. Base the questions strictly on the provided context if available. Try to generate at least one question for each topic that is covered in the context. If the question or the answer or the distractors contain any piece of code, pseudocode or use special characters, enclose it in backticks: `code`.
For each question, generate:
- The question text.
- The correct answer.
- A list of distractors.

{custom_generator_instructions}

Output the questions as a JSON object with keys: "questions" (list of objects), where each object has keys: "text" (string), "correct_answer" (string), "distractors" (list of strings). OUTPUT ONLY THE JSON OBJECT, NOTHING ELSE.
"""

IMAGE_GENERATION_SYSTEM_PROMPT = """
You are an AI assistant specialized in creating educational multiple-choice questions based on images.
Given the provided image and optional context text, generate ONE multiple-choice question that requires understanding the image content.
Do not add a period at the end of the correct answer nor at the end of the distractors.
Provide:
- The question text.
- The correct answer.
- A list of distractors.

{custom_generator_instructions}

Output the question as a single JSON object with keys: "text" (string), "correct_answer" (string), "distractors" (list of strings). Focus the question on interpreting the visual information in the image, potentially using the context text for background. OUTPUT ONLY THE JSON OBJECT, NOTHING ELSE.
"""

REVIEW_SYSTEM_PROMPT = """
You are an AI assistant expert in evaluating the quality of multiple-choice questions and improving them if needed. You must also check that the correct answer cannot be easily differentiated from the distractors.
Review the following question based on clarity, correctness, plausibility of distractors, grammatical correctness, and adherence to good question design principles.
Take special care to ensure that all options are of similar length, and that the level of complexity of the wrong answers is similar to that of the correct answer.
Make sure that neither the correct answer nor the distractors end with a period.
If possible, avoid absolutes in the confounders, such as: never, always, exclusively, etc.
If the question or the answer or the distractors contain any piece of code, pseudocode or use special characters, enclose it in backticks: `code`.

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
# Timeout for LLM API calls (in seconds)
LLM_TIMEOUT = 120
# Max retries for LLM API calls
LLM_MAX_RETRIES = 2
# Base delay for retries (in seconds), will be subject to exponential backoff
RETRY_DELAY_BASE = 2 # Added for retry logic

# Add other configurations as needed

# --- Model Capabilities ---
# Keywords to identify models that support structured/JSON output modes we use.
# This is a simple check; models not listed might still work.
STRUCTURED_OUTPUT_SUPPORTED_MODELS = {
    "openai": ["*"],
    # For OpenRouter, support is widespread. We will assume any model the user
    # selects on OpenRouter is chosen for this capability.
    # See: https://openrouter.ai/models?fmt=cards&supported_parameters=structured_outputs
    "openrouter": ["*"], # Using a wildcard to mean "all"
    "google": ["*"], # Broader keywords
    "ollama": ["*"],
    "anthropic": [], # Not implemented with native JSON mode
    "replicate": [], # Not implemented with native JSON mode
} 