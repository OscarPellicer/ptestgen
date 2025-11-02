import logging
from typing import Any, Dict, Optional
from .base import LLMProvider
from .. import config
import base64

class GoogleProvider(LLMProvider):
    """Provider for Google's Generative AI models (Gemini)."""

    def _initialize_client(self) -> Any:
        """Initializes the Google Generative AI client."""
        api_key = self.api_keys.get("google")
        if not api_key:
            raise ValueError("Google API key missing.")
        try:
            import google.generativeai as genai
            from google.api_core.exceptions import GoogleAPIError
        except ImportError as e:
            logging.error("Failed to import 'google.generativeai'. Please install it.")
            raise RuntimeError("Missing required library: google-generativeai") from e
            
        genai.configure(api_key=api_key)
        # Store the module itself to access types like GenerationConfig
        self.api_error_types = (GoogleAPIError,)
        self.timeout_error_types = () # Google client handles this internally
        logging.info("Initialized Google GenAI client.")
        return genai

    def _generate_content(self, schema, prompts: list) -> Optional[str]:
        """Helper method to call the generate_content API."""
        model = self.client.GenerativeModel(self.model_name)
        generation_config = self.client.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )
        response = self._call_llm_with_retry(
            model.generate_content, prompts, generation_config=generation_config
        )
        return response.text if response else None

    def generate_questions_from_text(self, system_prompt: str, user_prompt: str, num_distractors: int) -> Optional[str]:
        from ..schemas import LLMQuestionList
        schema = LLMQuestionList.model_json_schema()

        if 'properties' in schema and 'questions' in schema['properties']:
            question_item_schema = schema['properties']['questions']['items']
            if 'properties' in question_item_schema and 'properties' in question_item_schema and 'distractors' in question_item_schema['properties']:
                question_item_schema['properties']['distractors']['minItems'] = num_distractors
                question_item_schema['properties']['distractors']['maxItems'] = num_distractors
        
        return self._generate_content(schema, [system_prompt, user_prompt])

    def generate_question_from_image(self, system_prompt: str, user_prompt: str, image_path: str, num_distractors: int) -> Optional[str]:
        from ..schemas import LLMQuestionItem
        from .openai_compatible import encode_image_to_base64, get_image_mime_type

        schema = LLMQuestionItem.model_json_schema()

        if 'properties' in schema and 'distractors' in schema['properties']:
            schema['properties']['distractors']['minItems'] = num_distractors
            schema['properties']['distractors']['maxItems'] = num_distractors

        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            return None
        mime_type = get_image_mime_type(image_path)
        image_part = {"mime_type": mime_type, "data": base64.b64decode(base64_image)}
        
        return self._generate_content(schema, [system_prompt, user_prompt, image_part])

    def review_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        from ..schemas import LLMReview
        full_prompt = system_prompt.format(question_json=question_json)
        return self._generate_content(LLMReview, [full_prompt])

    def evaluate_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        from ..schemas import LLMEvaluation
        full_prompt = system_prompt.format(question_json=question_json)
        return self._generate_content(LLMEvaluation, [full_prompt])

    def supports_vision(self) -> bool:
        """Checks if the Google model is known to support vision."""
        # Models like "gemini-pro-vision" and the latest "gemini-1.5-pro" support vision.
        return "vision" in self.model_name or "1.5" in self.model_name or "gemini-pro" in self.model_name