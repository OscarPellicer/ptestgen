import os
import base64
import json
import time
import random # Needed for shuffling options in stub
from typing import List, Optional, Any, Dict
from ..schemas import QuestionRecord, QuestionContent, QuestionStage
from .. import config
from .. import artifacts
import logging # Use logging
from .base import BaseAgent
from ..llm_providers import get_provider, LLMProvider

# Helper function to encode images for APIs
def encode_image_to_base64(image_path):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logging.error(f"Error encoding image {image_path}: {e}", exc_info=True)
        return None

# Helper function to get mime type (basic)
def get_image_mime_type(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext == ".png":
        return "image/png"
    elif ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    elif ext == ".gif":
        return "image/gif"
    elif ext == ".bmp":
        return "image/bmp"
    # Add more types if needed
    return "application/octet-stream" # Default fallback


class QuestionGenerator(BaseAgent):
    """Agent responsible for generating questions using various LLM providers."""

    def __init__(self,
                 llm_provider: str = config.LLM_PROVIDER,
                 model_name: str = config.GENERATOR_MODEL,
                 api_keys: Dict[str, str] = None):

        super().__init__()
        self.llm_provider_name = llm_provider
        self.provider: Optional[LLMProvider] = None

        if self.llm_provider_name != "stub":
            try:
                self.provider = get_provider(
                    provider_name=llm_provider,
                    model_name=model_name,
                    api_keys=api_keys
                )
            except (ValueError, RuntimeError) as e:
                logging.error(f"Failed to initialize LLM provider for Generator: {e}. Generation will be disabled.")
        
        logging.info(f"Initializing QuestionGenerator with provider: {self.llm_provider_name}, model: {model_name}")

    def generate_questions_from_text(self,
                                     text_content: Optional[str],
                                     num_questions: int = config.DEFAULT_NUM_QUESTIONS,
                                     num_options: int = config.DEFAULT_NUM_OPTIONS,
                                     language: str = config.DEFAULT_LANGUAGE,
                                     custom_instructions: Optional[str] = None,
                                     source_material_path: Optional[str] = None) -> List[QuestionRecord]:
        """
        Generates multiple-choice questions based on text or instructions.
        Returns a list of QuestionRecord objects.
        """
        if not text_content and not custom_instructions:
            logging.warning("generate_questions_from_text called without text_content or custom_instructions. Cannot generate.")
            return []

        if self.llm_provider_name == "stub":
            return self._generate_stub_records(num_questions, num_options, source_material_path)
        
        if not self.provider:
            raise RuntimeError(f"LLM provider for '{self.llm_provider_name}' is not available. Cannot generate questions.")

        logging.info(f"Generating {num_questions} questions from {'text' if text_content else 'instructions'} using {self.llm_provider_name} ({self.provider.model_name})...")
        records = []
        num_distractors = num_options - 1

        system_prompt_template = config.GENERATION_SYSTEM_PROMPT.replace(
            '{custom_generator_instructions}',
            custom_instructions if custom_instructions else ""
        )
        user_prompt_parts = []
        if text_content:
            user_prompt_parts.append(f"Context:\n{text_content}\n")
        user_prompt_parts.append(f"Generate exactly {num_questions} multiple-choice questions {'based on the context above' if text_content else 'based on the instructions'}.")
        user_prompt_parts.append(f"Each question should have one correct answer and {num_distractors} distractors.")
        user_prompt_parts.append(f"Generate the questions and the answers in the following language: {language}.")
        user_prompt = "\n".join(user_prompt_parts)

        try:
            response_content = self.provider.generate_questions_from_text(
                system_prompt=system_prompt_template,
                user_prompt=user_prompt,
                num_distractors=num_distractors
            )

            if not response_content:
                 logging.error("No content received from LLM.")
                 return []

            parsed_data = self._parse_llm_json_response(response_content, expected_structure='questions_list')

            if parsed_data and isinstance(parsed_data, dict) and "questions" in parsed_data:
                question_list = parsed_data["questions"]
                if not isinstance(question_list, list):
                    logging.warning(f"LLM response 'questions' key is not a list. Content: {question_list}")
                    return []

                for item in question_list:
                     if not isinstance(item, dict):
                         logging.warning(f"Skipping malformed question item (not a dictionary): {item}")
                         continue

                     if isinstance(item.get("distractors"), list) and len(item["distractors"]) == num_distractors:
                         content = QuestionContent(
                             text=item["text"],
                             correct_answer=item["correct_answer"],
                             distractors=item["distractors"],
                             explanation=item.get("explanation"),
                         )
                         record = QuestionRecord(
                             question_id=artifacts.generate_question_id(source_material_path),
                             source_material=source_material_path or "custom_instructions",
                             generated=QuestionStage(content=content)
                         )
                         records.append(record)
                     else:
                         logging.warning(f"Skipping malformed question item (invalid/missing distractors): {item}")
            else:
                logging.warning(f"Failed to parse a valid question list from LLM response: {parsed_data}")

        except Exception as e:
            logging.error(f"Error during LLM call or processing for {self.llm_provider_name}: {e}", exc_info=True)

        logging.info(f"Generated {len(records)} question records.")
        return records

    def generate_questions_from_images(self,
                                       image_paths: List[str],
                                       context_text: Optional[str] = None,
                                       num_options: int = config.DEFAULT_NUM_OPTIONS,
                                       custom_instructions: Optional[str] = None) -> List[QuestionRecord]:
        """Generates one question for each image provided."""
        records = []
        if not image_paths:
            return records

        logging.info(f"Generating questions for {len(image_paths)} image(s)...")
        for image_path in image_paths:
            record = self._generate_one_question_from_image(
                image_path=image_path,
                context_text=context_text,
                num_options=num_options,
                custom_instructions=custom_instructions
            )
            if record:
                records.append(record)
        return records

    def _generate_one_question_from_image(self,
                                          image_path: str,
                                          context_text: Optional[str],
                                          num_options: int,
                                          custom_instructions: Optional[str]) -> Optional[QuestionRecord]:
        """Generates a single question from an image using the configured LLM."""
        if self.llm_provider_name == "stub":
            return self._generate_stub_records(1, num_options, f"Image: {image_path}")[0]

        if not self.provider:
            raise RuntimeError(f"LLM provider '{self.llm_provider_name}' is not available.")

        logging.info(f"Generating question from image {image_path} using {self.llm_provider_name} ({self.provider.model_name})...")

        # Basic vision capabilities check
        if not self.provider.supports_vision():
             logging.warning(f"Model '{self.provider.model_name}' for provider '{self.llm_provider_name}' may not support vision. Skipping image question.")
             return None

        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            return None
        
        num_distractors = num_options - 1

        system_prompt_template = config.IMAGE_GENERATION_SYSTEM_PROMPT.replace(
            '{custom_generator_instructions}',
            custom_instructions if custom_instructions else ""
        )
        user_prompt_text = f"Generate ONE multiple-choice question based on the provided image. It should have one correct answer and {num_distractors} distractors."
        if context_text:
            user_prompt_text += f"\n\nOptional Context:\n{context_text}"
        
        try:
            response_content = self.provider.generate_question_from_image(
                system_prompt=system_prompt_template,
                user_prompt=user_prompt_text,
                image_path=image_path, # Provider handles encoding now
                num_distractors=num_distractors
            )
            
            if not response_content:
                 logging.error(f"No content received from LLM for image {image_path}.")
                 return None

            parsed_data = self._parse_llm_json_response(response_content, expected_structure='single_question_dict')

            if parsed_data:
                # Pydantic will validate the structure here
                content = QuestionContent(**parsed_data)
                record = QuestionRecord(
                    question_id=artifacts.generate_question_id(image_path),
                    source_material=f"Image: {os.path.basename(image_path)}",
                    image_reference=image_path,
                    generated=QuestionStage(content=content)
                )
                return record

        except Exception as e:
            logging.error(f"Error during image question generation for {image_path}: {e}", exc_info=True)
        
        return None

    def _generate_stub_records(self, num_questions: int, num_options: int, source: Optional[str]) -> List[QuestionRecord]:
        """Generates placeholder QuestionRecord objects for stub mode."""
        logging.info(f"STUB: Generating {num_questions} records for source: {source}")
        records = []
        num_distractors = num_options - 1
        for i in range(num_questions):
            content = QuestionContent(
                text=f"This is STUB question {i+1} based on {source}?",
                correct_answer="Stub Correct Answer",
                distractors=[f"Stub Distractor {j+1}" for j in range(num_distractors)],
                explanation="This is a stub explanation."
            )
            record = QuestionRecord(
                question_id=artifacts.generate_question_id(source),
                source_material=source,
                generated=QuestionStage(content=content)
            )
            records.append(record)
        return records 