from typing import List, Dict, Any, Optional
from ..schemas import QuestionRecord, QuestionStage, QuestionContent, QuestionStageContent, ChangeMetrics
from .. import artifacts
from .. import config
import logging
from .base import BaseAgent
from ..llm_providers import get_provider, LLMProvider
from tqdm import tqdm
import re
import unicodedata

# Characters that should survive a review untouched in Spanish/Catalan/etc. texts.
_NON_ASCII_LETTER = re.compile(r"[^\x00-\x7f]")
_SUSPICIOUS = re.compile(r"[#&][a-záéíóúñ]|[a-záéíóúñ][#&]|[\ufffd]|·¡")


def _all_text(content) -> str:
    parts = [content.text or "", content.correct_answer or ""] + list(content.distractors or [])
    return " ".join(parts)


def review_corrupts_characters(original, reviewed) -> bool:
    """Detects reviews that mangle non-ASCII characters (seen with some models via
    structured output: 'clasificaci#n', 'categor&as', 'clculo', '·¡A diferencia')."""
    before, after = _all_text(original), _all_text(reviewed)
    if _SUSPICIOUS.search(after) and not _SUSPICIOUS.search(before):
        return True
    # Same letter with a different diacritic than in the original (e.g. 'ù' where the
    # original only had 'ú') is a transcoding error, not an editorial change.
    def base(c):
        return unicodedata.normalize("NFD", c)[0]
    old_chars = set(_NON_ASCII_LETTER.findall(before))
    new_chars = set(_NON_ASCII_LETTER.findall(after)) - old_chars
    old_bases = {base(c) for c in old_chars}
    if any(unicodedata.category(c).startswith("L") and base(c) in old_bases for c in new_chars):
        return True
    n_before = len(_NON_ASCII_LETTER.findall(unicodedata.normalize("NFC", before)))
    n_after = len(_NON_ASCII_LETTER.findall(unicodedata.normalize("NFC", after)))
    # Reviews shorten text a bit, but losing most accents means the encoding broke.
    return n_before >= 4 and n_after < 0.5 * n_before * (len(after) / max(len(before), 1))


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
            original = record.generated.content
            for attempt in range(2):
                reviewed_content = self._apply_llm_review(original, custom_instructions)
                if reviewed_content is None or not review_corrupts_characters(original, reviewed_content):
                    break
                logging.warning(
                    f"Review of {record.question_id} corrupted non-ASCII characters (attempt {attempt + 1}); "
                    + ("retrying." if attempt == 0 else "keeping the generated version.")
                )
                reviewed_content = None
        
        # If no LLM review or LLM review failed, use the original content
        if reviewed_content is None:
            reviewed_content = record.generated.content.copy(deep=True)

        # Create the new reviewed stage
        record.reviewed = QuestionStageContent(content=reviewed_content)
        
        # Calculate changes
        record.changes_gen_to_rev = artifacts.calculate_changes(record.generated, record.reviewed)
        
        return record

    def _apply_llm_review(self, original_content: QuestionContent, custom_instructions: Optional[str] = None) -> Optional[QuestionContent]:
        """Uses an LLM to review content and returns the new content, or None on failure."""
        if not self.provider:
            logging.error(f"LLM provider not available. Skipping LLM review.")
            return None
        if original_content.is_open_answer:
            logging.info("Skipping LLM review for open-answer question; preserving generated expected answer and rubric.")
            return original_content.copy(deep=True)

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
                        return original_content.model_copy(update={
                            "text": reviewed_q_data["text"],
                            "correct_answer": reviewed_q_data["correct_answer"],
                            "distractors": reviewed_q_data["distractors"],
                        })
                    else:
                        logging.warning(f"LLM returned 'reviewed_question' with invalid structure/types or distractor count: {reviewed_q_data}")
            else:
                logging.warning(f"Failed to parse a valid review response from LLM.")

        except Exception as e:
            logging.error(f"Error during LLM review call or processing: {e}", exc_info=True)
        
        return None 

