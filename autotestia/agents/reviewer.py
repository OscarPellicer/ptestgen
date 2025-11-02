from typing import List, Dict, Any, Optional
from ..schemas import QuestionRecord, QuestionStage, QuestionContent, ChangeMetrics
from .. import artifacts
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

    def review_questions(self, records: List[QuestionRecord], custom_instructions: Optional[str] = None) -> List[QuestionRecord]:
        """
        Reviews a list of question records.
        Updates each record with a 'reviewed' stage and change metrics.
        """
        logging.info(f"Reviewing {len(records)} question records...")
        reviewed_records = []
        for record in tqdm(records, desc="Reviewing Questions"):
            reviewed_record = self._apply_review(record, custom_instructions)
            reviewed_records.append(reviewed_record)
            
        logging.info("Review complete.")
        return reviewed_records

    def _apply_review(self, record: QuestionRecord, custom_instructions: Optional[str] = None) -> QuestionRecord:
        """Applies rule-based and/or LLM review to a single question record."""
        if not record.generated:
            logging.warning(f"Question record {record.question_id} has no 'generated' stage to review. Skipping.")
            return record

        reviewed_content: Optional[QuestionContent] = None

        if self.use_llm:
            reviewed_content = self._apply_llm_review(record.generated.content, custom_instructions)
        
        # If no LLM review or LLM review failed, use the original content
        if reviewed_content is None:
            reviewed_content = record.generated.content.copy(deep=True)

        # Create the new reviewed stage
        record.reviewed = QuestionStage(content=reviewed_content)
        
        # Calculate changes
        record.changes_gen_to_rev = artifacts.calculate_changes(record.generated, record.reviewed)
        
        return record

    def _apply_llm_review(self, original_content: QuestionContent, custom_instructions: Optional[str] = None) -> Optional[QuestionContent]:
        """Uses an LLM to review content and returns the new content, or None on failure."""
        if not self.provider:
            logging.error(f"LLM provider not available. Skipping LLM review.")
            return None

        logging.info(f"  LLM Reviewing content using {self.llm_provider_name} ({self.provider.model_name})...")
        
        # Pydantic v2 uses model_dump_json
        question_json = original_content.model_dump_json(indent=2)

        # Use .replace() for partial formatting to avoid KeyError
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
                logging.error(f"No review content received from LLM.")
                return None

            parsed_review = self._parse_llm_json_response(response_content, expected_structure='review_dict')

            if parsed_review and isinstance(parsed_review, dict):
                reviewed_q_data = parsed_review.get("reviewed_question")
                if reviewed_q_data and isinstance(reviewed_q_data, dict) and all(k in reviewed_q_data for k in ["text", "correct_answer", "distractors"]):
                    # Basic validation
                    if isinstance(reviewed_q_data.get("distractors"), list) and \
                       len(reviewed_q_data.get("distractors")) == len(original_content.distractors):
                        
                        logging.info(f"Applying LLM suggested revisions.")
                        return QuestionContent(**reviewed_q_data)
                    else:
                        logging.warning(f"LLM returned 'reviewed_question' with invalid structure/types or distractor count: {reviewed_q_data}")
            else:
                logging.warning(f"Failed to parse a valid review response from LLM.")

        except Exception as e:
            logging.error(f"Error during LLM review call or processing: {e}", exc_info=True)
        
        return None 