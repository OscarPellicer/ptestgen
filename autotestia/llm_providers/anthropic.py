import logging
from typing import Any, Dict, Optional
from .base import LLMProvider
from .. import config
import base64
import json

class AnthropicProvider(LLMProvider):
    """Provider for Anthropic's Claude models."""

    def _initialize_client(self) -> Any:
        """Initializes the Anthropic client."""
        api_key = self.api_keys.get("anthropic")
        if not api_key:
            raise ValueError("Anthropic API key missing.")
        try:
            from anthropic import Anthropic, APIError as AnthropicAPIError, APITimeoutError as AnthropicAPITimeoutError
        except ImportError as e:
            logging.error("Failed to import 'anthropic'. Please install it.")
            raise RuntimeError("Missing required library: anthropic") from e

        self.api_error_types = (AnthropicAPIError,)
        self.timeout_error_types = (AnthropicAPITimeoutError,)
        logging.info("Initialized Anthropic client.")
        return Anthropic(api_key=api_key, timeout=config.LLM_TIMEOUT)

    def _call_anthropic_messages_api(self, system_prompt: str, messages: list, max_tokens: int = 4096) -> Optional[str]:
        """Helper to call the Anthropic messages API."""
        message = self._call_llm_with_retry(
            self.client.messages.create,
            model=self.model_name,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages
        )
        if message and message.content:
            return next((block.text for block in message.content if block.type == 'text'), None)
        return None

    def generate_questions_from_text(self, system_prompt: str, user_prompt: str, num_distractors: int) -> Optional[str]:
        messages = [{"role": "user", "content": user_prompt}]
        return self._call_anthropic_messages_api(system_prompt, messages)

    def generate_question_from_image(self, system_prompt: str, user_prompt: str, image_path: str, num_distractors: int) -> Optional[str]:
        from .openai_compatible import encode_image_to_base64, get_image_mime_type

        base64_image = encode_image_to_base64(image_path)
        if not base64_image: return None
        mime_type = get_image_mime_type(image_path)
        
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": base64_image}},
                {"type": "text", "text": user_prompt}
            ]
        }]
        return self._call_anthropic_messages_api(system_prompt, messages)

    def review_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        full_prompt = system_prompt.format(question_json=question_json)
        messages = [{"role": "user", "content": full_prompt}]
        system_prompt_for_review = "You are an AI assistant reviewing a multiple-choice question."
        return self._call_anthropic_messages_api(system_prompt_for_review, messages)
    
    def evaluate_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        full_prompt = system_prompt.format(question_json=question_json)
        messages = [{"role": "user", "content": full_prompt}]
        system_prompt_for_eval = "You are an AI assistant evaluating a multiple-choice question."
        return self._call_anthropic_messages_api(system_prompt_for_eval, messages)
