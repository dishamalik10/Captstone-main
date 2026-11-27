"""Inference adapter for AURA's scratch-trained 5.24M parameter model.

The model explains server-ranked outfits; it cannot choose or change wardrobe IDs.
It is loaded only from local files and never downloads weights.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

from settings import settings
from ml.explain_prompt import CATEGORY, build_request, make_prompt
from services.fashion_contract import validate_explanation_json

LOGGER = logging.getLogger(__name__)
_lock = threading.RLock()
_model: Any | None = None
_tokenizer: Any | None = None
_torch: Any | None = None
_device: str | None = None
_last_error: str | None = None


def model_info() -> dict[str, Any]:
    """Return readiness without loading weights or revealing the local path."""
    safe_error = _last_error
    if safe_error:
        safe_error = safe_error.replace(str(settings.fashion_lm_path), "<AURA_FASHION_LM_PATH>")
    return {
        "engine": "AURA scratch fashion GPT",
        "weights_present": settings.fashion_lm_path.is_dir(),
        "loaded": _model is not None,
        "ready": _model is not None,
        "architecture": "GPT-style decoder, 4 layers, 256 hidden, 4 heads, vocab 8000",
        "role": "explanation only; deterministic ranker selects all outfit items",
        "last_error": safe_error,
    }


def load_model() -> None:
    global _model, _tokenizer, _torch, _device, _last_error
    with _lock:
        if _model is not None:
            return
        if not settings.fashion_lm_path.is_dir():
            _last_error = "AURA fashion LM files not found; check AURA_FASHION_LM_PATH"
            raise FileNotFoundError(_last_error)
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                str(settings.fashion_lm_path), local_files_only=True, use_fast=True
            )
            model = AutoModelForCausalLM.from_pretrained(
                str(settings.fashion_lm_path), local_files_only=True
            )
            parameter_count = sum(parameter.numel() for parameter in model.parameters())
            if len(tokenizer) != model.config.vocab_size or len(tokenizer) != 8000:
                raise ValueError("AURA model/tokenizer vocabulary mismatch")
            if parameter_count != 5_240_320:
                raise ValueError(f"Unexpected AURA scratch model parameter count: {parameter_count}")
            if (model.config.n_layer, model.config.n_embd, model.config.n_head) != (4, 256, 4):
                raise ValueError("Unexpected AURA scratch model architecture")
            if tokenizer.eos_token_id is None:
                raise ValueError("AURA tokenizer is missing an EOS token")
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token
            model.config.pad_token_id = tokenizer.pad_token_id
            device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            model.to(device=device, dtype=dtype).eval()
            _torch, _tokenizer, _model, _device = torch, tokenizer, model, device
            _last_error = None
            LOGGER.info("Loaded AURA scratch fashion LM on %s from local files", device)
        except Exception as exc:
            LOGGER.exception("Could not load AURA scratch fashion LM")
            _last_error = "Could not load AURA scratch fashion LM; see the server log for details."
            raise RuntimeError(_last_error) from exc


def explain_outfit(
    selected_items: list[dict[str, Any]],
    wardrobe: list[dict[str, Any]],
    *,
    occasion: str,
    temperature: float,
    condition: str,
    preferences: dict[str, Any] | None = None,
) -> str:
    """Generate and validate JSON for an already selected outfit.

    The prompt carries only the selected garments and request context, in the
    exact format the model was trained on (``ml/explain_prompt.py``). The full
    wardrobe is used only to validate the answer.
    """
    if not selected_items:
        raise ValueError("Selected outfit is empty")
    selected_ids = [str(item["item_id"]) for item in selected_items]
    validate_explanation_json(
        json.dumps({"item_ids": selected_ids, "explanation": "validation"}),
        selected_items, wardrobe,
    )
    load_model()
    prompt = make_prompt(CATEGORY, build_request(
        selected_items,
        occasion=occasion,
        weather={"temperature_c": temperature, "condition": condition},
        preferences=preferences,
    ))
    with _lock:
        assert _model is not None and _tokenizer is not None and _torch is not None and _device is not None
        input_limit = min(512, max(64, int(getattr(_model.config, "n_positions", 1024)) - 160))
        inputs = _tokenizer(prompt, return_tensors="pt")
        if inputs["input_ids"].shape[1] > input_limit:
            # Truncating would cut the "### Assistant:" marker; the caller keeps the rule explanation.
            raise ValueError("Outfit prompt exceeds the scratch model context")
        inputs = {key: value.to(_device) for key, value in inputs.items()}
        with _torch.inference_mode():
            output = _model.generate(
                **inputs, max_new_tokens=140, do_sample=False,
                pad_token_id=_tokenizer.pad_token_id,
                eos_token_id=_tokenizer.eos_token_id,
            )
        raw = _tokenizer.decode(output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return validate_explanation_json(raw, selected_items, wardrobe)


def unload_model() -> None:
    global _model, _tokenizer, _torch, _device
    with _lock:
        _model = _tokenizer = _torch = _device = None
