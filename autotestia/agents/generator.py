import os
import base64
import json
import time
import random # Needed for shuffling options in stub
from typing import List, Optional, Any, Dict
from ..schemas import Question
from .. import config
import logging # Use logging
from .base import BaseAgent # Changed inheritance
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


class QuestionGenerator(BaseAgent): # Changed inheritance
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
                                     text_content: Optional[str], # Make optional
                                     num_questions: int = config.DEFAULT_NUM_QUESTIONS,
                                     num_options: int = config.DEFAULT_NUM_OPTIONS,
                                     language: str = config.DEFAULT_LANGUAGE,
                                     custom_instructions: Optional[str] = None) -> List[Question]:
        """
        Generates multiple-choice questions based on text or instructions using the configured LLM.
        """
        if not text_content and not custom_instructions:
            logging.warning("generate_questions_from_text called without text_content or custom_instructions. Cannot generate.")
            return []

        if self.llm_provider_name == "stub":
            source_desc = "Provided Text" if text_content else "Provided Instructions"
            return self._generate_stub_questions(num_questions, num_options, source_desc)
        
        if not self.provider:
            raise RuntimeError(f"LLM provider for '{self.llm_provider_name}' is not available. Cannot generate questions.")

        logging.info(f"Generating {num_questions} questions from {'text' if text_content else 'instructions'} using {self.llm_provider_name} ({self.provider.model_name})...")
        questions = []
        num_distractors = num_options - 1

        # --- Prepare Prompt ---
        # System Prompt
        system_prompt = config.GENERATION_SYSTEM_PROMPT.format(
            custom_generator_instructions=custom_instructions if custom_instructions else ""
        )

        # User Prompt
        user_prompt_parts = []
        if text_content:
            user_prompt_parts.append(f"Context:\n{text_content}\n")
        user_prompt_parts.append(f"Generate exactly {num_questions} multiple-choice questions {'based on the context above' if text_content else 'based on the instructions'}.")
        user_prompt_parts.append(f"Each question should have one correct answer and {num_distractors} distractors.")
        user_prompt_parts.append(f"Generate the questions and the answers in the following language: {language}.")

        user_prompt = "\n".join(user_prompt_parts)
        # --- End Prompt Prep ---

        try:
            response_content = self.provider.generate_questions_from_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                num_distractors=num_distractors
            )

            if not response_content:
                 logging.error("No content received from LLM.")
                 return []

            # Expect a list of question dicts from the parser now
            parsed_data = self._parse_llm_json_response(response_content, expected_structure='questions_list')

            if parsed_data:
                 question_id_counter = 1
                 source_material_desc = "Provided Text" if text_content else "Provided Instructions"
                 for item in parsed_data:
                     # Validation is now done inside _parse_llm_response
                     # Basic length check remains useful
                     if isinstance(item.get("distractors"), list) and len(item["distractors"]) == num_distractors:
                         q = Question(
                             id=question_id_counter,
                             text=item["text"],
                             correct_answer=item["correct_answer"],
                             distractors=item["distractors"],
                             explanation=item.get("explanation"),
                             source_material=source_material_desc
                         )
                         questions.append(q)
                         question_id_counter += 1
                     else:
                         logging.warning(f"Skipping malformed question item (invalid/missing distractors): {item}")

        except Exception as e:
            logging.error(f"Error during LLM call or processing for {self.llm_provider_name}: {e}", exc_info=True)

        logging.info(f"Generated {len(questions)} questions.")
        return questions


    def generate_question_from_image(self,
                                     image_path: str,
                                     context_text: Optional[str] = None,
                                     num_options: int = config.DEFAULT_NUM_OPTIONS,
                                     custom_instructions: Optional[str] = None) -> Optional[Question]:
        """Generates a single question from an image using the configured LLM."""
        if self.llm_provider_name == "stub": # Explicit stub check for clarity
            return self._generate_stub_questions(1, num_options, f"Image: {image_path}")[0]

        if not self.provider: # Check if client was initialized in base
            raise RuntimeError(f"LLM provider for '{self.llm_provider_name}' is not available. Cannot generate image question.")

        logging.info(f"Generating question from image {image_path} using {self.llm_provider_name} ({self.provider.model_name})...")

        # Vision capabilities check (simple)
        # Updated to use self.model_name which is set in BaseLLMAgent
        vision_models = {
            "openai": ["gpt-4o", "gpt-4-turbo"], 
            "google": ["gemini-2.5-pro", "gemini-pro-vision", "gemini-2.5-pro-latest"], # Removed gemini-2.5-pro as it was not in config
            "anthropic": ["claude-3.7", "claude-3.7-opus", "claude-3.7-sonnet", "claude-3.7-haiku"], # More specific names
            "replicate": [] 
        }
        
        is_vision_model = False
        if self.llm_provider_name in vision_models:
            is_vision_model = any(vm_keyword in self.provider.model_name for vm_keyword in vision_models[self.llm_provider_name])

        if self.llm_provider_name == 'replicate':
             # For Replicate, model names are URLs/paths, e.g., "yorickvp/llava-13b:2facb4a474a0462c15041b78b1ad70952ea46b5ec6ad29583c0b29dbd4249591"
             # A simple check might be if 'llava' or 'vision' is in the model string, but this is highly dependent on chosen model.
             # The config has "unsloth/meta-llama-3.3-70b-instruct" which is not a vision model.
             # This check needs to be robust or rely on user configuring a vision model for Replicate.
             # For now, if it's replicate, and not explicitly a non-vision model, we might assume it could be, or log a warning.
             # Let's assume it is NOT a vision model by default unless specified.
             # logging.warning("Replicate vision model check is basic. Ensure the configured model supports vision.")
             # is_vision_model = True # Cautious assumption, or make it False and require specific model names
             if 'llava' in self.provider.model_name or 'vision' in self.provider.model_name: # Example check
                 is_vision_model = True
             else:
                 is_vision_model = False # Default to false if no clear indicator for Replicate

        if not is_vision_model:
             logging.warning(f"Model '{self.provider.model_name}' for provider '{self.llm_provider_name}' may not support vision. Generation from image might fail or produce poor results. Skipping image question.")
             return None


        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            return None
        mime_type = get_image_mime_type(image_path)
        num_distractors = num_options - 1

        # --- Prepare Prompt ---
        # System Prompt
        system_prompt = config.IMAGE_GENERATION_SYSTEM_PROMPT.format(
            custom_generator_instructions=custom_instructions if custom_instructions else ""
        )

        # User Prompt (base)
        user_prompt_text = f"Generate ONE multiple-choice question based on the provided image. It should have one correct answer and {num_distractors} distractors. Follow the JSON output format specified in the system prompt."
        if context_text:
            user_prompt_text += f"\n\nOptional Context:\n{context_text}"
        # --- End Prompt Prep ---

        try:
            response_content = self.provider.generate_question_from_image(
                system_prompt=system_prompt,
                user_prompt=user_prompt_text,
                image_path=image_path,
                num_distractors=num_distractors
            )

            if not response_content:
                logging.error("No content received from LLM for image question.")
                return None

            # Expect a single question dict from the parser
            parsed_data = self._parse_llm_json_response(response_content, expected_structure='single_question_dict')

            if parsed_data:
                 # Validation now done in parser (base class)
                 if isinstance(parsed_data.get("distractors"), list) and len(parsed_data["distractors"]) == num_distractors:
                    q = Question(
                        id=999, # Placeholder ID
                        text=parsed_data["text"],
                        correct_answer=parsed_data["correct_answer"],
                        distractors=parsed_data["distractors"],
                        explanation=parsed_data.get("explanation"),
                        source_material=f"Image: {os.path.basename(image_path)}" + (f", Context provided" if context_text else ""),
                        image_reference=image_path
                    )
                    logging.info(f"Generated question from image.")
                    return q
                 else:
                     logging.warning(f"Skipping malformed image question item (invalid distractors): {parsed_data}")
                     return None
            # else: No need for else, parser handles logging


        except Exception as e:
            logging.error(f"Error during image question LLM call or processing for {self.llm_provider_name}: {e}", exc_info=True)
            return None

    def _generate_stub_questions(self, num_questions: int, num_options: int, source: str) -> List[Question]:
        """Generates placeholder questions for stub mode matching the new schema."""
        logging.info(f"STUB: Generating {num_questions} questions for source: {source}")
        questions = []
        num_distractors = num_options - 1
        for i in range(num_questions):
            distractors = [f"Stub Distractor {j+1}" for j in range(num_distractors)]
            correct = "Stub Correct Answer"

            q = Question(
                id=i + 1,
                text=f"This is STUB question {i+1} based on {source}?",
                correct_answer=correct,
                distractors=distractors,
                source_material=source,
                explanation="This is a stub explanation."
            )
            questions.append(q)
        return questions 