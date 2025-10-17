import abc
from typing import Any, Dict, Optional, List

class LLMProvider(abc.ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, model_name: str, api_keys: Dict[str, str]):
        self.model_name = model_name
        self.api_keys = api_keys
        self.client = self._initialize_client()

    @abc.abstractmethod
    def _initialize_client(self) -> Any:
        """Initializes and returns the specific LLM client."""
        pass

    @abc.abstractmethod
    def generate_questions_from_text(self, system_prompt: str, user_prompt: str, num_distractors: int) -> Optional[str]:
        """Generates questions from text content."""
        pass
    
    @abc.abstractmethod
    def generate_question_from_image(self, system_prompt: str, user_prompt: str, image_path: str, num_distractors: int) -> Optional[str]:
        """Generates a question from an image."""
        pass

    @abc.abstractmethod
    def review_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        """Reviews a single question."""
        pass

    @abc.abstractmethod
    def evaluate_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        """Evaluates a single question."""
        pass
        
    def _call_llm_with_retry(self, api_call_func, *args, **kwargs):
        """Wrapper to handle retries for API calls. Can be overridden by providers if needed."""
        # This is a simplified version. The more complex one from BaseLLMAgent can be moved here.
        # For now, let's keep it simple. The full implementation will be moved later.
        import time
        import random
        from .. import config

        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                return api_call_func(*args, **kwargs)
            except Exception as e:
                if attempt == config.LLM_MAX_RETRIES:
                    raise
                delay = (config.RETRY_DELAY_BASE ** attempt) + random.uniform(0, 0.5)
                print(f"API call failed with {type(e).__name__}, retrying in {delay:.2f}s...")
                time.sleep(delay)
        return None
