import json
import random
from typing import List, Dict, Optional
from ..schemas import QuestionRecord, QuestionStage, EvaluationData
from .. import config
import logging
from .base import BaseAgent
from ..llm_providers import get_provider, LLMProvider
from tqdm import tqdm

class QuestionEvaluator(BaseAgent):
    """Agent responsible for evaluating the quality of questions."""

    def __init__(self,
                 use_llm: bool = True,
                 llm_provider: str = config.LLM_PROVIDER,
                 model_name: str = config.EVALUATOR_MODEL,
                 api_keys: Dict[str, str] = None):

        super().__init__()
        self.provider: Optional[LLMProvider] = None
        self.use_llm = use_llm
        self.llm_provider_name = llm_provider

        if self.llm_provider_name == "stub":
            self.use_llm = False
        
        if self.use_llm:
            try:
                self.provider = get_provider(
                    provider_name=llm_provider,
                    model_name=model_name,
                    api_keys=api_keys
                )
            except (ValueError, RuntimeError) as e:
                logging.error(f"Failed to initialize LLM provider for Evaluator: {e}. Disabling LLM evaluation.")
                self.use_llm = False
        
        logging.info(f"Initializing QuestionEvaluator (LLM Evaluation Enabled: {self.use_llm})")
        if self.use_llm and self.provider:
            logging.info(f"  Evaluator Provider: {self.llm_provider_name}, Model: {self.provider.model_name}")

    def evaluate_records(self, records: List[QuestionRecord], stage: str, custom_instructions: Optional[str] = None) -> List[QuestionRecord]:
        """Evaluates a list of QuestionRecords at a specific stage."""
        if not self.use_llm or not self.provider:
            logging.warning("LLM Evaluation is disabled. Skipping evaluation.")
            return records

        logging.info(f"Evaluating {len(records)} records (stage: {stage})...")
        
        for record in tqdm(records, desc=f"Evaluating Questions ({stage})"):
            stage_to_evaluate: Optional[QuestionStage] = None
            if stage == 'initial' and record.generated:
                stage_to_evaluate = record.generated
            elif stage == 'reviewed' and record.reviewed:
                stage_to_evaluate = record.reviewed
            # Add 'final' stage if needed later
            
            if stage_to_evaluate:
                evaluation_result = self._apply_llm_evaluation(stage_to_evaluate, custom_instructions)
                if evaluation_result:
                    stage_to_evaluate.evaluation = evaluation_result
            else:
                logging.warning(f"Could not find stage '{stage}' to evaluate for record {record.question_id}")
        
        logging.info("Evaluation complete.")
        return records

    def _apply_llm_evaluation(self, question_stage: QuestionStage, custom_instructions: Optional[str] = None) -> Optional[EvaluationData]:
        """Uses an LLM to evaluate a single question stage and returns EvaluationData."""
        content_to_eval = question_stage.content

        question_json = content_to_eval.model_dump_json(indent=2)

        system_prompt_template = config.EVALUATION_SYSTEM_PROMPT.replace(
            '{custom_evaluator_instructions}',
            custom_instructions if custom_instructions else ""
        )
        
        try:
            response_content = self.provider.evaluate_question(
                system_prompt=system_prompt_template,
                question_json=question_json
            )

            if not response_content:
                logging.error(f"No evaluation content received from LLM.")
                return None

            parsed_eval = self._parse_llm_json_response(response_content, expected_structure='evaluation_dict')

            if parsed_eval and isinstance(parsed_eval, dict):
                evaluation_result = EvaluationData()
                try:
                    evaluation_result.difficulty_score = round(float(parsed_eval.get("difficulty_score", 0.0)), 2)
                    evaluation_result.pedagogical_value = round(float(parsed_eval.get("pedagogical_value", 0.0)), 2)
                    evaluation_result.clarity_score = round(float(parsed_eval.get("clarity", 0.0)), 2)
                    evaluation_result.distractor_plausibility_score = round(float(parsed_eval.get("distractor_plausibility", 0.0)), 2)
                    guessed_idx = parsed_eval.get("guessed_correct_answer")
                    if guessed_idx is not None:
                        evaluation_result.evaluator_guessed_correctly = (int(guessed_idx) == 1)
                    evaluation_result.evaluation_comments = parsed_eval.get("evaluation_comment")
                    return evaluation_result
                except (ValueError, TypeError) as e:
                    logging.warning(f"LLM returned one or more invalid evaluation fields: {e}")
            else:
                logging.warning(f"Failed to parse a valid evaluation response from LLM.")
        
        except Exception as e:
            logging.error(f"Error during LLM evaluation: {e}", exc_info=True)

        return None
