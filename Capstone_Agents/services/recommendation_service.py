from __future__ import annotations

import itertools
import json
import logging
import math
import random
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from database import connection, decode_json_fields, rows, utc_now
from services.preference_service import get_preferences
from services.wardrobe_service import list_items
from services.agentic_recommender import (
    critique_candidate,
    execution_step,
    learned_preference_score,
    load_preference_memory,
    plan_recommendation,
    recent_worn_items,
    repetition_score,
    summarize_agent_run,
)
from services import bandit_ranker, outfit_compat_service, stylist_selector
from ml.stylist_prompt import MAX_OPTIONS as MAX_STYLIST_OPTIONS
from settings import settings
from services.trend_service import current_fashion_trends, trend_relevance
from services.compatibility_service import learned_compatibility_score
from services.fashion_analysis import analyze_outfit

LOGGER = logging.getLogger(__name__)


NEUTRALS = {
    "black", "white", "off white", "grey", "dark grey", "light grey",
    "beige", "dark beige", "light beige", "navy", "dark blue", "brown",
}
COLOR_FAMILIES = {
    "blue": {"blue", "dark blue", "light blue", "navy"},
    "red": {"red", "dark red", "light red", "pink", "dark pink", "light pink"},
    "green": {"green", "dark green", "light green", "olive"},
    "yellow": {"yellow", "dark yellow", "light yellow", "mustard"},
    "orange": {"orange", "dark orange", "light orange", "rust", "coral"},
    "bluegreen": {"teal", "turquoise", "cyan", "mint"},
    "purple": {"purple", "dark purple", "light purple"},
    "neutral": NEUTRALS,
}
KNOWN_COLORS = set(NEUTRALS).union(*(colors for colors in COLOR_FAMILIES.values()))
FORMAL_WORDS = {
    "blazer", "coat", "shirt", "dress", "trousers", "pumps", "heels",
    "loafer", "suit", "tailored", "formal",
}
CASUAL_WORDS = {
    "t-shirt", "tee", "jeans", "sneakers", "hoodie", "shorts", "casual",
}
SPORT_WORDS = {
    "sports", "legging", "sneakers", "trainer", "swim", "active",
}


def _words(items: Iterable[dict[str, Any]]) -> str:
    return " ".join(
        f"{item['subcategory']} {item.get('garment_group', '')} "
        f"{' '.join(item.get('style_tags', []))}"
        for item in items
    ).lower()


def _color_family(color: str) -> str:
    value = color.lower()
    for family, names in COLOR_FAMILIES.items():
        if value in names:
            return family
    return value


def color_score(items: list[dict[str, Any]]) -> float:
    colors = [str(item.get("color_name") or "unknown").lower() for item in items]
    if any(color == "unknown" or color not in KNOWN_COLORS for color in colors):
        return 50.0
    non_neutral = [_color_family(color) for color in colors if color not in NEUTRALS]
    if not non_neutral:
        return 92.0
    unique = set(non_neutral)
    if len(unique) == 1:
        return 90.0
    if len(unique) == 2:
        wheel = ("red", "orange", "yellow", "green", "bluegreen", "blue", "purple", "red")
        families = sorted(unique, key=lambda value: wheel.index(value) if value in wheel else len(wheel))
        if all(family in wheel for family in families):
            distance = abs(wheel.index(families[0]) - wheel.index(families[1]))
            distance = min(distance, len(wheel) - distance)
            if distance == 4:
                return 92.0  # approximate complementary pairing
            if distance == 1:
                return 87.0  # approximate analogous pairing
        return 76.0
    if len(unique) == 3:
        wheel = ("red", "orange", "yellow", "green", "bluegreen", "blue", "purple", "red")
        positions = sorted(wheel.index(value) for value in unique if value in wheel)
        gaps = sorted(
            [positions[(index + 1) % len(positions)] - positions[index] if index < len(positions) - 1
             else len(wheel) + positions[0] - positions[index] for index in range(len(positions))]
        )
        return 84.0 if len(positions) == 3 and max(gaps) - min(gaps) <= 1 else 70.0
    return 48.0


def _diverse_rerank(candidates: list[dict[str, Any]], limit: int, penalty_weight: float = 10.0,
                    score_key: str = "compatibility_score") -> list[dict[str, Any]]:
    """Greedy maximal-marginal-relevance rerank; preserves raw rule score separately."""
    remaining = list(candidates)
    selected: list[dict[str, Any]] = []
    while remaining and len(selected) < limit:
        def adjusted(entry: dict[str, Any]) -> tuple[float, int, tuple[str, ...]]:
            candidate_ids = set(entry["item_ids"])
            overlaps = [
                len(candidate_ids & set(previous["item_ids"]))
                / max(1, len(candidate_ids | set(previous["item_ids"])))
                for previous in selected
            ]
            overlap = max(overlaps, default=0.0)
            return (entry[score_key] - penalty_weight * overlap,
                    entry[score_key], tuple(sorted(entry["item_ids"])))

        best = max(remaining, key=adjusted)
        remaining.remove(best)
        candidate_ids = set(best["item_ids"])
        overlap = max((
            len(candidate_ids & set(previous["item_ids"]))
            / max(1, len(candidate_ids | set(previous["item_ids"])))
            for previous in selected
        ), default=0.0)
        best["diversity_penalty"] = round(penalty_weight * overlap, 1)
        selected.append(best)
    return selected


def occasion_score(items: list[dict[str, Any]], occasion: str) -> float:
    words = _words(items)
    occasion = occasion.lower()
    formal = sum(word in words for word in FORMAL_WORDS)
    casual = sum(word in words for word in CASUAL_WORDS)
    sport = sum(word in words for word in SPORT_WORDS)
    formal_occasions = {"wedding", "interview", "formal", "meeting", "office", "work", "smart casual"}
    if occasion in formal_occasions:
        score = min(100.0, 55 + formal * 12 - casual * 7)
    elif occasion in {"gym", "workout", "sport"}:
        score = min(100.0, 55 + sport * 15 - formal * 5)
    elif occasion == "date":
        has_dress = any(item.get("category") == "Dress" for item in items)
        has_outerwear = any(item.get("category") == "Outerwear" for item in items)
        has_accessory = any(item.get("category") == "Accessory" for item in items)
        score = min(
            100.0,
            66 + formal * 6 + (16 if has_dress else 0)
            + (5 if has_outerwear else 0) + (4 if has_accessory else 0)
            - casual * 5,
        )
    elif occasion in {"party", "festival", "concert"}:
        has_dress = any(item.get("category") == "Dress" for item in items)
        score = min(100.0, 68 + formal * 7 + (10 if has_dress else 0))
    else:
        score = min(100.0, 72 + casual * 5)
    occasion_terms = {
        "college": {"college", "campus", "casual"},
        "office": {"office", "work", "smart casual", "formal"},
        "work": {"office", "work", "smart casual", "formal"},
        "smart casual": {"office", "meeting", "smart casual"},
        "meeting": {"meeting", "office", "smart casual", "formal"},
        "wedding": {"wedding", "ceremony", "formal"},
        "interview": {"interview", "formal", "office"},
        "party": {"party", "evening", "festival"},
        "festival": {"festival", "party", "cultural"},
        "travel": {"travel", "casual", "walking"},
        "casual": {"casual", "everyday", "college"},
    }.get(occasion, {occasion})
    explicit = sum(
        bool(occasion_terms & {str(tag).lower() for tag in item.get("occasion_tags", [])})
        for item in items
    )
    score += min(18, explicit * 6)
    return max(0.0, min(100.0, score))


def weather_score(
    items: list[dict[str, Any]],
    temperature: float,
    condition: str,
) -> float:
    words = _words(items)
    score = 85.0
    if temperature >= 30:
        if any(word in words for word in ("coat", "wool", "fleece", "sweater", "jacket")):
            score -= 30
        if any(word in words for word in ("shorts", "t-shirt", "dress", "sandals")):
            score += 10
    elif temperature <= 15:
        if any(word in words for word in ("coat", "jacket", "sweater", "knit", "boots")):
            score += 12
        else:
            score -= 18
    if any(value in condition.lower() for value in ("rain", "drizzle", "storm")):
        if any(word in words for word in ("sandals", "suede", "slippers")):
            score -= 32
        if any(str(item.get("fabric") or "").lower() == "suede" for item in items):
            score -= 22
    fabrics = " ".join(str(item.get("fabric") or "").lower() for item in items)
    seasons = {str(season).lower() for item in items for season in item.get("seasons", [])}
    if temperature >= 30:
        if any(material in fabrics for material in ("linen", "cotton")):
            score += 6
        if "summer" in seasons:
            score += 4
    elif temperature <= 15:
        if any(material in fabrics for material in ("wool", "fleece", "cashmere", "knit")):
            score += 10
        if any(season in seasons for season in ("winter", "autumn")):
            score += 4
    return max(0.0, min(100.0, score))


def pattern_coordination_score(items: list[dict[str, Any]]) -> float:
    patterns = [
        str(item.get("pattern") or "").strip().lower()
        for item in items if item.get("pattern") and str(item.get("pattern")).strip().lower() not in {"solid", "plain", "none", "unknown"}
    ]
    if not patterns:
        return 50.0
    if len(set(patterns)) > 1:
        # Pattern scale and print geometry are not captured in these database fields.
        return 62.0
    return 88.0 if len(patterns) == 1 and len(items) > 1 else 78.0


def silhouette_balance_score(items: list[dict[str, Any]]) -> float:
    top = next((item for item in items if item.get("category") == "Top"), None)
    bottom = next((item for item in items if item.get("category") == "Bottom"), None)
    if top is None or bottom is None:
        return 65.0 if any(item.get("fit") for item in items) else 50.0
    top_fit = str(top.get("fit") or "").lower()
    bottom_fit = str(bottom.get("fit") or "").lower()
    if not top_fit or not bottom_fit:
        return 50.0
    roomy = {"oversized", "relaxed", "loose", "wide"}
    fitted = {"fitted", "slim", "skinny", "tailored"}
    top_roomy = any(value in top_fit for value in roomy)
    bottom_roomy = any(value in bottom_fit for value in roomy)
    top_fitted = any(value in top_fit for value in fitted)
    bottom_fitted = any(value in bottom_fit for value in fitted)
    if top_roomy and bottom_fitted or bottom_roomy and top_fitted:
        return 92.0
    if top_roomy and bottom_roomy:
        return 70.0
    if top_fitted and bottom_fitted:
        return 78.0
    return 80.0


def fabric_weather_score(items: list[dict[str, Any]], temperature: float, condition: str) -> float:
    fabrics = " ".join(str(item.get("fabric") or "").lower() for item in items)
    if not fabrics.strip():
        return 50.0
    hot_materials = ("linen", "cotton", "viscose", "rayon")
    cold_materials = ("wool", "fleece", "cashmere", "knit", "down")
    heavy = ("wool", "fleece", "cashmere", "down", "fur")
    score = 72.0
    if temperature >= 30:
        if any(value in fabrics for value in hot_materials):
            score += 18
        if any(value in fabrics for value in heavy):
            score -= 35
    elif temperature <= 15:
        if any(value in fabrics for value in cold_materials):
            score += 20
        elif any(value in fabrics for value in hot_materials):
            score -= 12
    if any(value in condition.lower() for value in ("rain", "drizzle", "storm")):
        if "suede" in fabrics:
            score -= 30
    return max(0.0, min(100.0, score))


def preference_score(
    items: list[dict[str, Any]],
    preferences: dict[str, Any],
) -> float:
    colors = {item["color_name"].lower() for item in items}
    words = _words(items)
    preferred_colors = {value.lower() for value in preferences["preferred_colors"]}
    avoided_colors = {value.lower() for value in preferences["avoided_colors"]}
    preferred_styles = {value.lower() for value in preferences["preferred_styles"]}
    disliked_styles = {value.lower() for value in preferences["disliked_styles"]}
    score = 70.0
    score += 8 * len(colors & preferred_colors)
    score -= 18 * len(colors & avoided_colors)
    score += 6 * sum(style in words for style in preferred_styles)
    score -= 15 * sum(style in words for style in disliked_styles)
    fit = (preferences.get("fit_preference") or "").lower()
    if fit and any((item.get("fit") or "").lower() == fit for item in items):
        score += 8
    return max(0.0, min(100.0, score))


def load_item_feedback(user_id: str) -> dict[str, dict[str, float]]:
    """Per-item decayed feedback signal, loaded once per recommendation request."""
    records = rows(
        "SELECT item_ids, action, rating, created_at FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT 250",
        (user_id,),
    )
    signal: dict[str, float] = defaultdict(float)
    observations: dict[str, int] = defaultdict(int)
    action_value = {"save": 2.0, "wear": 4.0, "like": 2.5, "skip": -1.5, "dislike": -4.0}
    now = datetime.now(timezone.utc)
    for record in records:
        try:
            created = datetime.fromisoformat(record["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created).total_seconds() / 86400.0)
        except (TypeError, ValueError):
            age_days = 0.0
        recency = math.exp(-math.log(2.0) * age_days / 90.0)
        reward = action_value.get(record["action"], 0.0)
        if record["rating"] is not None:
            reward += (record["rating"] - 3) * 0.8
        for item_id in json.loads(record["item_ids"]):
            signal[item_id] += reward * recency
            observations[item_id] += 1
    return {"signal": dict(signal), "observations": dict(observations)}


def feedback_score(
    user_id: str,
    item_ids: list[str],
    item_feedback: dict[str, dict[str, float]] | None = None,
) -> float:
    if not item_ids:
        return 50.0
    if item_feedback is None:
        item_feedback = load_item_feedback(user_id)
    signal = item_feedback["signal"]
    observations = item_feedback["observations"]
    normalized = [
        signal.get(item, 0.0) / (1.0 + 0.25 * math.log1p(observations.get(item, 0)))
        for item in item_ids
    ]
    mean_signal = sum(normalized) / len(normalized)
    return max(0.0, min(100.0, 50.0 + 35.0 * math.tanh(mean_signal / 5.0)))


MAX_PER_CATEGORY = 24
MAX_ADDON_FOOTWEAR = 8
MAX_ADDON_OUTERWEAR = 5
MAX_ADDON_ACCESSORIES = 6


def _group_by_category(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if len(groups[item["category"]]) < MAX_PER_CATEGORY:
            groups[item["category"]].append(item)
    return groups


def _bases(groups: dict[str, list[dict[str, Any]]]) -> list[tuple[dict[str, Any], ...]]:
    """Every structurally complete core: one dress, or one top with one bottom."""
    return [(dress,) for dress in groups["Dress"]] + [
        (top, bottom) for top in groups["Top"] for bottom in groups["Bottom"]
    ]


def _addons(groups: dict[str, list[dict[str, Any]]]) -> list[tuple[Any, Any, Any]]:
    """Footwear / outerwear / accessory variants, simplest variants first."""
    footwear = groups["Footwear"][:MAX_ADDON_FOOTWEAR] or [None]
    outerwear = [None, *groups["Outerwear"][:MAX_ADDON_OUTERWEAR]]
    accessories = [None, *groups["Accessory"][:MAX_ADDON_ACCESSORIES]]
    variants = list(itertools.product(footwear, outerwear, accessories))
    variants.sort(key=lambda variant: (variant[1] is not None) + (variant[2] is not None))
    return variants


def _assemble(base: tuple[dict[str, Any], ...], addon: tuple[Any, Any, Any]) -> list[dict[str, Any]]:
    return [*base, *(item for item in addon if item is not None)]


def _candidates(
    items: list[dict[str, Any]], limit: int = 750, seed: int = 0
) -> list[list[dict[str, Any]]]:
    """Spread the candidate budget across *all* complete cores.

    The previous version enumerated add-ons for the first core before moving on,
    so a 750-candidate budget was spent almost entirely on the newest top. Here
    every dress and every top/bottom pair gets an equal share of the budget, and
    add-ons are sampled so each core is tried with different shoes and layers.
    """
    groups = _group_by_category(items)
    bases = _bases(groups)
    if not bases:
        return []
    rng = random.Random(seed)
    if len(bases) > limit:
        bases = rng.sample(bases, limit)
    addons = _addons(groups)
    per_base = max(1, limit // len(bases))
    candidates: list[list[dict[str, Any]]] = []
    for base in bases:
        if len(addons) <= per_base:
            chosen = addons
        else:
            # Always try each pair of shoes without extra layers, then sample the rest.
            simple = [variant for variant in addons if variant[1] is None and variant[2] is None]
            chosen = simple[:per_base]
            remaining = per_base - len(chosen)
            if remaining > 0:
                chosen += rng.sample(addons[len(simple):], min(remaining, len(addons) - len(simple)))
        candidates.extend(_assemble(base, addon) for addon in chosen)
    return candidates


def _refinement_candidates(
    items: list[dict[str, Any]], top_bases: list[tuple[str, ...]], seen: set[tuple[str, ...]]
) -> list[list[dict[str, Any]]]:
    """Try every add-on combination for the best-scoring cores (bounded local search)."""
    groups = _group_by_category(items)
    by_ids = {tuple(sorted(item["item_id"] for item in base)): base for base in _bases(groups)}
    addons = _addons(groups)
    extra = []
    for key in top_bases:
        base = by_ids.get(key)
        if base is None:
            continue
        for addon in addons:
            candidate = _assemble(base, addon)
            if tuple(sorted(item["item_id"] for item in candidate)) not in seen:
                extra.append(candidate)
    return extra


def _explanation(
    items: list[dict[str, Any]],
    occasion: str,
    scores: dict[str, float],
) -> str:
    names = ", ".join(
        f"{item['color_name']} {item['subcategory']}" for item in items
    )
    strongest = max(scores, key=scores.get)
    messages = {
        "color": "The reported color families receive a favorable palette signal from the rule ranker.",
        "occasion": f"The garment categories receive a favorable {occasion} signal from the occasion rules.",
        "weather": "The selected categories receive a favorable signal for the supplied weather; fabric performance is unknown unless recorded.",
        "preference": "The selection reflects your saved colors and style preferences.",
        "feedback": "Your previous saves and wears support these item choices.",
        "learned_preference": "Patterns learned from your feedback support this selection.",
        "novelty": "This combination avoids overusing your recently worn pieces.",
        "trend": "Cached fashion context contributed a small supporting signal; its freshness is not guaranteed.",
        "learned_compatibility": "The compatibility model contributes a learned co-occurrence signal; it is not a personal rating.",
        "pattern": "The recorded patterns are consistent; print scale and visual balance are not available to the ranker.",
        "silhouette": "The recorded top and bottom fit labels support the silhouette balance signal; body measurements are not inferred.",
        "fabric_weather": "Recorded fabric labels contribute to the weather signal; construction and actual warmth are unknown.",
    }
    return f"Available pieces: {names}. {messages[strongest]}"


REFINEMENT_BASES = 6


def _score_entries(
    candidates: list[list[dict[str, Any]]],
    *,
    user_id: str,
    occasion: str,
    temperature: float,
    condition: str,
    preferences: dict[str, Any],
    trend_context: dict[str, Any],
    owned_item_ids: set[str],
    item_feedback: dict[str, dict[str, float]],
    preference_memory: dict[str, Any] | None,
    worn: list[str],
) -> list[dict[str, Any]]:
    """Score candidates with the rule signals plus the best available compatibility model."""
    item_level = outfit_compat_service.score_outfits(user_id, candidates)
    entries = []
    for index, items in enumerate(candidates):
        item_ids = [item["item_id"] for item in items]
        scores = {
            "color": color_score(items),
            "pattern": pattern_coordination_score(items),
            "silhouette": silhouette_balance_score(items),
            "fabric_weather": fabric_weather_score(items, temperature, condition),
            "occasion": occasion_score(items, occasion),
            "weather": weather_score(items, temperature, condition),
            "preference": preference_score(items, preferences),
            "feedback": feedback_score(user_id, item_ids, item_feedback),
            "learned_preference": learned_preference_score(user_id, items, preference_memory),
            "novelty": repetition_score(user_id, item_ids, worn),
            "trend": trend_relevance(items, trend_context),
        }
        rule_total = (
            scores["color"] * 0.17
            + scores["occasion"] * 0.17
            + scores["weather"] * 0.14
            + scores["preference"] * 0.14
            + scores["feedback"] * 0.08
            + scores["learned_preference"] * 0.13
            + scores["novelty"] * 0.05
            + scores["trend"] * 0.03
            + scores["pattern"] * 0.03
            + scores["silhouette"] * 0.03
            + scores["fabric_weather"] * 0.03
        )
        visual = item_level[index] if item_level is not None else None
        if visual is not None:
            # Item-level visual compatibility learned from real Polyvore outfits.
            scores["learned_compatibility"] = visual
            weight = settings.outfit_compat_weight
            total = rule_total * (1.0 - weight) + visual * weight
            source = "item_level"
        else:
            category_level = learned_compatibility_score(items)
            if category_level is not None:
                scores["learned_compatibility"] = category_level
                total = rule_total * 0.88 + category_level * 0.12
                source = "category_level"
            else:
                total = rule_total
                source = "none"
        critique = critique_candidate(items, owned_item_ids, scores["occasion"], scores["weather"])
        entries.append({
            "item_ids": item_ids,
            "items": items,
            "compatibility_score": round(total),
            "component_scores": {key: round(value, 1) for key, value in scores.items()},
            "compatibility_source": source,
            "critic": critique,
        })
    return entries


def recommend(
    user_id: str,
    occasion: str,
    temperature: float,
    condition: str,
    limit: int,
    exclude_recommendation_ids: list[str] | None = None,
    *,
    use_stylist: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wardrobe = list_items(user_id, available_only=True)
    steps = [execution_step("wardrobe_retrieval_agent", "completed", available_items=len(wardrobe))]
    has_feedback = bool(rows("SELECT 1 FROM feedback WHERE user_id=? LIMIT 1", (user_id,)))
    plan = plan_recommendation(occasion, temperature, condition, has_feedback)
    steps.append(execution_step("planner_agent", "completed", plan=plan))
    candidates = _candidates(wardrobe)
    steps.append(execution_step("candidate_generation_agent", "completed", candidates_generated=len(candidates), strategy="budget_spread_across_all_complete_cores"))
    if not candidates:
        trace = summarize_agent_run(plan, 0, 0, False)
        trace["agents"] = steps + [execution_step("critic_agent", "skipped", reason="no_complete_candidates"), execution_step("ranker_agent", "skipped", reason="no_complete_candidates")]
        return [], trace
    preferences = get_preferences(user_id)
    trend_context = current_fashion_trends("India")
    steps.append(execution_step("context_agent", "completed", occasion=occasion, weather={"temperature_c": temperature, "condition": condition}, preferences_loaded=True, feedback_memory=has_feedback, trend_context_available=bool(trend_context)))
    owned_item_ids = {item["item_id"] for item in wardrobe}
    excluded_keys: set[tuple[str, ...]] = set()
    requested_exclusions = list(dict.fromkeys(exclude_recommendation_ids or []))[:50]
    if requested_exclusions:
        matching = rows(
            "SELECT item_ids FROM recommendations WHERE user_id=? AND recommendation_id IN (%s)"
            % ",".join("?" for _ in requested_exclusions),
            (user_id, *requested_exclusions),
        )
        excluded_keys = {
            tuple(sorted(json.loads(record["item_ids"]))) for record in matching
        }
    context = dict(
        user_id=user_id, occasion=occasion, temperature=temperature, condition=condition,
        preferences=preferences, trend_context=trend_context, owned_item_ids=owned_item_ids,
        item_feedback=load_item_feedback(user_id),
        preference_memory=load_preference_memory(user_id),
        worn=recent_worn_items(user_id),
    )

    def unique(batch: list[list[dict[str, Any]]], seen: set[tuple[str, ...]]) -> list[list[dict[str, Any]]]:
        kept = []
        for items in batch:
            key = tuple(sorted(item["item_id"] for item in items))
            if key in excluded_keys or key in seen:
                continue
            seen.add(key)
            kept.append(items)
        return kept

    seen: set[tuple[str, ...]] = set()
    entries = _score_entries(unique(candidates, seen), **context)
    # Bounded refinement: try every shoe/layer/accessory variant for the best cores.
    best_bases: list[tuple[str, ...]] = []
    for entry in sorted(entries, key=lambda value: value["compatibility_score"], reverse=True):
        base = tuple(sorted(
            item["item_id"] for item in entry["items"]
            if item["category"] in {"Dress", "Top", "Bottom"}
        ))
        if base not in best_bases:
            best_bases.append(base)
        if len(best_bases) >= REFINEMENT_BASES:
            break
    refined = unique(_refinement_candidates(wardrobe, best_bases, seen), seen)
    if refined:
        entries += _score_entries(refined, **context)
    ranked = [entry for entry in entries if entry["critic"]["passed"]]
    rejected = [entry for entry in entries if not entry["critic"]["passed"]]
    critique_issue_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        for issue in entry["critic"]["issues"]:
            critique_issue_counts[issue] += 1
    sources = sorted({entry["compatibility_source"] for entry in entries})
    steps.append(execution_step("scoring_agents", "completed", agents=["palette", "occasion", "weather", "explicit_preference", "feedback_memory", "learned_preference", "wear_history", "trend_cache", "compatibility_model"], scored_candidates=len(entries), refinement_candidates=len(refined), compatibility_sources=sources))
    steps.append(execution_step("critic_agent", "completed", accepted=len(ranked), rejected=len(rejected), issue_counts=dict(critique_issue_counts)))
    revised = False
    if not ranked and rejected:
        # One bounded revision: retain ownership-safe, complete outfits and apply
        # an explicit penalty for the remaining contextual weakness.
        revised = True
        for entry in rejected:
            blocking = {"contains_unowned_item", "incomplete_base_outfit"}
            if not blocking.intersection(entry["critic"]["issues"]):
                entry["compatibility_score"] = max(0, entry["compatibility_score"] - 12)
                ranked.append(entry)
    steps.append(execution_step("revision_agent", "completed" if revised else "skipped", revision_rounds=1 if revised else 0, reason="no_candidate_passed_context_critique" if revised else "at_least_one_candidate_passed_critique"))
    # Personalised policy: a per-user contextual bandit (Thompson sampling) re-scores the
    # candidates once the user has given feedback; before that the hand-tuned prior is used.
    personalised = settings.bandit_enabled and bandit_ranker.rank(user_id, ranked, occasion)
    score_key = "bandit_score" if personalised else "compatibility_score"
    ranked.sort(key=lambda entry: entry[score_key], reverse=True)
    pool = _diverse_rerank(ranked, max(limit, MAX_STYLIST_OPTIONS if use_stylist else limit), score_key=score_key)
    steps.append(execution_step("ranking_agent", "completed", eligible_candidates=len(ranked), selected=min(limit, len(pool)), method="contextual_bandit_thompson_sampling_then_diversity_rerank" if personalised else "weighted_signals_then_diversity_rerank"))

    stylist_choice = None
    if use_stylist and len(pool) > 1:
        options = pool[:MAX_STYLIST_OPTIONS]
        stylist_context = {
            "occasion": occasion,
            # 25 C / "Unknown" is the API's placeholder when no weather was supplied.
            "weather": {
                "temperature_c": None if condition.lower() == "unknown" and temperature == 25.0 else temperature,
                "condition": condition,
            },
            "preferences": preferences,
            **stylist_selector.load_user_context(user_id),
        }
        stylist_choice = stylist_selector.choose(options, stylist_context)
        if stylist_choice is not None:
            chosen = pool.pop(stylist_choice["index"])
            pool.insert(0, chosen)
        steps.append(execution_step(
            "stylist_llm_agent",
            "completed" if stylist_choice is not None else "skipped",
            model=stylist_selector.model_source(),
            options_considered=len(options),
            chosen_option=None if stylist_choice is None else stylist_choice["index"] + 1,
            may_add_or_change_items=False,
            may_change_rank=True,
            changed_rank=stylist_choice is not None and stylist_choice["index"] != 0,
        ))
    selected = pool[:limit]

    result = []
    run_id = f"run_{uuid.uuid4().hex[:16]}"
    for rank_position, entry in enumerate(selected, start=1):
        recommendation_id = f"rec_{uuid.uuid4().hex[:12]}"
        explanation = _explanation(
            entry["items"],
            occasion,
            entry["component_scores"],
        )
        if rank_position == 1 and stylist_choice is not None and stylist_choice["reason_grounded"]:
            explanation = stylist_choice["reason"]
            entry["explanation_source"] = "stylist_llm"
        entry.update(
            recommendation_id=recommendation_id,
            explanation=explanation,
            analysis=analyze_outfit(entry["items"], occasion, temperature, condition),
        )
        entry.pop("critic", None)
        with connection() as db:
            db.execute(
                """
                INSERT INTO recommendations(
                    recommendation_id, user_id, occasion, item_ids,
                    component_scores, total_score, explanation, run_id,
                    rank_position, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id,
                    user_id,
                    occasion,
                    json.dumps(entry["item_ids"]),
                    json.dumps(entry["component_scores"]),
                    entry["compatibility_score"],
                    explanation,
                    run_id,
                    rank_position,
                    utc_now(),
                ),
            )
        result.append(entry)
    trace = summarize_agent_run(plan, len(entries), len(ranked), revised)
    trace["agents"] = steps
    return result, trace


def save_feedback(data: dict[str, Any]) -> None:
    recommendation_id = data.get("recommendation_id")
    if recommendation_id:
        record = rows(
            "SELECT user_id,item_ids FROM recommendations WHERE recommendation_id=?",
            (recommendation_id,),
        )
        if not record or record[0]["user_id"] != data["user_id"]:
            raise ValueError("Recommendation was not found for this user.")
        expected_items = set(json.loads(record[0]["item_ids"]))
        if set(data["item_ids"]) != expected_items:
            raise ValueError("Feedback item IDs must match the referenced recommendation.")
    with connection() as db:
        db.execute(
            """
            INSERT INTO feedback(
                user_id, recommendation_id, item_ids, action, rating, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data["user_id"],
                data.get("recommendation_id"),
                json.dumps(data["item_ids"]),
                data["action"],
                data.get("rating"),
                utc_now(),
            ),
        )
    if settings.bandit_enabled:
        try:
            bandit_ranker.learn_from_feedback(
                data["user_id"], data.get("recommendation_id"), data["action"], data.get("rating"),
            )
        except Exception:  # learning must never lose the user's saved feedback
            LOGGER.exception("Bandit update failed for recommendation %s", data.get("recommendation_id"))
