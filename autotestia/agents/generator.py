import os
import base64
import json
import time
import random # Needed for shuffling options in stub
from typing import List, Optional, Any, Dict
from ..schemas import Question
from .. import config
import logging # Use logging

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


class QuestionGenerator:
    """Agent responsible for generating questions using various LLM providers."""

    def __init__(self,
                 llm_provider: str = config.LLM_PROVIDER,
                 model_name: str = config.GENERATOR_MODEL,
                 api_keys: Dict[str, str] = None):

        self.llm_provider = llm_provider
        self.model_name = model_name
        self.client = None
        self.api_keys = api_keys or {
            "openai": config.OPENAI_API_KEY,
            "google": config.GOOGLE_API_KEY,
            "anthropic": config.ANTHROPIC_API_KEY,
            "replicate": config.REPLICATE_API_TOKEN,
        }
        self.api_error_types = () # Tuple to store relevant API error types
        self.timeout_error_types = () # Tuple for timeout errors

        logging.info(f"Initializing QuestionGenerator with provider: {self.llm_provider}, model: {self.model_name}")

        try:
            if self.llm_provider == "openai":
                if not self.api_keys.get("openai"): raise ValueError("OpenAI API key not found in config/env.")
                # Conditional import
                from openai import OpenAI, APIError, APITimeoutError
                self.client = OpenAI(api_key=self.api_keys["openai"], timeout=config.LLM_TIMEOUT)
                self.api_error_types = (APIError,)
                self.timeout_error_types = (APITimeoutError,)
            elif self.llm_provider == "google":
                if not self.api_keys.get("google"): raise ValueError("Google API key not found in config/env.")
                 # Conditional import
                import google.generativeai as genai
                from google.api_core.exceptions import GoogleAPIError
                genai.configure(api_key=self.api_keys["google"])
                self.client = genai # Store the module itself
                self.api_error_types = (GoogleAPIError,)
                self.timeout_error_types = () # No specific timeout error class identified easily
            elif self.llm_provider == "anthropic":
                if not self.api_keys.get("anthropic"): raise ValueError("Anthropic API key not found in config/env.")
                 # Conditional import
                from anthropic import Anthropic, APIError as AnthropicAPIError, APITimeoutError as AnthropicAPITimeoutError
                self.client = Anthropic(api_key=self.api_keys["anthropic"], timeout=config.LLM_TIMEOUT)
                self.api_error_types = (AnthropicAPIError,)
                self.timeout_error_types = (AnthropicAPITimeoutError,)
            elif self.llm_provider == "replicate":
                if not self.api_keys.get("replicate"): raise ValueError("Replicate API token not found in config/env.")
                # Conditional import
                import replicate
                from replicate.exceptions import ReplicateError
                self.replicate_token = self.api_keys["replicate"]
                self.client = replicate # Use the replicate module itself
                self.api_error_types = (ReplicateError,) # Use generic if specific unknown
                self.timeout_error_types = ()
            elif self.llm_provider == "stub":
                logging.info("Using STUB generator. No real API calls will be made.")
            else:
                raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")
        except ImportError as e:
             logging.error(f"Failed to import required library for provider '{self.llm_provider}': {e}. Please install it.")
             self.client = None
        except Exception as e:
            logging.error(f"Error initializing LLM client for {self.llm_provider}: {e}", exc_info=True)
            self.client = None # Ensure client is None if init fails

    def _call_llm_with_retry(self, api_call_func, *args, **kwargs):
        """Wrapper to handle retries for API calls."""
        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                return api_call_func(*args, **kwargs)
            # Combine known timeout errors if they exist
            except self.timeout_error_types as e:
                if attempt == config.LLM_MAX_RETRIES:
                    logging.error(f"API Timeout Error after {attempt + 1} attempts: {e}")
                    raise
                logging.warning(f"API Timeout Error, retrying ({attempt + 1}/{config.LLM_MAX_RETRIES})...")
                time.sleep(2 ** attempt) # Exponential backoff
            # Combine known API errors and general exceptions
            except (*self.api_error_types, Exception) as e:
                 # Check if it's actually one of the known API errors
                 is_known_api_error = any(isinstance(e, err_type) for err_type in self.api_error_types)

                 if attempt == config.LLM_MAX_RETRIES:
                     error_type = "API Error" if is_known_api_error else "Unexpected Error"
                     logging.error(f"{error_type} after {attempt + 1} attempts: {e}", exc_info=(not is_known_api_error)) # Log traceback for unexpected
                     raise
                 log_func = logging.warning if is_known_api_error else logging.info # Log unexpected errors less loudly during retries
                 log_func(f"API Error: {e}. Retrying ({attempt + 1}/{config.LLM_MAX_RETRIES})...")
                 time.sleep(2 ** attempt) # Exponential backoff
        return None # Should not be reached if exceptions are raised correctly

    def _parse_llm_response(self, response_content: str, expected_format='questions_list') -> Any:
        """Attempts to parse the LLM's JSON response, handling different expected structures."""
        try:
            # Sometimes models wrap JSON in backticks or add prefixes
            response_content = response_content.strip()
            if response_content.startswith("```json"):
                response_content = response_content[len("```json"):].strip()
            elif response_content.startswith("```"):
                 response_content = response_content[len("```"):].strip()
            if response_content.endswith("```"):
                 response_content = response_content[:-len("```")].strip()

            # Check again if the prefix was just 'json' without backticks
            if response_content.startswith("json"):
                 response_content = response_content[len("json"):].strip()

            data = json.loads(response_content)

            # Validate structure based on expected format
            if expected_format == 'questions_list':
                if not isinstance(data, dict) or "questions" not in data:
                    raise ValueError("Expected JSON object with a 'questions' key containing a list.")
                questions_list = data["questions"]
                if not isinstance(questions_list, list):
                    raise ValueError("Expected 'questions' key to contain a list.")
                for q in questions_list:
                    if not isinstance(q, dict) or not all(k in q for k in ["text", "correct_answer", "distractors"]):
                         raise ValueError(f"List item is not a valid question object (missing keys): {q}")
                return questions_list # Return the list of questions directly
            elif expected_format == 'single_question':
                 if not isinstance(data, dict) or not all(k in data for k in ["text", "correct_answer", "distractors"]):
                     raise ValueError("Expected JSON object with keys 'text', 'correct_answer', 'distractors'.")
                 return data # Return the single question dict
            else:
                raise ValueError(f"Unknown expected_format: {expected_format}")

        except json.JSONDecodeError as e:
            logging.error(f"Could not decode JSON response: {e}")
            logging.error(f"Raw response content was:\n---\n{response_content}\n---")
            return None
        except ValueError as e:
             logging.error(f"Invalid response structure for format '{expected_format}': {e}")
             logging.error(f"Raw response content was:\n---\n{response_content}\n---")
             return None
        except Exception as e:
             logging.error(f"Unexpected error parsing response: {e}", exc_info=True)
             logging.error(f"Raw response content was:\n---\n{response_content}\n---")
             return None


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

        if self.llm_provider == "stub" or not self.client:
            source_desc = "Provided Text" if text_content else "Provided Instructions"
            return self._generate_stub_questions(num_questions, num_options, source_desc)

        logging.info(f"Generating {num_questions} questions from {'text' if text_content else 'instructions'} using {self.llm_provider} ({self.model_name})...")
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
            response_content = None
            # --- Provider-specific calls ---
            if self.llm_provider == "openai":
                completion = self._call_llm_with_retry(
                    self.client.chat.completions.create,
                    model=self.model_name,
                    response_format={ "type": "json_object" },
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                response_content = completion.choices[0].message.content
            elif self.llm_provider == "google":
                model = self.client.GenerativeModel(self.model_name)
                generation_config = self.client.types.GenerationConfig(response_mime_type="application/json")
                response = self._call_llm_with_retry(
                    model.generate_content,
                    [system_prompt, user_prompt], # Pass both prompts
                    generation_config=generation_config
                )
                response_content = response.text
            elif self.llm_provider == "anthropic":
                 message = self._call_llm_with_retry(
                     self.client.messages.create,
                     model=self.model_name,
                     max_tokens=4000,
                     system=system_prompt, # Use system parameter
                     messages=[{"role": "user", "content": user_prompt}]
                 )
                 response_content = next((block.text for block in message.content if block.type == 'text'), None)
            elif self.llm_provider == "replicate":
                full_prompt = f"{system_prompt}\n\n{user_prompt}" # Combine for Replicate
                output = self._call_llm_with_retry(
                    self.client.run,
                    self.model_name,
                    input={"prompt": full_prompt}
                )
                response_content = "".join(output)

            # --- Process response ---
            if not response_content:
                 logging.error("No content received from LLM.")
                 return []

            # Expect a list of question dicts from the parser now
            parsed_data = self._parse_llm_response(response_content, expected_format='questions_list')

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
            logging.error(f"Error during LLM call or processing for {self.llm_provider}: {e}", exc_info=True)

        logging.info(f"Generated {len(questions)} questions.")
        return questions


    def generate_question_from_image(self,
                                     image_path: str,
                                     context_text: Optional[str] = None,
                                     num_options: int = config.DEFAULT_NUM_OPTIONS,
                                     custom_instructions: Optional[str] = None) -> Optional[Question]:
        """Generates a single question from an image using the configured LLM."""
        if self.llm_provider == "stub" or not self.client:
            return self._generate_stub_questions(1, num_options, f"Image: {image_path}")[0]

        logging.info(f"Generating question from image {image_path} using {self.llm_provider} ({self.model_name})...")

        # Vision capabilities check (simple)
        vision_models = {
            "openai": ["gpt-4o", "gpt-4-vision-preview", "gpt-4-turbo"], # Add other vision models
            "google": ["gemini-1.5-pro", "gemini-pro-vision", "gemini-1.5-pro-latest", "gemini-2.5-pro"],
            "anthropic": ["claude-3", "claude-3-7-sonnet"], # Check exact names
            "replicate": [] # Replicate vision models often have specific names like 'llava', check model details
        }
        # A basic check, might need refinement based on exact model strings
        is_vision_model = any(vm in self.model_name for vm in vision_models.get(self.llm_provider, []))
        # Replicate needs explicit check as model names vary wildly
        if self.llm_provider == 'replicate':
            # Placeholder - check Replicate docs for LLaVA or other vision models
            print("Warning: Replicate vision model check not implemented. Assuming model supports vision if provider is replicate.")
            is_vision_model = True # Assume yes for now

        if not is_vision_model:
             logging.warning(f"Model '{self.model_name}' for provider '{self.llm_provider}' might not support vision. Skipping image question.")
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
            response_content = None
            if self.llm_provider == "openai":
                completion = self._call_llm_with_retry(
                    self.client.chat.completions.create,
                    model=self.model_name,
                     response_format={ "type": "json_object" },
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
                        ]}
                    ],
                    max_tokens=1000
                )
                response_content = completion.choices[0].message.content
            elif self.llm_provider == "google":
                 model = self.client.GenerativeModel(self.model_name)
                 generation_config = self.client.types.GenerationConfig(response_mime_type="application/json")
                 image_part = {"mime_type": mime_type, "data": base64.b64decode(base64_image)}
                 response = self._call_llm_with_retry(
                     model.generate_content,
                     [system_prompt, user_prompt_text, image_part], # Pass system prompt
                     generation_config=generation_config
                 )
                 response_content = response.text
            elif self.llm_provider == "anthropic":
                 message = self._call_llm_with_retry(
                     self.client.messages.create,
                     model=self.model_name,
                     max_tokens=4000,
                     system=system_prompt, # Pass system prompt
                     messages=[{
                         "role": "user",
                         "content": [
                             {
                                 "type": "image",
                                 "source": { "type": "base64", "media_type": mime_type, "data": base64_image }
                             },
                             {"type": "text", "text": user_prompt_text}
                         ]
                     }]
                 )
                 response_content = next((block.text for block in message.content if block.type == 'text'), None)
            elif self.llm_provider == "replicate":
                 full_prompt = f"{system_prompt}\n\n{user_prompt_text}" # Combine system/user for prompt field
                 output = self._call_llm_with_retry(
                     self.client.run,
                     self.model_name,
                     input={
                         "image": f"data:{mime_type};base64,{base64_image}",
                         "prompt": full_prompt
                     }
                 )
                 response_content = "".join(output)


            if not response_content:
                logging.error("No content received from LLM for image question.")
                return None

            # Expect a single question dict from the parser
            parsed_data = self._parse_llm_response(response_content, expected_format='single_question')

            if parsed_data:
                 # Validation now done in parser
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
            logging.error(f"Error during image question LLM call or processing for {self.llm_provider}: {e}", exc_info=True)
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