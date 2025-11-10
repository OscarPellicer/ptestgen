from typing import List, Dict, Optional
from ..schemas import QuestionRecord, QuestionStage, EvaluationData, QuestionContent
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

    def evaluate_records(self, 
                        records: List[QuestionRecord], 
                        stage: QuestionStage, 
                        custom_instructions: Optional[str] = None, 
                        language: str = config.DEFAULT_LANGUAGE
                        ) -> List[QuestionRecord]:
        """
        Evaluates a list of QuestionRecord objects at a specified stage.
        """
        for record in tqdm(records, desc=f"Evaluating Questions ({stage.value})"):
            
            stage_to_evaluate = None
            if stage == QuestionStage.FINAL:
                stage_to_evaluate = record.final
            elif stage == QuestionStage.REVIEWED:
                stage_to_evaluate = record.reviewed
            elif stage == QuestionStage.GENERATED:
                stage_to_evaluate = record.generated
            
            if not stage_to_evaluate:
                logging.warning(f"Could not find stage '{stage.value}' to evaluate for record {record.question_id}")
                continue

            evaluation_result = self.evaluate(
                question_content=stage_to_evaluate.content,
                custom_instructions=custom_instructions,
                language=language
            )
            if evaluation_result:
                stage_to_evaluate.evaluation = evaluation_result
        return records

    def evaluate(self, 
                 question_content: QuestionContent, 
                 custom_instructions: Optional[str] = None, 
                 language: str = config.DEFAULT_LANGUAGE) -> Optional[EvaluationData]:
        """
        Evaluates a single QuestionContent object.
        """
        content_to_eval = question_content

        question_json = content_to_eval.model_dump_json(indent=2)

        system_prompt_template = config.EVALUATION_SYSTEM_PROMPT.replace(
            '{custom_evaluator_instructions}',
            custom_instructions if custom_instructions else ""
        )
        system_prompt_template += f"\nMake sure that the question and the answers are in the following language: {language}. If not, translate them to the correct language."
        
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
