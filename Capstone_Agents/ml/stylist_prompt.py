"""Prompt and answer format for the AURA stylist language model.

The stylist LLM never sees or writes database item IDs. The server sends up to
five complete, owned outfit options (already checked for ownership and
completeness); the model answers with the option number it recommends and a
short reason. This keeps every suggestion inside the user's real wardrobe.

This file is shared verbatim by the backend and
``training/AURA_Stylist_LLM_LoRA_Colab.ipynb`` so training prompts and
inference prompts are byte-identical.
"""
from __future__ import annotations

import json
import re
from typing import Any, Sequence

MAX_OPTIONS = 5
REASON_MAX_CHARS = 420

SYSTEM_PROMPT = (
    "You are AURA, an expert personal fashion stylist. You are given the user's context "
    "(occasion, weather, self-described body shape, height, skin tone and saved preferences) "
    "and numbered outfit options built only from clothes the user owns. Choose the single "
    "option that best suits the occasion and weather, has the most coherent colours and "
    "proportions, and respects the user's preferences. visual_match is a learned estimate of "
    "how well the pieces look together. Use body shape only as optional proportion guidance, "
    "never as a criticism. Mention only garments and attributes listed in the chosen option. "
    'Reply with JSON only: {"choice": <option number>, "reason": "<one or two sentences>"}.'
)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "choice": {"type": "integer", "minimum": 1, "maximum": MAX_OPTIONS},
        # No maxLength: llama.cpp unrolls it into a grammar nested REASON_MAX_CHARS deep, which
        # exceeds its recursion limit and crashes the process. parse_answer trims the reason instead.
        "reason": {"type": "string"},
    },
    "required": ["choice", "reason"],
}

_ITEM_FIELDS = ("category", "type", "color", "pattern", "fabric", "fit")
_PREFERENCE_FIELDS = (
    "preferred_colors", "avoided_colors", "preferred_styles", "disliked_styles", "fit_preference",
)


def visual_match_label(probability: float | None) -> str:
    if probability is None:
        return "unknown"
    if probability >= 0.7:
        return "high"
    if probability >= 0.4:
        return "medium"
    return "low"


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (list, tuple)):
        cleaned = [_clean(entry) for entry in value]
        return [entry for entry in cleaned if entry not in (None, [], {})] or None
    return value


def build_user_payload(context: dict[str, Any], options: Sequence[dict[str, Any]]) -> str:
    """Serialize context and options deterministically (compact JSON)."""
    weather = context.get("weather") or {}
    preferences = context.get("preferences") or {}
    payload: dict[str, Any] = {
        "occasion": _clean(context.get("occasion")) or "casual",
        "weather": {
            "temperature_c": weather.get("temperature_c"),
            "condition": _clean(weather.get("condition")) or "unknown",
        },
    }
    for key in ("body_shape", "height_cm", "skin_tone"):
        value = _clean(context.get(key))
        if value is not None:
            payload[key] = value
    saved = {key: _clean(preferences.get(key)) for key in _PREFERENCE_FIELDS}
    saved = {key: value for key, value in saved.items() if value is not None}
    if saved:
        payload["preferences"] = saved
    payload["options"] = []
    for number, option in enumerate(list(options)[:MAX_OPTIONS], start=1):
        items = []
        for item in option.get("items", []):
            entry = {key: _clean(item.get(key)) for key in _ITEM_FIELDS}
            items.append({key: value for key, value in entry.items() if value is not None})
        payload["options"].append({
            "option": number,
            "visual_match": visual_match_label(option.get("visual_match")),
            "items": items,
        })
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_messages(context: dict[str, Any], options: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_payload(context, options)},
    ]


def format_answer(choice: int, reason: str) -> str:
    return json.dumps({"choice": int(choice), "reason": reason.strip()[:REASON_MAX_CHARS]}, ensure_ascii=False)


def parse_answer(raw: str, option_count: int) -> tuple[int, str]:
    """Parse and validate the model's JSON answer; raise ValueError if unusable."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw).strip(), flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object in stylist answer")
    decoded = json.loads(text[start:end + 1])
    if not isinstance(decoded, dict):
        raise ValueError("Stylist answer is not an object")
    choice = decoded.get("choice")
    if isinstance(choice, str) and choice.strip().isdigit():
        choice = int(choice.strip())
    if not isinstance(choice, int) or isinstance(choice, bool) or not 1 <= choice <= option_count:
        raise ValueError("Stylist choice is outside the offered options")
    reason = decoded.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 10:
        raise ValueError("Stylist reason is missing")
    return choice, reason.strip()[:REASON_MAX_CHARS]
