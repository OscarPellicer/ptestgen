import json
import time
import random
import logging
import sys
from typing import Dict, Any, Tuple, Type, Callable, Optional

from .. import config # Assuming this path is correct

class BaseLLMAgent:
    def __init__(self,
                 llm_provider: str,
                 model_name: str,
                 api_keys: Dict[str, str]):
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.client: Any = None
        self.api_keys = api_keys
        self.api_error_types: Tuple[Type[Exception], ...] = ()
        self.timeout_error_types: Tuple[Type[Exception], ...] = ()

        # Logging moved to child classes after super().__init__() for better context
        # logging.info(f"Initializing BaseLLMAgent for {self.__class__.__name__} with provider: {self.llm_provider}, model: {self.model_name}")
        
        # Initialize client unless it's a stub provider that doesn't need a client
        if self.llm_provider != "stub":
            self._initialize_client()
        else:
            logging.info(f"BaseLLMAgent: STUB provider ({self.model_name}) selected for {self.__class__.__name__}. Client not initialized.")


    def _initialize_client(self):
        """Initializes the LLM client based on the provider."""
        try:
            if self.llm_provider == "openai":
                if not self.api_keys.get("openai"): raise ValueError("OpenAI API key missing.")
                from openai import OpenAI, APIError, APITimeoutError
                self.client = OpenAI(api_key=self.api_keys["openai"], timeout=config.LLM_TIMEOUT)
                self.api_error_types = (APIError,)
                self.timeout_error_types = (APITimeoutError,)
            elif self.llm_provider == "openrouter":
                if not self.api_keys.get("openrouter"): raise ValueError("OpenRouter API key missing.")
                from openai import OpenAI, APIError, APITimeoutError
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_keys["openrouter"],
                    default_headers={
                        "HTTP-Referer": "https://github.com/OscarPellicer/AutoTestIA",
                        "X-Title": "AutoTestIA",
                    },
                    timeout=config.LLM_TIMEOUT
                )
                self.api_error_types = (APIError,)
                self.timeout_error_types = (APITimeoutError,)
            elif self.llm_provider == "google":
                if not self.api_keys.get("google"): raise ValueError("Google API key missing.")
                import google.generativeai as genai
                from google.api_core.exceptions import GoogleAPIError #, RetryError (more general)
                genai.configure(api_key=self.api_keys["google"])
                self.client = genai # Store the module
                self.api_error_types = (GoogleAPIError,)
                self.timeout_error_types = () # Google client handles retries/timeouts internally or raises GoogleAPIError
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
                # Replicate client uses REPLICATE_API_TOKEN env var by default if not passed to client constructor
                # but explicit client init can be replicate.Client(api_token=...)
                # For now, assuming module-level `replicate.run` uses env var.
                self.client = replicate # Store the module
                self.api_error_types = (ReplicateError,)
                self.timeout_error_types = () # Timeout handling might be part of ReplicateError or general request exceptions
            else:
                # This case should ideally not be reached if llm_provider == "stub" is handled before calling _initialize_client
                raise ValueError(f"Unsupported LLM provider for client initialization: {self.llm_provider}")
            
            logging.info(f"BaseLLMAgent: Successfully initialized client for {self.llm_provider} ({self.model_name}) in {self.__class__.__name__}.")

        except ImportError as e:
            logging.error(f"BaseLLMAgent: Failed to import library for '{self.llm_provider}' in {self.__class__.__name__}: {e}. LLM features will be impaired.")
            self.client = None
            raise RuntimeError(f"Failed to import required library for {self.llm_provider}: {e}") from e
        except ValueError as e: # Catch API key errors or unsupported provider
            logging.error(f"BaseLLMAgent: Configuration error for '{self.llm_provider}' in {self.__class__.__name__}: {e}. LLM features will be impaired.")
            self.client = None
            raise RuntimeError(f"Configuration error for {self.llm_provider}: {e}") from e
        except Exception as e:
            logging.error(f"BaseLLMAgent: Error initializing LLM client for '{self.llm_provider}' in {self.__class__.__name__}: {e}. LLM features will be impaired.", exc_info=True)
            self.client = None
            raise RuntimeError(f"An unexpected error occurred while initializing the LLM client for {self.llm_provider}: {e}") from e

    def _check_structured_output_support(self):
        """
        Checks if the current model is known to support structured outputs.
        Logs a warning if it might not be supported.
        """
        provider = self.llm_provider
        model = self.model_name
        
        supported_models = config.STRUCTURED_OUTPUT_SUPPORTED_MODELS.get(provider)

        if supported_models is None:
            # Provider not in our list, assume no support for our implementation
            logging.warning(f"Provider '{provider}' is not in the list of providers with known structured output support. JSON parsing may fail.")
            return

        if supported_models == ["*"]: # Wildcard for providers like OpenRouter
            return

        if not any(keyword in model for keyword in supported_models):
            warning_msg = (
                f"Model '{model}' for provider '{provider}' is not in the list of models known to support structured outputs. "
                "Generation may fail or produce malformed JSON.\n"
                "It is recommended to use a model known for reliable JSON output, for instance, by using the 'openrouter' provider.\n"
                "You can find a list of compatible OpenRouter models here: https://openrouter.ai/models?fmt=cards&supported_parameters=structured_outputs"
            )
            logging.warning(warning_msg)
            print(f"Warning: {warning_msg}", file=sys.stderr)

    def _call_llm_with_retry(self, api_call_func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Wrapper to handle retries for API calls with exponential backoff and jitter."""
        if not self.client and self.llm_provider != "stub": # Double check client exists
             logging.error(f"{self.__class__.__name__}: LLM client not available for provider {self.llm_provider}. Cannot make API call.")
             raise RuntimeError(f"LLM client not initialized for {self.llm_provider}")

        # Ensure error types are tuples for the except block
        timeout_errors = self.timeout_error_types if isinstance(self.timeout_error_types, tuple) else ()
        api_errors = self.api_error_types if isinstance(self.api_error_types, tuple) else ()

        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                return api_call_func(*args, **kwargs)
            except timeout_errors as e: # Specific timeout errors
                if attempt == config.LLM_MAX_RETRIES:
                    logging.error(f"{self.__class__.__name__}: API Timeout Error for {self.llm_provider} after {attempt + 1} attempts: {e}")
                    raise
                delay = (config.RETRY_DELAY_BASE ** attempt) + random.uniform(0, 0.5 * (config.RETRY_DELAY_BASE ** attempt)) # Exponential backoff with jitter
                logging.warning(f"{self.__class__.__name__}: API Timeout Error for {self.llm_provider} ({type(e).__name__}), retrying in {delay:.2f}s ({attempt + 1}/{config.LLM_MAX_RETRIES})...")
                time.sleep(delay)
            except (*api_errors, Exception) as e: # Specific API errors and then general exceptions
                # Check if it's one of the known API errors (if any are defined)
                is_known_api_error = api_errors and any(isinstance(e, err_type) for err_type in api_errors)
                
                # If it was a timeout error caught by the general Exception (e.g., if timeout_errors was empty)
                # This is a fallback, ideally specific timeout errors are caught above.
                is_general_timeout = not isinstance(e, timeout_errors) and ("timeout" in str(e).lower() or "timed out" in str(e).lower())


                if attempt == config.LLM_MAX_RETRIES:
                    error_type_str = "Known API Error" if is_known_api_error else ("Timeout-related Error" if is_general_timeout else "Unexpected Error during API call")
                    logging.error(f"{self.__class__.__name__}: {error_type_str} for {self.llm_provider} after {attempt + 1} attempts: {e}", exc_info=(not is_known_api_error and not is_general_timeout))
                    raise
                
                delay = (config.RETRY_DELAY_BASE ** attempt) + random.uniform(0, 0.5 * (config.RETRY_DELAY_BASE ** attempt))
                log_func = logging.warning # if is_known_api_error or is_general_timeout else logging.info
                error_desc = type(e).__name__
                if is_known_api_error: error_desc = f"Known API Error ({error_desc})"
                elif is_general_timeout: error_desc = f"Timeout-related Error ({error_desc})"

                log_func(f"{self.__class__.__name__}: {error_desc} for {self.llm_provider}: {e}. Retrying in {delay:.2f}s ({attempt + 1}/{config.LLM_MAX_RETRIES})...")
                time.sleep(delay)
        return None # Should be unreachable if an exception is always raised on the final attempt

    def _parse_llm_json_response(self, response_content: str, expected_structure: str) -> Any:
        """
        Attempts to parse the LLM's JSON response and validate its structure.
        Assumes LLM was instructed to return JSON (e.g., via API params or prompts).
        Args:
            response_content: The raw string content from the LLM.
            expected_structure: A string indicating the expected JSON structure
                                ('questions_list', 'single_question_dict', 'review_dict').
        Returns:
            The parsed data (e.g., list of question dicts, or a single dict) or None if parsing/validation fails.
        """
        if not response_content:
            logging.error(f"{self.__class__.__name__}: No response content to parse.")
            return None
        
        processed_content = response_content.strip()

        # Attempt to remove common markdown wrappers if present
        # Check for ```json ... ```
        if processed_content.startswith("```json") and processed_content.endswith("```"):
            processed_content = processed_content[len("```json"):-len("```")].strip()
        # Check for ``` ... ``` (if not caught by the above)
        elif processed_content.startswith("```") and processed_content.endswith("```"):
            processed_content = processed_content[len("```"):-len("```")].strip()
        # Sometimes, models might just start with "json" without backticks before the actual JSON
        elif processed_content.lower().startswith("json") and (processed_content[4:].lstrip().startswith("{") or processed_content[4:].lstrip().startswith("[")):
            processed_content = processed_content[len("json"):].strip()

        try:
            data = json.loads(processed_content)

            if expected_structure == 'questions_list':
                if not isinstance(data, dict) or "questions" not in data:
                    raise ValueError("Expected JSON object with a 'questions' key.")
                questions_list = data["questions"]
                if not isinstance(questions_list, list):
                    raise ValueError("The 'questions' key must contain a list.")
                for i, q_item in enumerate(questions_list):
                    if not isinstance(q_item, dict) or not all(k in q_item for k in ["text", "correct_answer", "distractors"]):
                        raise ValueError(f"Question item {i} is missing required keys (text, correct_answer, distractors). Found: {list(q_item.keys())}")
                    if not isinstance(q_item.get("distractors"), list):
                        raise ValueError(f"Question item {i} has 'distractors' which is not a list. Type: {type(q_item.get('distractors'))}")
                return questions_list
            elif expected_structure == 'single_question_dict':
                if not isinstance(data, dict) or not all(k in data for k in ["text", "correct_answer", "distractors"]):
                    raise ValueError("Expected single JSON object with keys: 'text', 'correct_answer', 'distractors'. Found: {list(data.keys())}")
                if not isinstance(data.get("distractors"), list):
                     raise ValueError(f"Single question has 'distractors' which is not a list. Type: {type(data.get('distractors'))}")
                return data
            elif expected_structure == 'review_dict':
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object (dict) for review output.")
                # Core keys for review scores. "reviewed_question" is optional and its structure validated by caller.
                # "review_comments" is also optional.
                # For now, we only check it's a dict. Caller handles content validation.
                # Example of stricter check (can be enabled if needed):
                # required_keys = ["difficulty_score", "quality_score"]
                # if not all(k in data for k in required_keys):
                #    logging.warning(f"{self.__class__.__name__}: Review response missing some expected keys (e.g., difficulty_score, quality_score): {list(data.keys())}")
                #    # Depending on strictness, could raise ValueError here.
                return data
            else:
                raise ValueError(f"Unknown expected_structure type: '{expected_structure}'")

        except json.JSONDecodeError as e:
            logging.error(f"{self.__class__.__name__}: Could not decode JSON response: {e}. Content (original, partial): '{response_content[:200]}', Content (processed, partial): '{processed_content[:200]}'")
            return None
        except ValueError as e: # Catches structure validation errors
            logging.error(f"{self.__class__.__name__}: Invalid response structure for '{expected_structure}': {e}. Content (processed, partial): '{processed_content[:200]}'")
            return None
        except Exception as e:
            logging.error(f"{self.__class__.__name__}: Unexpected error parsing LLM response: {e}. Content (processed, partial): '{processed_content[:200]}'", exc_info=True)
            return None 