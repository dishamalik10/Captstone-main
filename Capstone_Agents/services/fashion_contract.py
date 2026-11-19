"""Hard checks for wardrobe-grounded AURA language-model output."""
from __future__ import annotations

import json
import re
from typing import Any


class InvalidFashionResponse(ValueError):
    pass


def parse_json_object(raw: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    start = text.find("{")
    if start < 0:
        raise InvalidFashionResponse("No JSON object in model output")
    depth = 0
    quoted = escaped = False
    for index, char in enumerate(text[start:], start):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                result = json.loads(text[start:index + 1])
                if isinstance(result, dict):
                    return result
                break
    raise InvalidFashionResponse("Model output is not one complete JSON object")


def validate_owned_outfit(
    item_ids: list[str],
    wardrobe: list[dict[str, Any]],
    *,
    expected_ids: list[str] | None = None,
) -> None:
    if not item_ids or len(item_ids) != len(set(item_ids)):
        raise InvalidFashionResponse("Outfit item IDs must be nonempty and unique")
    wardrobe_by_id = {str(item.get("item_id")): item for item in wardrobe}
    if not set(item_ids) <= wardrobe_by_id.keys():
        raise InvalidFashionResponse("Outfit contains an ID outside the user's wardrobe")
    if any(not wardrobe_by_id[item_id].get("available", True) for item_id in item_ids):
        raise InvalidFashionResponse("Outfit contains an unavailable wardrobe item")
    if expected_ids is not None and item_ids != expected_ids:
        raise InvalidFashionResponse("Model changed the deterministic outfit selection")
    categories = {wardrobe_by_id[item_id].get("category") for item_id in item_ids}
    if "Dress" not in categories and not {"Top", "Bottom"} <= categories:
        raise InvalidFashionResponse("Outfit needs a dress or a top and bottom")
    if any(item.get("available", True) and item.get("category") == "Footwear" for item in wardrobe):
        if "Footwear" not in categories:
            raise InvalidFashionResponse("Outfit omits available footwear")


def validate_explanation_json(
    raw: str,
    selected_items: list[dict[str, Any]],
    wardrobe: list[dict[str, Any]],
) -> str:
    result = parse_json_object(raw)
    if set(result) != {"item_ids", "explanation"}:
        raise InvalidFashionResponse("Expected exactly item_ids and explanation")
    ids = result["item_ids"]
    explanation = result["explanation"]
    if not isinstance(ids, list) or not all(isinstance(item_id, str) for item_id in ids):
        raise InvalidFashionResponse("item_ids must be an array of strings")
    expected_ids = [str(item["item_id"]) for item in selected_items]
    validate_owned_outfit(ids, wardrobe, expected_ids=expected_ids)
    if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 700:
        raise InvalidFashionResponse("Explanation must be nonempty and at most 700 characters")
    return explanation.strip()
