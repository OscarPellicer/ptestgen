import json
import random
from typing import List, Dict, Optional
from ..schemas import Question, EvaluationData
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

    def evaluate_questions(self, questions: List[Question], stage: str, custom_instructions: Optional[str] = None) -> List[Question]:
        """Evaluates a list of questions using an LLM."""
        if not self.use_llm or not self.provider:
            logging.warning("LLM Evaluation is disabled. Skipping evaluation.")
            return questions

        logging.info(f"Evaluating {len(questions)} questions (stage: {stage})...")
        evaluated_questions = []
        for q in tqdm(questions, desc=f"Evaluating Questions ({stage})"):
            evaluated_q = self._apply_llm_evaluation(q, stage, custom_instructions)
            evaluated_questions.append(evaluated_q)
        
        logging.info("Evaluation complete.")
        return evaluated_questions

    def _apply_llm_evaluation(self, question: Question, stage: str, custom_instructions: Optional[str] = None) -> Question:
        """Uses an LLM to evaluate a single question."""

        # Per user request, do not shuffle options. The model should guess the first is correct.
        options = question.options[:] 

        # The object sent to the LLM should not reveal the correct answer
        question_dict_for_llm = {
            "text": question.text,
            "options": options,
            "explanation": question.explanation
        }
        try:
            question_json = json.dumps({k: v for k, v in question_dict_for_llm.items() if v is not None}, indent=2, ensure_ascii=False)
        except TypeError as e:
            logging.error(f"Could not serialize Question {question.id} to JSON for evaluation: {e}. Skipping.")
            return question

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
                logging.error(f"No evaluation content received from LLM for question {question.id}.")
                return question

            parsed_eval = self._parse_llm_json_response(response_content, expected_structure='evaluation_dict')

            if parsed_eval and isinstance(parsed_eval, dict):
                difficulty = parsed_eval.get("difficulty_score")
                pedagogy = parsed_eval.get("pedagogical_value")
                clarity = parsed_eval.get("clarity")
                plausibility = parsed_eval.get("distractor_plausibility")
                guessed_answer_idx = parsed_eval.get("guessed_correct_answer")
                comment = parsed_eval.get("evaluation_comment")
                
                evaluation_result = EvaluationData()

                try:
                    if difficulty is not None:
                        evaluation_result.difficulty_score = round(float(difficulty), 2)
                    if pedagogy is not None:
                        evaluation_result.pedagogical_value = round(float(pedagogy), 2)
                    if clarity is not None:
                        evaluation_result.clarity_score = round(float(clarity), 2)
                    if plausibility is not None:
                        evaluation_result.distractor_plausibility_score = round(float(plausibility), 2)
                except (ValueError, TypeError) as e:
                    logging.warning(f"LLM returned one or more invalid scores: {e}")

                if guessed_answer_idx is not None:
                    try:
                        # The correct answer is always at index 0. LLM provides a 1-based index.
                        evaluation_result.evaluator_guessed_correctly = (int(guessed_answer_idx) == 1)
                    except (ValueError, TypeError):
                        logging.warning(f"LLM returned an invalid index for guessed answer: {guessed_answer_idx}")
                
                if comment and isinstance(comment, str):
                    evaluation_result.evaluation_comments.append(comment)
                
                if stage == 'initial':
                    question.initial_evaluation = evaluation_result
                elif stage in ['reviewed', 'final']:
                    question.reviewed_evaluation = evaluation_result
                else:
                    logging.warning(f"Unknown evaluation stage: {stage}")

            else:
                logging.warning(f"Failed to parse a valid evaluation response from LLM for question {question.id}")

        except Exception as e:
            logging.error(f"Error during LLM evaluation for question {question.id}: {e}", exc_info=True)

        return question
