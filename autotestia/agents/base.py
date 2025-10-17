import abc
import json
import logging
from typing import Any

class BaseAgent(abc.ABC):
    """Abstract base class for all agents."""

    def __init__(self):
        pass

    def _parse_llm_json_response(self, response_content: str, expected_structure: str) -> Any:
        """
        Attempts to parse the LLM's JSON response and validate its structure.
        """
        if not response_content:
            logging.error(f"{self.__class__.__name__}: No response content to parse.")
            return None
        
        processed_content = response_content.strip()
        if processed_content.startswith("```json") and processed_content.endswith("```"):
            processed_content = processed_content[len("```json"):-len("```")].strip()
        elif processed_content.startswith("```") and processed_content.endswith("```"):
            processed_content = processed_content[len("```"):-len("```")].strip()

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
                        raise ValueError(f"Question item {i} is missing required keys.")
                return questions_list
            elif expected_structure == 'single_question_dict':
                if not isinstance(data, dict) or not all(k in data for k in ["text", "correct_answer", "distractors"]):
                    raise ValueError("Expected single JSON object with required keys.")
                return data
            elif expected_structure == 'review_dict':
                 if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object (dict) for review output.")
                 return data
            elif expected_structure == 'evaluation_dict':
                 required_keys = ["difficulty_score", "pedagogical_value", "clarity", "distractor_plausibility", "evaluation_comment"]
                 if not isinstance(data, dict) or not all(k in data for k in required_keys):
                     raise ValueError(f"Expected JSON object with keys: {required_keys}.")
                 return data
            else:
                raise ValueError(f"Unknown expected_structure type: '{expected_structure}'")

        except json.JSONDecodeError as e:
            logging.error(f"{self.__class__.__name__}: Could not decode JSON: {e}. Content: '{processed_content[:200]}'")
            return None
        except ValueError as e:
            logging.error(f"{self.__class__.__name__}: Invalid structure for '{expected_structure}': {e}.")
            return None
        except Exception as e:
            logging.error(f"{self.__class__.__name__}: Unexpected error parsing response: {e}", exc_info=True)
            return None
