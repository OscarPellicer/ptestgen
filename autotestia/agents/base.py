import abc
import json
import logging
from typing import Any, Optional
import re

class BaseAgent(abc.ABC):
    """Abstract base class for all agents."""

    def __init__(self):
        pass

    def _parse_llm_json_response(self, response_content: str, expected_structure: str) -> Optional[Any]:
        """
        Parses the JSON response from the LLM.
        Handles responses that might be wrapped in ```json ... ```.
        """
        # Regex to find JSON content inside ```json ... ``` blocks
        match = re.search(r"```json\s*(\{.*\}|\[.*\])\s*```", response_content, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Fallback for when there's no markdown block, just the JSON
            json_str = response_content

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            agent_name = self.__class__.__name__
            logging.error(f"{agent_name}: Could not decode JSON: {e}. Content: '{response_content[:150]}...'")
            return None
