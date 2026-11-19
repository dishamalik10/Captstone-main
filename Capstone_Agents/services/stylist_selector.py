"""Let the AURA stylist LLM choose among the top server-built outfit options.

The ranker guarantees that every option is complete and made only of the
user's available garments. The LLM sees those options (without database IDs)
plus occasion, weather, self-described body shape, height, skin tone and saved
preferences, and answers with an option number and a reason. Anything invalid
falls back to the ranker's order, so the LLM can improve the choice but can
never break wardrobe safety.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from database import row
from ml.stylist_prompt import (
    MAX_OPTIONS,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    build_user_payload,
    parse_answer,
)
from services.local_llm import LocalLLM, LocalModelError, local_llm
from settings import settings

LOGGER = logging.getLogger(__name__)
_stylist_llm: LocalLLM | None = None

_COLOR_WORDS = {
    "black", "white", "grey", "gray", "red", "blue", "green", "yellow", "brown", "beige",
    "pink", "purple", "orange", "navy", "gold", "cream", "ivory", "olive", "teal",
    "turquoise", "mint", "lilac", "khaki", "burgundy", "maroon", "silver", "tan",
}


def _llm() -> LocalLLM | None:
    """Prefer the fine-tuned stylist GGUF; otherwise reuse the chat model."""
    global _stylist_llm
    if not settings.stylist_llm_enabled:
        return None
    if settings.stylist_llm_model_path.is_file():
        if settings.stylist_llm_model_path == settings.llm_model_path:
            return local_llm
        if _stylist_llm is None:
            _stylist_llm = LocalLLM(settings.stylist_llm_model_path)
        return _stylist_llm
    if settings.llm_model_path.is_file():
        return local_llm
    return None


def model_source() -> str:
    if not settings.stylist_llm_enabled:
        return "disabled"
    if settings.stylist_llm_model_path.is_file():
        return "fine_tuned_stylist"
    if settings.llm_model_path.is_file():
        return "base_chat_model"
    return "unavailable"


def load_user_context(user_id: str) -> dict[str, Any]:
    record = row("SELECT profile_json FROM users WHERE user_id=?", (user_id,)) or {}
    try:
        profile = json.loads(record.get("profile_json") or "{}")
    except (TypeError, ValueError):
        profile = {}
    return {
        "body_shape": profile.get("bodyShape"),
        "height_cm": profile.get("heightCm"),
        "skin_tone": profile.get("skinTone"),
    }


def option_payload(entry: dict[str, Any]) -> dict[str, Any]:
    scores = entry.get("component_scores", {})
    visual = scores.get("learned_compatibility") if entry.get("compatibility_source") == "item_level" else None
    return {
        "visual_match": None if visual is None else float(visual) / 100.0,
        "items": [
            {
                "category": item.get("category"),
                "type": item.get("subcategory"),
                "color": item.get("color_name"),
                "pattern": item.get("pattern"),
                "fabric": item.get("fabric"),
                "fit": item.get("fit"),
            }
            for item in entry.get("items", [])
        ],
    }


def _reason_is_grounded(reason: str, items: list[dict[str, Any]], context: dict[str, Any]) -> bool:
    from services.recommendation_explainer import _has_unlisted_garment

    if _has_unlisted_garment(reason, items):
        return False
    recorded = {
        word for item in items for word in re.findall(r"[a-z]+", str(item.get("color_name") or "").lower())
    }
    # The reason may say which of the user's avoided colours the outfit leaves out.
    for color in (context.get("preferences") or {}).get("avoided_colors") or []:
        recorded.update(re.findall(r"[a-z]+", str(color).lower()))
    mentioned = {word for word in re.findall(r"[a-z]+", reason.lower()) if word in _COLOR_WORDS}
    return mentioned <= recorded


def choose(options: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``{"index", "reason", "reason_grounded"}`` or ``None`` on any failure."""
    options = options[:MAX_OPTIONS]
    if len(options) < 2:
        return None
    llm = _llm()
    if llm is None:
        return None
    try:
        raw = llm.generate_response(
            build_user_payload(context, [option_payload(entry) for entry in options]),
            system_prompt=SYSTEM_PROMPT,
            max_tokens=160,
            temperature=0.1,
            response_format={"type": "json_object", "schema": RESPONSE_SCHEMA},
        )
        choice, reason = parse_answer(raw, len(options))
    except (LocalModelError, ValueError, TypeError) as exc:
        LOGGER.info("Stylist LLM selection skipped: %s", exc)
        return None
    index = choice - 1
    return {
        "index": index,
        "reason": reason,
        "reason_grounded": _reason_is_grounded(reason, options[index].get("items", []), context),
    }
