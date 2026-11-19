from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from database import rows


POSITIVE_ACTIONS = {"save": 2.0, "like": 2.5, "wear": 4.0}
NEGATIVE_ACTIONS = {"skip": -1.5, "dislike": -4.0}


def plan_recommendation(
    occasion: str,
    temperature: float,
    condition: str,
    has_feedback: bool,
) -> dict[str, Any]:
    """Create a bounded, inspectable plan instead of allowing arbitrary tool calls."""
    tools = ["wardrobe_retrieval", "candidate_generator"]
    if condition.lower() != "unknown" or temperature != 25:
        tools.append("weather_context")
    tools.extend(["fashion_critic", "compatibility_scorer"])
    if has_feedback:
        tools.append("preference_memory")
    tools.append("personalized_ranker")
    return {
        "intent": "outfit_recommendation",
        "occasion": occasion,
        "tools": tools,
        "max_revision_rounds": 1,
    }


def load_preference_memory(user_id: str) -> dict[str, Any] | None:
    """Load learned attribute and attribute-pair rewards once per request."""
    records = rows(
        """SELECT f.action, f.rating, f.item_ids, f.created_at
           FROM feedback f
           WHERE f.user_id=?
           ORDER BY f.created_at DESC LIMIT 250""",
        (user_id,),
    )
    if not records:
        return None

    item_ids = {
        item_id
        for record in records
        for item_id in json.loads(record["item_ids"])
    }
    if not item_ids:
        return None
    placeholders = ",".join("?" for _ in item_ids)
    wardrobe = rows(
        f"""SELECT item_id,category,color_name,subcategory,style_tags
            FROM clothing_items WHERE user_id=? AND item_id IN ({placeholders})""",
        (user_id, *item_ids),
    )
    attributes: dict[str, list[str]] = {}
    for item in wardrobe:
        tags = json.loads(item["style_tags"] or "[]")
        attributes[item["item_id"]] = [
            f"category:{item['category'].lower()}",
            f"color:{item['color_name'].lower()}",
            f"type:{item['subcategory'].lower()}",
            *(f"style:{tag.lower()}" for tag in tags),
        ]

    weights: dict[str, float] = defaultdict(float)
    pair_weights: dict[tuple[str, str], float] = defaultdict(float)
    now = datetime.now(timezone.utc)
    for record in records:
        reward = POSITIVE_ACTIONS.get(record["action"], NEGATIVE_ACTIONS.get(record["action"], 0.0))
        if record["rating"]:
            reward += (record["rating"] - 3) * 1.5
        try:
            created = datetime.fromisoformat(record["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created).total_seconds() / 86400.0)
        except (TypeError, ValueError):
            age_days = 0.0
        # Ninety-day half-life lets the stylist adapt as taste changes while
        # preserving a weaker long-term memory of older choices.
        recency = math.exp(-math.log(2.0) * age_days / 90.0)
        weighted_reward = reward * recency
        record_attributes: list[list[str]] = []
        for item_id in json.loads(record["item_ids"]):
            item_attributes = attributes.get(item_id, [])
            record_attributes.append(item_attributes)
            for attribute in item_attributes:
                weights[attribute] += weighted_reward
        # Learn combinations the user repeatedly likes, not only isolated
        # colors or garment types.
        for index, left in enumerate(record_attributes):
            for right in record_attributes[index + 1:]:
                for left_value in left:
                    for right_value in right:
                        pair_weights[tuple(sorted((left_value, right_value)))] += weighted_reward
    return {"weights": dict(weights), "pair_weights": dict(pair_weights)}


_UNSET: Any = object()


def learned_preference_score(
    user_id: str,
    items: list[dict[str, Any]],
    memory: dict[str, Any] | None = _UNSET,
) -> float:
    """Generalize feedback from exact garments to colors, categories and style tags.

    Pass ``memory`` from :func:`load_preference_memory` to avoid re-reading the
    feedback table for every candidate outfit.
    """
    if memory is _UNSET:
        memory = load_preference_memory(user_id)
    if not memory:
        return 50.0
    weights = memory["weights"]
    pair_weights = memory["pair_weights"]

    candidate_attributes = []
    for item in items:
        candidate_attributes.extend(
            [
                f"category:{item['category'].lower()}",
                f"color:{item['color_name'].lower()}",
                f"type:{item['subcategory'].lower()}",
                *(f"style:{tag.lower()}" for tag in item.get("style_tags", [])),
            ]
        )
    if not candidate_attributes:
        return 50.0
    signal = sum(weights.get(value, 0.0) for value in candidate_attributes) / len(candidate_attributes)
    candidate_by_item = [
        [
            f"category:{item['category'].lower()}",
            f"color:{item['color_name'].lower()}",
            f"type:{item['subcategory'].lower()}",
            *(f"style:{tag.lower()}" for tag in item.get("style_tags", [])),
        ]
        for item in items
    ]
    combination_signals = []
    for index, left in enumerate(candidate_by_item):
        for right in candidate_by_item[index + 1:]:
            values = [
                pair_weights.get(tuple(sorted((left_value, right_value))), 0.0)
                for left_value in left
                for right_value in right
            ]
            if values:
                combination_signals.append(sum(values) / len(values))
    pair_signal = (
        sum(combination_signals) / len(combination_signals)
        if combination_signals else 0.0
    )
    return max(0.0, min(100.0, 50.0 + signal * 3.0 + pair_signal * 2.0))


def recent_worn_items(user_id: str) -> list[str]:
    recent = rows(
        """SELECT item_ids FROM feedback
           WHERE user_id=? AND action='wear'
           ORDER BY created_at DESC LIMIT 8""",
        (user_id,),
    )
    return [
        item_id
        for record in recent
        for item_id in json.loads(record["item_ids"])
    ]


def repetition_score(user_id: str, item_ids: list[str], worn: list[str] | None = None) -> float:
    if worn is None:
        worn = recent_worn_items(user_id)
    overlap = sum(worn.count(item_id) for item_id in item_ids)
    return max(20.0, 100.0 - overlap * 12.0)


def critique_candidate(
    items: list[dict[str, Any]],
    owned_item_ids: set[str],
    occasion_value: float,
    weather_value: float,
) -> dict[str, Any]:
    issues: list[str] = []
    categories = {item["category"] for item in items}
    ids = {item["item_id"] for item in items}
    if not ids.issubset(owned_item_ids):
        issues.append("contains_unowned_item")
    complete = "Dress" in categories or {"Top", "Bottom"}.issubset(categories)
    if not complete:
        issues.append("incomplete_base_outfit")
    if occasion_value < 45:
        issues.append("weak_occasion_match")
    if weather_value < 45:
        issues.append("weak_weather_match")
    return {"passed": not issues, "issues": issues}


def summarize_agent_run(
    plan: dict[str, Any],
    generated: int,
    accepted: int,
    revised: bool,
) -> dict[str, Any]:
    return {
        "plan": plan,
        "candidates_generated": generated,
        "candidates_accepted": accepted,
        "revision_performed": revised,
        "guardrails": [
            "owned_items_only",
            "complete_outfit_required",
            "bounded_revision",
        ],
    }


def execution_step(agent: str, status: str, **details: Any) -> dict[str, Any]:
    """Create a small, serializable audit record for one bounded agent step."""
    return {"agent": agent, "status": status, **details}
