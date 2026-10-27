"""Thin adapter between ptestgen's agents and the shared ``pexams.llm.LLMClient``.

The generator, reviewer and evaluator ask for structured output (JSON Schemas from
``ptestgen.schemas``); routing, effort, API keys, retries of transient HTTP errors, redaction of
secrets and provenance logging (``llm_calls.jsonl``) are handled by ``LLMClient``, the same
client pexams and pevaluate use. Bare ``claude-…`` ids go to the Anthropic API; any other id
(``google/gemini-…``, ``anthropic/claude-…``) goes to OpenRouter.
"""
import logging
import mimetypes
import random
import threading
import time
from pathlib import Path
from typing import List, Optional

from pexams.llm import LLMClient, resolve_provider

from .. import config

SUPPORTED_PROVIDERS = ("openrouter", "anthropic")


def get_image_mime_type(image_path: str) -> str:
    return mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"


def _read_images(image_paths) -> list:
    images = []
    for path in image_paths or []:
        try:
            images.append((Path(path).read_bytes(), get_image_mime_type(path)))
        except OSError as e:
            logging.error(f"Could not read image {path}: {e}")
    return images


def questions_schema(num_distractors: int) -> dict:
    from ..schemas import LLMQuestionList

    schema = LLMQuestionList.model_json_schema()
    distractors = schema.get("$defs", {}).get("LLMQuestionItem", {}).get("properties", {}).get("distractors")
    if distractors is not None and num_distractors > 0:
        # Open-answer items have no distractors, so only the maximum is enforced.
        distractors["maxItems"] = num_distractors
    return schema


class LLMProvider:
    """One agent's model. Methods return the model's JSON text, or raise after the retries."""

    def __init__(
        self,
        model_name: str,
        provider_name: str = "auto",
        api_key_env: Optional[str] = None,
        effort: Optional[str] = None,
        log_path: Optional[str] = None,
        role: str = "",
    ):
        self.model_name = model_name
        self.provider_name = resolve_provider(model_name, provider_name if provider_name in SUPPORTED_PROVIDERS else "auto")
        self.api_key_env = api_key_env or config.PROVIDER_API_KEY_MAP.get(self.provider_name)
        self.effort = effort
        self.role = role
        self._log_path = log_path
        self._client: Optional[LLMClient] = None
        self._init_error: Optional[Exception] = None

    # The client is created on first use: commands that never call the model (export without
    # --evaluate-final) do not need its API key.
    @property
    def client(self) -> LLMClient:
        if self._client is None:
            if self._init_error is not None:
                raise self._init_error
            try:
                self._client = LLMClient(
                    self.model_name,
                    provider=self.provider_name,
                    effort=self.effort,
                    api_key_env=self.api_key_env,
                    log_path=self._log_path,
                    tool="ptestgen",
                    max_retries=config.LLM_MAX_RETRIES,
                    timeout=config.LLM_TIMEOUT,
                )
            except Exception as e:
                self._init_error = RuntimeError(f"{self.role or 'LLM'}: {e}")
                raise self._init_error from None
        return self._client

    @property
    def log_path(self) -> Optional[str]:
        return self._log_path

    @log_path.setter
    def log_path(self, value: Optional[str]) -> None:
        self._log_path = value
        if self._client is not None:
            self._client.log_path = value

    def describe(self) -> dict:
        return {"role": self.role, "provider": self.provider_name, "model": self.model_name, "effort": self.effort, "api_key_env": self.api_key_env}

    def supports_vision(self) -> bool:
        return True

    def _call_with_retry(self, func):
        """Retries failed calls with exponential backoff. OpenRouter calls also get a hard
        wall-clock deadline: its keep-alive padding can keep a dead request open forever (the
        client timeout is per read). Anthropic calls stream, so the SDK timeout suffices."""
        deadline = config.LLM_HARD_TIMEOUT if self.provider_name == "openrouter" else None

        def call_with_deadline():
            if not deadline:
                return func()
            outcome = {}

            def target():
                try:
                    outcome["value"] = func()
                except Exception as error:  # re-raised in the caller thread
                    outcome["error"] = error

            worker = threading.Thread(target=target, daemon=True)  # a hung request must not block exit
            worker.start()
            worker.join(deadline)
            if worker.is_alive():
                raise TimeoutError(f"LLM call exceeded the hard timeout of {deadline}s")
            if "error" in outcome:
                raise outcome["error"]
            return outcome.get("value")

        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                return call_with_deadline()
            except Exception as e:
                if attempt == config.LLM_MAX_RETRIES or self._init_error is not None:
                    raise
                delay = (config.RETRY_DELAY_BASE ** attempt) + random.uniform(0, 0.5)
                logging.warning(f"LLM call failed ({type(e).__name__}: {e}); retrying in {delay:.1f}s...")
                time.sleep(delay)
        return None

    def _complete(self, prompt: str, schema: dict, purpose: str, system: Optional[str] = None, images=()) -> Optional[str]:
        result = self._call_with_retry(
            lambda: self.client.complete(prompt, images=images, system=system, json_schema=schema, purpose=purpose)
        )
        return result[0] if result else None

    # --- Agent-facing calls -------------------------------------------------------------
    def generate_questions_from_text(self, system_prompt: str, user_prompt: str, num_distractors: int, image_paths: Optional[List[str]] = None) -> Optional[str]:
        return self._complete(user_prompt, questions_schema(num_distractors), "generate_questions", system=system_prompt, images=_read_images(image_paths))

    def generate_question_from_image(self, system_prompt: str, user_prompt: str, image_path: str, num_distractors: int) -> Optional[str]:
        images = _read_images([image_path])
        if not images:
            return None
        return self._complete(user_prompt, questions_schema(num_distractors), "generate_questions_from_image", system=system_prompt, images=images)

    def review_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        from ..schemas import LLMReview

        prompt = system_prompt.replace("{question_json}", question_json)
        return self._complete(prompt, LLMReview.model_json_schema(), "review_question", system="You are an AI assistant reviewing a multiple-choice question.")

    def evaluate_question(self, system_prompt: str, question_json: str) -> Optional[str]:
        from ..schemas import LLMEvaluation

        prompt = system_prompt.replace("{question_json}", question_json)
        return self._complete(prompt, LLMEvaluation.model_json_schema(), "evaluate_question", system="You are an AI assistant evaluating a multiple-choice question.")


def get_provider(
    provider_name: str = config.LLM_PROVIDER,
    model_name: str = config.GENERATOR_MODEL,
    api_key_env: Optional[str] = None,
    effort: Optional[str] = None,
    log_path: Optional[str] = None,
    role: str = "",
) -> LLMProvider:
    """Adapter for ``model_name``. The model id decides the route (``claude-…`` → Anthropic,
    anything else → OpenRouter), as in pexams and pevaluate. ``api_key_env`` applies when that
    route is ``provider_name``; otherwise the route's default variable
    (``config.PROVIDER_API_KEY_MAP``) is read."""
    provider_name = (provider_name or "auto").lower()
    if provider_name not in SUPPORTED_PROVIDERS + ("auto",):
        raise ValueError(f"Unsupported LLM provider: {provider_name} (use {', '.join(SUPPORTED_PROVIDERS)} or stub).")
    route = resolve_provider(model_name, "auto")
    if provider_name != "auto" and route != provider_name:
        logging.info(f"Model '{model_name}' is routed to {route} although provider '{provider_name}' was selected.")
    key_env = api_key_env if api_key_env and provider_name in (route, "auto") else None
    return LLMProvider(model_name, provider_name=route, api_key_env=key_env, effort=effort, log_path=log_path, role=role)
