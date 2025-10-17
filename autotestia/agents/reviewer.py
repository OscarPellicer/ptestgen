import json
import time
import random
from typing import List, Dict, Any, Optional
from ..schemas import Question
from .. import config
import logging
from .base import BaseAgent
from ..llm_providers import get_provider, LLMProvider
from tqdm import tqdm


class QuestionReviewer(BaseAgent):
    """Agent responsible for reviewing and potentially improving questions."""

    def __init__(self,
                 criteria: dict = config.REVIEWER_CRITERIA,
                 use_llm: bool = config.DEFAULT_LLM_REVIEW_ENABLED,
                 llm_provider: str = config.LLM_PROVIDER,
                 model_name: str = config.REVIEWER_MODEL,
                 api_keys: Dict[str, str] = None):

        super().__init__()
        self.criteria = criteria
        self.provider: Optional[LLMProvider] = None
        self.use_llm = use_llm
        self.llm_provider_name = llm_provider

        if self.llm_provider_name == "stub":
            self.use_llm = False # Force disable if provider is stub
        
        if self.use_llm:
            try:
                self.provider = get_provider(
                    provider_name=llm_provider,
                    model_name=model_name,
                    api_keys=api_keys
                )
            except (ValueError, RuntimeError) as e:
                logging.error(f"Failed to initialize LLM provider for Reviewer: {e}. Disabling LLM review.")
                self.use_llm = False
        
        logging.info(f"Initializing QuestionReviewer (LLM Review Enabled: {self.use_llm})")
        if self.use_llm and self.provider:
            logging.info(f"  Reviewer Provider: {self.llm_provider_name}, Model: {self.provider.model_name}")

    def review_questions(self, questions: List[Question], custom_instructions: Optional[str] = None) -> List[Question]:
        """
        Reviews a list of questions based on predefined criteria and optionally LLM.
        """
        logging.info(f"Reviewing {len(questions)} questions...")
        reviewed_questions = []
        for q_orig in tqdm(questions, desc="Reviewing Questions"):
            q_reviewed = q_orig # Start with original

            if self.use_llm:
                q_reviewed = self._apply_llm_review(q_reviewed, custom_instructions)

            reviewed_questions.append(q_reviewed)
        logging.info("Review complete.")
        return reviewed_questions

    def _apply_llm_review(self, question: Question, custom_instructions: Optional[str] = None) -> Question:
        """Uses an LLM to review/score a question, incorporating custom instructions."""
        if not self.provider:
            logging.error(f"LLM provider not available. Skipping LLM review for question {question.id}.")
            return question

        logging.info(f"  LLM Reviewing Question {question.id} using {self.llm_provider_name} ({self.provider.model_name})...")

        question_dict = {
            "text": question.text,
            "correct_answer": question.correct_answer,
            "distractors": question.distractors,
            "explanation": question.explanation
        }
        try:
            question_json = json.dumps({k: v for k, v in question_dict.items() if v is not None}, indent=2, ensure_ascii=False)
        except TypeError as e:
            logging.error(f"Could not serialize Question {question.id} to JSON for LLM review: {e}. Skipping.")
            return question

        system_prompt_template = config.REVIEW_SYSTEM_PROMPT.replace(
            '{custom_reviewer_instructions}',
            custom_instructions if custom_instructions else ""
        )

        try:
            response_content = self.provider.review_question(
                system_prompt=system_prompt_template,
                question_json=question_json
            )

            if not response_content:
                logging.error(f"No review content received from LLM for question {question.id}.")
                return question

            parsed_review = self._parse_llm_json_response(response_content, expected_structure='review_dict')

            if parsed_review and isinstance(parsed_review, dict):
                reviewed_q_data = parsed_review.get("reviewed_question")
                if reviewed_q_data and isinstance(reviewed_q_data, dict) and all(k in reviewed_q_data for k in ["text", "correct_answer", "distractors"]):
                    # Basic validation
                    if isinstance(reviewed_q_data.get("text"), str) and \
                       isinstance(reviewed_q_data.get("correct_answer"), str) and \
                       isinstance(reviewed_q_data.get("distractors"), list) and \
                       len(reviewed_q_data.get("distractors")) == len(question.distractors):

                        logging.info(f"Applying LLM suggested revisions to Question {question.id}")
                        if question.original_details is None:
                            question.original_details = {
                                "text": question.text,
                                "correct_answer": question.correct_answer,
                                "distractors": list(question.distractors)
                            }
                        question.text = reviewed_q_data["text"]
                        question.correct_answer = reviewed_q_data["correct_answer"]
                        question.distractors = reviewed_q_data["distractors"]
                    else:
                        logging.warning(f"LLM returned 'reviewed_question' with invalid structure/types or distractor count: {reviewed_q_data}")
            else:
                logging.warning(f"Failed to parse a valid review response from LLM for question {question.id}")

        except Exception as e:
            logging.error(f"Error during LLM review call or processing for question {question.id}: {e}", exc_info=True)

        return question 