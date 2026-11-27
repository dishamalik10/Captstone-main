"""In-process local GGUF inference. No network access or implicit downloads."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from settings import settings

LOGGER = logging.getLogger(__name__)


class LocalModelError(RuntimeError):
    pass


class LocalLLM:
    def __init__(self, model_path: str | Path | None = None) -> None:
        # None means "use settings.llm_model_path" (the chat model).
        self._default_path = Path(model_path).expanduser() if model_path else None
        self._model: Any | None = None
        self._last_error: str | None = None
        self._load_lock = threading.Lock()
        self._request_slots = threading.BoundedSemaphore(max(1, settings.llm_concurrency))

    def load_model(self, model_path: str | Path | None = None) -> None:
        path = Path(model_path or self._default_path or settings.llm_model_path).expanduser()
        with self._load_lock:
            if self._model is not None:
                return
            if not path.is_file():
                LOGGER.warning("Local LLM weights are missing: %s", path)
                self._last_error = "Local LLM weights are missing. Download the authorized GGUF with `python -m training.download_model`."
                raise LocalModelError(self._last_error)
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                self._last_error = "Local inference runtime is not installed. Install requirements-local.txt."
                raise LocalModelError(self._last_error) from exc
            try:
                self._model = Llama(
                    model_path=str(path), n_ctx=settings.llm_context_length,
                    n_threads=settings.llm_threads, n_gpu_layers=settings.llm_gpu_layers,
                    verbose=False,
                )
                self._last_error = None
                LOGGER.info("Loaded local LLM from %s", path)
            except Exception as exc:
                LOGGER.exception("Could not load local LLM from %s", path)
                self._last_error = "Could not load the local LLM; see the server log for details."
                raise LocalModelError(self._last_error) from exc

    def generate_response(
        self, prompt: str, *, system_prompt: str = "You are AURA, a concise personal fashion stylist.",
        max_tokens: int | None = None, temperature: float | None = None,
        response_format: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must not be empty.")
        if len(prompt) > settings.llm_max_input_tokens * 5:
            raise ValueError("Prompt exceeds the configured maximum input size.")
        output_limit = min(max_tokens or settings.llm_max_output_tokens, settings.llm_max_output_tokens)
        if output_limit < 1 or output_limit >= settings.llm_context_length:
            raise LocalModelError("Configured output tokens must be positive and smaller than the model context.")
        self.load_model()
        if not self._request_slots.acquire(timeout=settings.llm_queue_timeout_seconds):
            raise LocalModelError("Local model is busy; retry shortly.")
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                *(history or []),
                {"role": "user", "content": prompt},
            ]
            input_limit = min(
                settings.llm_max_input_tokens,
                settings.llm_context_length - output_limit,
            )
            try:
                tokenized = self._model.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True
                )
                if isinstance(tokenized, str):
                    tokenized = self._model.tokenize(tokenized.encode("utf-8"), add_bos=False)
                input_token_count = len(tokenized)
            except (AttributeError, TypeError, ValueError):
                # Older llama-cpp bindings may not expose chat-template tokenization.
                rendered = system_prompt + "\n" + prompt
                input_token_count = len(self._model.tokenize(rendered.encode("utf-8")))
            if input_token_count > input_limit:
                raise ValueError(
                    f"Prompt is {input_token_count} tokens; maximum is {input_limit}."
                )
            generation_args = dict(
                messages=messages,
                max_tokens=output_limit,
                temperature=settings.llm_temperature if temperature is None else temperature,
                top_p=settings.llm_top_p,
            )
            if response_format is not None:
                generation_args["response_format"] = response_format
            result = self._model.create_chat_completion(**generation_args)
            text = result["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise LocalModelError("Local model returned an empty response.")
            return text.strip()
        except LocalModelError:
            raise
        except ValueError:
            # Preserve input/config validation errors so the API can return 4xx.
            raise
        except Exception as exc:
            LOGGER.exception("Local model generation failed")
            raise LocalModelError(f"Local model generation failed: {exc}") from exc
        finally:
            self._request_slots.release()

    def get_model_info(self) -> dict[str, Any]:
        model_path = self._default_path or settings.llm_model_path
        present = model_path.is_file()
        error = self._last_error
        if not present and not error:
            error = (
                "Local LLM weights are missing. "
                "Run `python -m training.download_model` after installing the local runtime."
            )
        return {"engine": "llama.cpp", "path": str(model_path),
                "present": present, "loaded": self._model is not None,
                "ready": self._model is not None,
                "context_length": settings.llm_context_length,
                "max_input_tokens": settings.llm_max_input_tokens,
                "concurrency": settings.llm_concurrency,
                "last_error": error}

    def unload_model(self) -> None:
        with self._load_lock:
            self._model = None


local_llm = LocalLLM()


def load_model() -> None:
    local_llm.load_model()


def generate_response(prompt: str, **kwargs: Any) -> str:
    return local_llm.generate_response(prompt, **kwargs)


def get_model_info() -> dict[str, Any]:
    return local_llm.get_model_info()


def unload_model() -> None:
    local_llm.unload_model()
