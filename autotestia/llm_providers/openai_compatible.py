import logging
from typing import Any, Dict, Optional, Tuple, Type
from .base import LLMProvider
from .. import config
import os
import base64

# Helper functions for image processing, moved from generator.py
def encode_image_to_base64(image_path):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logging.error(f"Error encoding image {image_path}: {e}", exc_info=True)
        return None

def get_image_mime_type(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext == ".png": return "image/png"
    elif ext in [".jpg", ".jpeg"]: return "image/jpeg"
    elif ext == ".gif": return "image/gif"
    elif ext == ".bmp": return "image/bmp"
    return "application/octet-stream"

class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI, OpenRouter, and other OpenAI-compatible APIs like Ollama."""

    def __init__(self, provider: str, model_name: str, api_keys: Dict[str, str]):
        self.provider = provider
        self.api_error_types: Tuple[Type[Exception], ...] = ()
        self.timeout_error_types: Tuple[Type[Exception], ...] = ()
        super().__init__(model_name, api_keys)

    def _initialize_client(self) -> Any:
        """Initializes the OpenAI client for the specified compatible provider."""
        try:
            from openai import OpenAI, APIError, APITimeoutError
        except ImportError as e:
            logging.error(f"Failed to import 'openai' library. Please install it with 'pip install openai'.")
            raise RuntimeError("Missing required library: openai") from e

        api_key = None
        base_url = None
        
        if self.provider == "openai":
            api_key = self.api_keys.get("openai")
            if not api_key: raise ValueError("OpenAI API key missing.")
        elif self.provider == "openrouter":
            api_key = self.api_keys.get("openrouter")
            if not api_key: raise ValueError("OpenRouter API key missing.")
            base_url = "https://openrouter.ai/api/v1"
        elif self.provider == "ollama":
            api_key = "ollama" # As per ollama docs
            base_url = config.OLLAMA_BASE_URL # Assumes OLLAMA_BASE_URL is in config
        else:
            raise ValueError(f"Unsupported provider for OpenAICompatibleProvider: {self.provider}")
        
        self.api_error_types = (APIError,)
        self.timeout_error_types = (APITimeoutError,)

        client_params = {
            "api_key": api_key,
            "timeout": config.LLM_TIMEOUT
        }
        if base_url:
            client_params["base_url"] = base_url

        client = OpenAI(**client_params)
        logging.info(f"Initialized OpenAI client for provider '{self.provider}'")
        return client

    def _construct_base_params(self, schema: dict) -> dict:
        """Constructs the base parameters for an API call, including structured output format."""
        params = {"model": self.model_name}
        if self.provider == "openrouter":
             params["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output", # A generic name
                    "strict": True,
                    "schema": schema
                }
            }
        elif self.provider == "ollama":
             # Use standard json_object mode, which Ollama's OpenAI endpoint supports.
             params["response_format"] = {"type": "json_object"}
        else: # openai
            params["response_format"] = {"type": "json_object"}
        
        return params

    def supports_vision(self) -> bool:
        """
        Checks if the model is likely to support vision.
        This is a heuristic based on common naming conventions.
        """
        return True # Assume all models support vision

    def generate_questions_from_text(self, system_prompt: str, user_prompt: str, num_distractors: int) -> Optional[str]:
        from ..schemas import LLMQuestionList
        schema = LLMQuestionList.model_json_schema()

        # Add constraints for the number of distractors
        if 'properties' in schema and 'questions' in schema['properties']:
            question_item_schema = schema['properties']['questions']['items']
            if 'properties' in question_item_schema and 'properties' in question_item_schema and 'distractors' in question_item_schema['properties']:
                question_item_schema['properties']['distractors']['minItems'] = num_distractors
                question_item_schema['properties']['distractors']['maxItems'] = num_distractors

        params = self._construct_base_params(schema)
        params["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        completion = self._call_llm_with_retry(
            self.client.chat.completions.create, **params
        )
        return completion.choices[0].message.content if completion else None

    def generate_question_from_image(self, system_prompt: str, user_prompt: str, image_path: str, num_distractors: int) -> Optional[str]:
        from ..schemas import LLMQuestionList
        schema = LLMQuestionList.model_json_schema()

        # Add constraints for the number of distractors
        if 'properties' in schema and 'questions' in schema['properties']:
            question_item_schema = schema['properties']['questions']['items']
            if 'properties' in question_item_schema and 'properties' in question_item_schema and 'distractors' in question_item_schema['properties']:
                question_item_schema['properties']['distractors']['minItems'] = num_distractors
                question_item_schema['properties']['distractors']['maxItems'] = num_distractors
        
        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            return None
        mime_type = get_image_mime_type(image_path)

        params = self._construct_base_params(schema)
        params["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
            ]}
        ]
        params["max_tokens"] = 4096

        completion = self._call_llm_with_retry(
            self.client.chat.completions.create, **params
        )
        return completion.choices[0].message.content if completion else None

    def review_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        from ..schemas import LLMReview
        schema = LLMReview.model_json_schema()

        params = self._construct_base_params(schema)
        full_prompt = system_prompt.format(question_json=question_json)
        params["messages"] = [{"role": "system", "content": full_prompt}]

        completion = self._call_llm_with_retry(
            self.client.chat.completions.create, **params
        )
        return completion.choices[0].message.content if completion else None

    def evaluate_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        from ..schemas import LLMEvaluation
        schema = LLMEvaluation.model_json_schema()

        params = self._construct_base_params(schema)
        full_prompt = system_prompt.format(question_json=question_json)
        params["messages"] = [{"role": "system", "content": full_prompt}]
        
        completion = self._call_llm_with_retry(
            self.client.chat.completions.create, **params
        )
        return completion.choices[0].message.content if completion else None
    
    # We can move the full retry logic from BaseLLMAgent here later.
    # For now, inheriting the simple one from base.py
