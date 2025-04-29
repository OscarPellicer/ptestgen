import json
import time
import random
from typing import List, Dict, Any
from ..schemas import Question
from .. import config
import logging

# Import SDKs selectively if needed, or rely on generator having initialized them
# Assuming pipeline passes the client if needed, or re-initialize here.
# For simplicity, let's re-use the generator's initialization logic pattern if needed.
# from openai import OpenAI, APIError, APITimeoutError
# import google.generativeai as genai
# from anthropic import Anthropic, APIError as AnthropicAPIError, APITimeoutError as AnthropicAPITimeoutError
# import replicate

class QuestionReviewer:
    """Agent responsible for reviewing and potentially improving questions."""

    def __init__(self,
                 criteria: dict = config.REVIEWER_CRITERIA,
                 use_llm: bool = config.DEFAULT_LLM_REVIEW_ENABLED,
                 llm_provider: str = config.LLM_PROVIDER,
                 model_name: str = config.REVIEWER_MODEL,
                 api_keys: Dict[str, str] = None):

        self.criteria = criteria
        self.use_llm = use_llm
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.client = None
        self.api_keys = api_keys or {
            "openai": config.OPENAI_API_KEY,
            "google": config.GOOGLE_API_KEY,
            "anthropic": config.ANTHROPIC_API_KEY,
            "replicate": config.REPLICATE_API_TOKEN,
        }
        self.api_error_types = ()
        self.timeout_error_types = ()

        logging.info(f"Initializing QuestionReviewer (LLM Review Enabled: {self.use_llm})")
        if self.use_llm:
            logging.info(f"  Reviewer Provider: {self.llm_provider}, Model: {self.model_name}")
            try:
                # Conditional Imports and Client Initialization
                if self.llm_provider == "openai":
                    if not self.api_keys.get("openai"): raise ValueError("OpenAI API key missing.")
                    from openai import OpenAI, APIError, APITimeoutError
                    self.client = OpenAI(api_key=self.api_keys["openai"], timeout=config.LLM_TIMEOUT)
                    self.api_error_types = (APIError,)
                    self.timeout_error_types = (APITimeoutError,)
                elif self.llm_provider == "google":
                    if not self.api_keys.get("google"): raise ValueError("Google API key missing.")
                    import google.generativeai as genai
                    from google.api_core.exceptions import GoogleAPIError
                    genai.configure(api_key=self.api_keys["google"])
                    self.client = genai
                    self.api_error_types = (GoogleAPIError,)
                    self.timeout_error_types = ()
                elif self.llm_provider == "anthropic":
                    if not self.api_keys.get("anthropic"): raise ValueError("Anthropic API key missing.")
                    from anthropic import Anthropic, APIError as AnthropicAPIError, APITimeoutError as AnthropicAPITimeoutError
                    self.client = Anthropic(api_key=self.api_keys["anthropic"], timeout=config.LLM_TIMEOUT)
                    self.api_error_types = (AnthropicAPIError,)
                    self.timeout_error_types = (AnthropicAPITimeoutError,)
                elif self.llm_provider == "replicate":
                    if not self.api_keys.get("replicate"): raise ValueError("Replicate API token missing.")
                    import replicate
                    from replicate.exceptions import ReplicateError
                    self.replicate_token = self.api_keys["replicate"]
                    self.client = replicate
                    self.api_error_types = (ReplicateError,)
                    self.timeout_error_types = ()
                elif self.llm_provider == "stub":
                    logging.info("  LLM Review set to STUB mode.")
                    self.use_llm = False # Force disable LLM if provider is stub
                else:
                    raise ValueError(f"Unsupported LLM provider for review: {self.llm_provider}")

            except ImportError as e:
                logging.error(f"Failed to import required library for reviewer provider '{self.llm_provider}': {e}. Disabling LLM review.")
                self.client = None
                self.use_llm = False
            except Exception as e:
                logging.error(f"Error initializing LLM client for Reviewer ({self.llm_provider}): {e}. Disabling LLM review.", exc_info=True)
                self.client = None
                self.use_llm = False

    # Re-use helper methods from Generator (or move to a shared utils module)
    def _call_llm_with_retry(self, api_call_func, *args, **kwargs):
        """Wrapper to handle retries for API calls."""
        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                return api_call_func(*args, **kwargs)
            except self.timeout_error_types as e:
                if attempt == config.LLM_MAX_RETRIES:
                    logging.error(f"API Timeout Error after {attempt + 1} attempts: {e}")
                    raise
                logging.warning(f"API Timeout Error, retrying ({attempt + 1}/{config.LLM_MAX_RETRIES})...")
                time.sleep(2 ** attempt)
            except (self.api_error_types, Exception) as e:
                 is_known_api_error = any(isinstance(e, err_type) for err_type in self.api_error_types)
                 if attempt == config.LLM_MAX_RETRIES:
                     error_type = "API Error" if is_known_api_error else "Unexpected Error"
                     logging.error(f"{error_type} after {attempt + 1} attempts: {e}", exc_info=(not is_known_api_error))
                     raise
                 log_func = logging.warning if is_known_api_error else logging.info
                 log_func(f"API Error: {e}. Retrying ({attempt + 1}/{config.LLM_MAX_RETRIES})...")
                 time.sleep(2 ** attempt)
        return None

    def _parse_llm_response(self, response_content: str, expected_type='dict') -> Any:
        """Attempts to parse the LLM's JSON response."""
        try:
            # Handle potential wrapping ```json ... ``` or ``` ... ```
            response_content = response_content.strip()
            if response_content.startswith("```json"):
                response_content = response_content[len("```json"):].strip()
            elif response_content.startswith("```"):
                 response_content = response_content[len("```"):].strip()
            if response_content.endswith("```"):
                 response_content = response_content[:-len("```")].strip()

            if response_content.startswith("json"):
                 response_content = response_content[len("json"):].strip()

            data = json.loads(response_content)

            # Basic type check
            if expected_type == 'dict' and not isinstance(data, dict):
                 raise ValueError("Expected a JSON object (dict).")
            # Add other type checks if needed (e.g., check keys for reviewer response)
            if expected_type == 'dict' and not all(k in data for k in ["difficulty_score", "quality_score", "review_comments", "reviewed_question"]):
                logging.warning(f"Reviewer response missing some expected keys: {data.keys()}")
                # Allow partial success if some keys exist? For now, treat as invalid.
                # raise ValueError("Reviewer JSON response missing expected keys.")


            return data
        except json.JSONDecodeError as e:
            logging.error(f"Reviewer: Could not decode JSON response: {e}")
            logging.error(f"Reviewer Raw response content was:\n---\n{response_content}\n---")
            return None
        except ValueError as e:
             logging.error(f"Reviewer: Invalid response structure: {e}")
             logging.error(f"Reviewer Raw response content was:\n---\n{response_content}\n---")
             return None
        except Exception as e:
             logging.error(f"Reviewer: Unexpected error parsing response: {e}", exc_info=True)
             logging.error(f"Reviewer Raw response content was:\n---\n{response_content}\n---")
             return None

    def review_questions(self, questions: List[Question]) -> List[Question]:
        """Reviews a list of questions based on predefined criteria and optionally LLM."""
        logging.info(f"Reviewing {len(questions)} questions...")
        reviewed_questions = []
        for q_orig in questions:
            # Apply rule-based checks first
            # q_reviewed = self._apply_review_rules(q_orig)
            q_reviewed = q_orig
            # Then apply LLM review if enabled and client is ready
            if self.use_llm and self.client:
                q_reviewed = self._apply_llm_review(q_reviewed)
            reviewed_questions.append(q_reviewed)
        logging.info("Review complete.")
        return reviewed_questions

    def _apply_review_rules(self, question: Question) -> Question:
        """Applies basic rule-based checks based on self.criteria."""
        comments = question.review_comments[:] # Preserve previous comments
        score = question.quality_score if question.quality_score is not None else 1.0

        # Combine all options for length check
        all_options = [question.correct_answer] + question.distractors
        min_len = self.criteria.get("min_option_length", 0)
        max_len = self.criteria.get("max_option_length", float('inf'))
        length_issue = False
        for i, option in enumerate(all_options):
            option_label = f"Correct Answer" if i == 0 else f"Distractor {i}"
            if len(option) < min_len:
                comments.append(f"Rule: {option_label} too short (len {len(option)} < {min_len}).")
                length_issue = True
            if len(option) > max_len:
                comments.append(f"Rule: {option_label} too long (len {len(option)} > {max_len}).")
                length_issue = True
        if length_issue: score = max(0.0, score - 0.1)

        # Check for absolute statements in distractors only
        absolute_statements = self.criteria.get("avoid_absolute_statements", [])
        absolute_issue = False
        if absolute_statements:
            for i, distractor in enumerate(question.distractors):
                if any(stmt in distractor.lower() for stmt in absolute_statements):
                    comments.append(f"Rule: Distractor {i+1} uses absolute term (e.g., 'always', 'never').")
                    absolute_issue = True
            if absolute_issue: score = max(0.0, score - 0.05)

        question.quality_score = round(max(0.0, min(1.0, score)), 2)
        question.review_comments = list(set(comments)) # Remove duplicate rule comments
        return question

    def _apply_llm_review(self, question: Question) -> Question:
        """Uses an LLM to review/score a question."""
        logging.info(f"  LLM Reviewing Question {question.id} using {self.llm_provider} ({self.model_name})...")

        # Prepare input for LLM using the new schema
        question_dict = {
            "text": question.text,
            "correct_answer": question.correct_answer,
            "distractors": question.distractors,
            "explanation": question.explanation # Include explanation if available
        }
        try:
            # Ensure dict keys are strings if any non-string keys somehow exist
            question_json = json.dumps({str(k): v for k, v in question_dict.items()}, indent=2, ensure_ascii=False)
        except TypeError as e:
            logging.error(f"Could not serialize Question {question.id} to JSON for LLM review: {e}. Skipping LLM review.")
            return question

        # Format the system prompt
        review_prompt = config.REVIEW_SYSTEM_PROMPT.format(question_json=question_json)

        try:
            response_content = None
            # --- Provider-specific calls ---
            if self.llm_provider == "openai":
                completion = self._call_llm_with_retry(
                    self.client.chat.completions.create,
                    model=self.model_name,
                    response_format={ "type": "json_object" },
                    messages=[{"role": "system", "content": review_prompt}]
                )
                response_content = completion.choices[0].message.content
            elif self.llm_provider == "google":
                 model = self.client.GenerativeModel(self.model_name)
                 generation_config = self.client.types.GenerationConfig(response_mime_type="application/json")
                 response = self._call_llm_with_retry(
                     model.generate_content, [review_prompt], generation_config=generation_config
                 )
                 response_content = response.text
            elif self.llm_provider == "anthropic":
                 # Separate system/user prompts for Anthropic
                 system_instr = config.REVIEW_SYSTEM_PROMPT.split("Input Question (JSON format):")[0].strip()
                 user_data = f"Input Question (JSON format):\n{question_json}\n\nOutput your review as a JSON object with keys: \"difficulty_score\" (float), \"quality_score\" (float), \"review_comments\" (string), \"reviewed_question\" (a JSON object with keys: \"text\", \"correct_answer\", \"distractors\")." # Reiterate output format
                 message = self._call_llm_with_retry(
                     self.client.messages.create,
                     model=self.model_name, max_tokens=1500, system=system_instr, messages=[{"role": "user", "content": user_data}]
                 )
                 response_content = next((block.text for block in message.content if block.type == 'text'), None)
            elif self.llm_provider == "replicate":
                 output = self._call_llm_with_retry(
                     self.client.run, self.model_name, input={"prompt": review_prompt}
                 )
                 response_content = "".join(output)

            # --- Process response ---
            if not response_content:
                 logging.error(f"No review content received from LLM for question {question.id}.")
                 return question

            # Expect a dict with specific keys
            parsed_review = self._parse_llm_response(response_content, expected_type='dict')

            if parsed_review and isinstance(parsed_review, dict):
                # Extract new fields
                llm_diff_score = parsed_review.get("difficulty_score")
                llm_qual_score = parsed_review.get("quality_score")
                llm_comments_str = parsed_review.get("review_comments") # Expecting single string now
                reviewed_q_data = parsed_review.get("reviewed_question")

                # Update scores
                if llm_diff_score is not None:
                    try:
                        question.difficulty_score = round(float(llm_diff_score), 2)
                    except (ValueError, TypeError):
                        logging.warning(f"LLM returned invalid difficulty score: {llm_diff_score}")
                else:
                    question.review_comments.append("LLM Review: Difficulty score not provided.")

                if llm_qual_score is not None:
                    try:
                        # Blend or replace? Let's blend quality score.
                        current_score = question.quality_score if question.quality_score is not None else 0.7
                        blend_factor = 0.6
                        new_score = (current_score * (1 - blend_factor)) + (float(llm_qual_score) * blend_factor)
                        question.quality_score = round(max(0.0, min(1.0, new_score)), 2)
                    except (ValueError, TypeError):
                        logging.warning(f"LLM returned invalid quality score: {llm_qual_score}")
                else:
                    question.review_comments.append("LLM Review: Quality score not provided.")

                # Add comments (now a single string)
                if llm_comments_str and isinstance(llm_comments_str, str):
                    question.review_comments.append(f"LLM Review: {llm_comments_str}")
                elif not llm_comments_str:
                    question.review_comments.append("LLM Review: No comments provided.")

                # Handle reviewed question data
                if reviewed_q_data and isinstance(reviewed_q_data, dict) and all(k in reviewed_q_data for k in ["text", "correct_answer", "distractors"]):
                    # Basic validation of the reviewed data
                    if isinstance(reviewed_q_data["text"], str) and \
                        isinstance(reviewed_q_data["correct_answer"], str) and \
                        isinstance(reviewed_q_data["distractors"], list):
                        # Option 1: Overwrite original question data
                        logging.info(f"Applying LLM suggested revisions to Question {question.id}")
                        # --> Store original data before overwriting, if not already stored <--
                        if question.original_details is None:
                            question.original_details = {
                                "text": question.text,
                                "correct_answer": question.correct_answer,
                                "distractors": list(question.distractors) # Store a copy
                            }
                        # --> Now overwrite <--
                        question.text = reviewed_q_data["text"]
                        question.correct_answer = reviewed_q_data["correct_answer"]
                        question.distractors = reviewed_q_data["distractors"]
                        question.review_comments.append("LLM Review: Applied suggested revisions.")
                        # Option 2: Store suggestion separately (e.g., add a new field to Question schema)
                        # question.suggested_revision = reviewed_q_data
                    else:
                        logging.warning(f"LLM returned 'reviewed_question' with invalid structure/types: {reviewed_q_data}")
                        question.review_comments.append("LLM Review: Suggestion ignored (invalid format).")
                #else:
                #    logging.debug(f"No 'reviewed_question' data provided by LLM for Q {question.id}.")


            else:
                question.review_comments.append("LLM Review: Failed to parse valid review response.")

        except Exception as e:
            logging.error(f"Error during LLM review call or processing for question {question.id}: {e}", exc_info=True)
            question.review_comments.append(f"LLM Review Error: Processing failed.")

        # Clean up comments list
        question.review_comments = list(set(question.review_comments))
        return question 