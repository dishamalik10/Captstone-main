from __future__ import annotations

import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import rows
from services.agentic_recommender import (
    critique_candidate,
    learned_preference_score,
    repetition_score,
)
from services.preference_service import get_preferences
from services.recommendation_service import (
    _candidates,
    color_score,
    feedback_score,
    occasion_score,
    preference_score,
    weather_score,
)
from services.trend_service import current_fashion_trends, trend_relevance
from services.wardrobe_service import list_items


METADATA = ROOT / "model_artifacts" / "fashion_cnn.metadata.json"
OUTPUT = ROOT / "model_artifacts" / "evaluation_report.json"
OCCASIONS = ("casual", "meeting", "date", "party")


def _diversity(outfits: list[list[str]]) -> float | None:
    if len(outfits) < 2:
        return None
    values = []
    for index, left in enumerate(outfits):
        for right in outfits[index + 1:]:
            union = set(left) | set(right)
            values.append(1 - len(set(left) & set(right)) / max(1, len(union)))
    return round(statistics.mean(values), 4)


def _evaluate_user(user_id: str) -> dict[str, Any]:
    wardrobe = list_items(user_id, available_only=True)
    owned = {item["item_id"] for item in wardrobe}
    preferences = get_preferences(user_id)
    trends = current_fashion_trends("India")
    generated = accepted = ownership_violations = incomplete = 0
    latencies = []
    top_outfits: list[list[str]] = []
    agent_scores = []
    baseline_scores = []

    for occasion in OCCASIONS:
        start = time.perf_counter()
        ranked = []
        for items in _candidates(wardrobe):
            generated += 1
            item_ids = [item["item_id"] for item in items]
            base = {
                "color": color_score(items),
                "occasion": occasion_score(items, occasion),
                "weather": weather_score(items, 25, "Clear"),
                "preference": preference_score(items, preferences),
                "feedback": feedback_score(user_id, item_ids),
            }
            critique = critique_candidate(
                items, owned, base["occasion"], base["weather"]
            )
            ownership_violations += "contains_unowned_item" in critique["issues"]
            incomplete += "incomplete_base_outfit" in critique["issues"]
            if not critique["passed"]:
                continue
            accepted += 1
            learned = learned_preference_score(user_id, items)
            novelty = repetition_score(user_id, item_ids)
            trend = trend_relevance(items, trends)
            baseline = (
                base["color"] * .25 + base["occasion"] * .25
                + base["weather"] * .20 + base["preference"] * .20
                + base["feedback"] * .10
            )
            agentic = (
                base["color"] * .18 + base["occasion"] * .18
                + base["weather"] * .15 + base["preference"] * .15
                + base["feedback"] * .10 + learned * .15
                + novelty * .05 + trend * .04
            )
            ranked.append((agentic, item_ids))
            baseline_scores.append(baseline)
            agent_scores.append(agentic)
        ranked.sort(reverse=True)
        top_outfits.extend(item_ids for _, item_ids in ranked[:5])
        latencies.append((time.perf_counter() - start) * 1000)

    return {
        "user_id": user_id,
        "wardrobe_items": len(wardrobe),
        "candidates_generated": generated,
        "critic_acceptance_rate": round(accepted / generated, 4) if generated else None,
        "owned_item_safety_rate": round(1 - ownership_violations / generated, 4) if generated else None,
        "complete_outfit_rate": round(1 - incomplete / generated, 4) if generated else None,
        "top5_pairwise_diversity": _diversity(top_outfits),
        "mean_baseline_score": round(statistics.mean(baseline_scores), 2) if baseline_scores else None,
        "mean_agentic_score": round(statistics.mean(agent_scores), 2) if agent_scores else None,
        "mean_ranking_latency_ms": round(statistics.mean(latencies), 2),
    }


def main() -> None:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    user_records = rows("SELECT user_id FROM users ORDER BY user_id")
    feedback_count = rows("SELECT COUNT(*) count FROM feedback")[0]["count"]
    positive = rows(
        "SELECT COUNT(*) count FROM feedback WHERE action IN ('wear','save','like')"
    )[0]["count"]
    evaluations = [_evaluate_user(record["user_id"]) for record in user_records]
    eligible = [item for item in evaluations if item["candidates_generated"]]

    report = {
        "evaluation_version": "1.0",
        "cnn": {
            "architecture": metadata.get("architecture"),
            "training_images": metadata.get("training_counts", {}).get("total"),
            "validation_product_type_accuracy": metadata.get("best_validation_metrics", {}).get("product_type_accuracy"),
            "independent_test_metrics": metadata.get("test_metrics"),
            "status": "validation-only; independent held-out test evaluation still required",
        },
        "dataset": {
            "users": len(user_records),
            "feedback_events": feedback_count,
            "positive_feedback_events": positive,
            "eligible_wardrobes": len(eligible),
        },
        "recommendation_system": {
            "per_user": evaluations,
            "mean_owned_item_safety_rate": round(statistics.mean(item["owned_item_safety_rate"] for item in eligible), 4) if eligible else None,
            "mean_complete_outfit_rate": round(statistics.mean(item["complete_outfit_rate"] for item in eligible), 4) if eligible else None,
            "mean_top5_pairwise_diversity": round(statistics.mean(item["top5_pairwise_diversity"] for item in eligible if item["top5_pairwise_diversity"] is not None), 4) if any(item["top5_pairwise_diversity"] is not None for item in eligible) else None,
        },
        "learning_evaluation": {
            "ndcg_at_5": None,
            "precision_at_3": None,
            "reason": "At least 500 recommendation impressions with positive and negative feedback are recommended; only explicit feedback is currently logged.",
        },
        "trend_grounding": current_fashion_trends("India"),
        "limitations": [
            "The CNN metadata contains no independent test-set metrics.",
            "Nine feedback events are insufficient for reliable ranking evaluation.",
            "No impression table currently records every outfit shown and its rank position.",
            "Offline scores do not replace a user study or A/B test.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
