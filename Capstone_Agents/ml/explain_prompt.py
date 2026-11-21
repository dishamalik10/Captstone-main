"""Prompt and target format for AURA's scratch-trained explanation model.

The model explains an outfit the server already selected. It sees only the
selected garments and the request context (no wider wardrobe, no rank scores),
and must answer with exactly ``{"item_ids": [...], "explanation": "..."}``
where ``item_ids`` repeats the selected IDs in order.

This file is shared verbatim by the backend and
``training/AURA_Scratch_Fashion_LM_Colab.ipynb`` so training prompts and
inference prompts are byte-identical. Keep it free of backend imports.
"""
from __future__ import annotations

import json
import re
from typing import Any

CATEGORY = "wardrobe_recommendation"
ITEM_FIELDS = ("item_id", "category", "subcategory", "color_name", "pattern", "fabric", "fit", "texture")
PREFERENCE_FIELDS = ("preferred_colors", "avoided_colors", "preferred_styles", "disliked_styles", "fit_preference")
TASK = (
    "Explain why the selected outfit works. Use only recorded item attributes and context. "
    "Do not add or remove clothing. Return exactly JSON with item_ids copied in the same order "
    "and explanation as a concise string."
)
_ITEM_ALIASES = {
    "subcategory": ("subcategory", "name", "type_name", "garment"),
    "category": ("category", "type", "slot"),
    "color_name": ("color_name", "color", "colour"),
}
_CATEGORY_NAMES = {
    "top": "Top", "tops": "Top", "bottom": "Bottom", "bottoms": "Bottom",
    "dress": "Dress", "dresses": "Dress", "shoe": "Footwear", "shoes": "Footwear",
    "footwear": "Footwear", "outerwear": "Outerwear", "jacket": "Outerwear",
    "coat": "Outerwear", "accessory": "Accessory", "accessories": "Accessory",
    "bag": "Accessory", "bags": "Accessory",
}


def make_prompt(category: str, user_input: str) -> str:
    return f"### Category: {category}\n### User:\n{user_input}\n### Assistant:\n"


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Map an item onto ITEM_FIELDS, accepting common alternative key names."""
    result: dict[str, Any] = {}
    for field in ITEM_FIELDS:
        value = None
        for key in _ITEM_ALIASES.get(field, (field,)):
            if item.get(key) not in (None, ""):
                value = item[key]
                break
        if field == "item_id" and value is not None:
            value = str(value)
        if field == "category" and isinstance(value, str):
            value = _CATEGORY_NAMES.get(value.strip().lower(), value)
        result[field] = value
    return result


def normalize_weather(weather: Any) -> dict[str, Any]:
    if isinstance(weather, dict):
        temperature = weather.get("temperature_c", weather.get("temperature"))
        condition = weather.get("condition", weather.get("summary"))
    else:
        temperature, condition = None, weather
    return {
        "temperature_c": None if temperature is None else float(temperature),
        "condition": None if condition is None else str(condition),
    }


def build_request(
    selected_items: list[dict[str, Any]],
    *,
    occasion: Any,
    weather: Any,
    preferences: dict[str, Any] | None = None,
) -> str:
    """Serialize the model input; the selected outfit comes first so truncation cannot cut it."""
    request = {
        "selected_outfit": [normalize_item(item) for item in selected_items],
        "occasion": occasion,
        "weather": normalize_weather(weather),
        "saved_preferences": {key: (preferences or {}).get(key) for key in PREFERENCE_FIELDS},
        "task": TASK,
    }
    return json.dumps(request, ensure_ascii=False, separators=(",", ":"))


def build_target(item_ids: list[str], explanation: str) -> str:
    return json.dumps(
        {"item_ids": [str(item_id) for item_id in item_ids], "explanation": explanation.strip()},
        ensure_ascii=False, separators=(",", ":"),
    )


def _load_object(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(value).strip(), flags=re.IGNORECASE)
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return None


def convert_training_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a recommend-style example into an explain-this-outfit example.

    The gold outfit and gold rationale become the selected outfit and target
    explanation. Returns None when the row has no usable outfit and rationale.
    """
    source = _load_object(row.get("input"))
    target = _load_object(row.get("output"))
    if not isinstance(source, dict) or not isinstance(target, dict):
        return None
    outfit = target.get("outfit", target.get("item_ids"))
    explanation = target.get("rationale", target.get("explanation"))
    if not isinstance(outfit, list) or not outfit or not isinstance(explanation, str) or not explanation.strip():
        return None
    wardrobe = source.get("wardrobe") or source.get("available_wardrobe") or []
    by_id = {str(item.get("item_id")): item for item in wardrobe if isinstance(item, dict)}
    selected = []
    for entry in outfit:
        item_id = str(entry.get("item_id")) if isinstance(entry, dict) else str(entry)
        attributes = {**(entry if isinstance(entry, dict) else {}), **by_id.get(item_id, {})}
        if item_id in ("", "None") or (item_id not in by_id and len(attributes) <= 1):
            return None
        selected.append({**attributes, "item_id": item_id})
    if len({item["item_id"] for item in selected}) != len(selected):
        return None
    return {
        "id": row.get("id"),
        "category": CATEGORY,
        "input": build_request(
            selected,
            occasion=source.get("occasion"),
            weather=source.get("weather"),
            preferences=source.get("saved_preferences") or source.get("preferences"),
        ),
        "output": build_target([item["item_id"] for item in selected], explanation),
    }
