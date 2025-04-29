# Configuration settings for AutoTestIA

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- LLM Configuration ---
# Select the provider: "openai", "google", "anthropic", "replicate", "stub"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "stub")

# API Keys from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# --- Model Selection ---
# Define models for each provider (using requested models or sensible defaults)
# Check provider documentation for the latest/most appropriate model names.
GENERATOR_MODEL_MAP = {
    "openai": os.getenv("OPENAI_GENERATOR_MODEL", "gpt-4o-mini"),
    "google": os.getenv("GOOGLE_GENERATOR_MODEL", "gemini-2.5-pro"),
    "anthropic": os.getenv("ANTHROPIC_GENERATOR_MODEL", "claude-3-7-sonnet"),
    "replicate": os.getenv("REPLICATE_GENERATOR_MODEL", "unsloth/meta-llama-3.3-70b-instruct"),
    "stub": "stub-generator-model"
}

REVIEWER_MODEL_MAP = { # Potentially use a cheaper model for review
    "openai": os.getenv("OPENAI_REVIEWER_MODEL", "gpt-4o-mini"),
    "google": os.getenv("GOOGLE_REVIEWER_MODEL", "gemini-2.5-pro"),
    "anthropic": os.getenv("ANTHROPIC_REVIEWER_MODEL", "claude-3-7-sonnet"), 
    "replicate": os.getenv("REPLICATE_REVIEWER_MODEL", "unsloth/meta-llama-3.3-70b-instruct"),
    "stub": "stub-reviewer-model"
}

# TODO: Add Evaluator Model Map (OE6)
EVALUATOR_MODEL = "stub-model" # For OE6

# Get the actual model names based on the selected provider
GENERATOR_MODEL = GENERATOR_MODEL_MAP.get(LLM_PROVIDER, "stub-generator-model")
REVIEWER_MODEL = REVIEWER_MODEL_MAP.get(LLM_PROVIDER, "stub-reviewer-model")


# --- Agent Settings ---
DEFAULT_NUM_QUESTIONS = 5
DEFAULT_NUM_OPTIONS = 4 # Including the correct answer
# Flag to enable LLM-based review (can be overridden by CLI arg)
DEFAULT_LLM_REVIEW_ENABLED = False

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
DEFAULT_OUTPUT_WOOCLAP_FILE = "output/wooclap_questions.xlsx" # Assuming Excel for Wooclap
DEFAULT_OUTPUT_REXAMS_DIR = "output/rexams/" # Directory for R/exams output files
DEFAULT_LANGUAGE = "Spanish"

# --- Prompting ---
# Basic prompt templates (can be refined)
GENERATION_SYSTEM_PROMPT = """
You are an AI assistant specialized in creating multiple-choice questions of high quality and difficulty for university students, given the provided context. Base the questions strictly on the provided context.
For each question, generate:
- The question text.
- The correct answer.
- A list of distractors.

Output the questions as a JSON object with keys: "questions" (list of objects), where each object has keys: "text" (string), "correct_answer" (string), "distractors" (list of strings).
"""

IMAGE_GENERATION_SYSTEM_PROMPT = """
You are an AI assistant specialized in creating educational multiple-choice questions based on images.
Given the provided image and optional context text, generate ONE multiple-choice question that requires understanding the image content.
Provide:
- The question text.
- The correct answer.
- A list of distractors.

Output the question as a single JSON object with keys: "text" (string), "correct_answer" (string), "distractors" (list of strings).
Focus the question on interpreting the visual information in the image, potentially using the context text for background.
"""

REVIEW_SYSTEM_PROMPT = """
You are an AI assistant expert in evaluating the quality of multiple-choice questions.
Review the following question based on clarity, correctness (assuming context it was based on was accurate), plausibility of distractors, grammatical correctness, and adherence to good question design principles.
Take special care to ensure that all options are of similar length, and that the level of complexity of the wrong answers is similar to that of the correct answer.
Provide scores for difficulty and quality between 0.0 (very poor) and 1.0 (excellent) and brief comments explaining your reasoning.
Finally, provide the corrected question (where all the comments from the review have been applied) in the same JSON format as the input question, under the key "reviewed_question".

Input Question (JSON format):
{question_json}

Output your review as a JSON object with keys: "difficulty_score" (float), "quality_score" (float), "review_comments" (string), "reviewed_question" (a JSON object with keys: "text", "correct_answer", "distractors").
"""


# --- Other ---
# Timeout for LLM API calls (in seconds)
LLM_TIMEOUT = 120
# Max retries for LLM API calls
LLM_MAX_RETRIES = 2

# Add other configurations as needed 