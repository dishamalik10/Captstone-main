"""Evaluate ranked recommendation slates using only actual explicit user feedback.

Unjudged items are excluded from the ranked judged list and judged coverage is
reported so small or biased samples are visible. No scores are fabricated.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import init_database, rows


POSITIVE_ACTIONS = {"save", "like", "wear"}
NEGATIVE_ACTIONS = {"skip", "dislike"}


def _relevance(action: str, rating: int | None) -> int | None:
    if action in POSITIVE_ACTIONS:
        return 1
    if action in NEGATIVE_ACTIONS:
        return 0
    if action == "rate" and rating is not None:
        return int(rating >= 4)
    return None


def _ndcg(relevances: list[int]) -> float | None:
    positives = sum(relevances)
    if positives == 0:
        return None
    dcg = sum(value / math.log2(index + 2) for index, value in enumerate(relevances))
    ideal = sum(1 / math.log2(index + 2) for index in range(positives))
    return dcg / ideal if ideal else None


def collect() -> dict[str, Any]:
    init_database()
    recommendations = rows(
        """SELECT recommendation_id,run_id,rank_position,created_at
           FROM recommendations WHERE run_id IS NOT NULL AND rank_position IS NOT NULL
             AND surface='recommend'  -- chat shows one outfit, not a ranked slate
           ORDER BY run_id,rank_position"""
    )
    feedback = rows(
        """SELECT recommendation_id,action,rating,created_at FROM feedback
           WHERE recommendation_id IS NOT NULL ORDER BY created_at"""
    )
    latest: dict[str, int | None] = {}
    for event in feedback:
        relevance = _relevance(event["action"], event["rating"])
        if relevance is not None:
            latest[event["recommendation_id"]] = relevance

    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in recommendations:
        runs[rec["run_id"]].append(rec)

    ndcgs, hit_at_3 = [], []
    judged_count = positive_count = 0
    runs_with_judgement = 0
    for slate in runs.values():
        slate.sort(key=lambda item: item["rank_position"])
        judged = [latest[rec["recommendation_id"]] for rec in slate
                  if rec["recommendation_id"] in latest]
        judged_count += len(judged)
        positive_count += sum(judged)
        if not judged:
            continue
        runs_with_judgement += 1
        metric = _ndcg(judged[:5])
        if metric is not None:
            ndcgs.append(metric)
        hit_at_3.append(float(any(judged[:3])))

    return {
        "recommendation_runs": len(runs),
        "recommendation_items_returned": len(recommendations),
        "explicitly_judged_items": judged_count,
        "judged_returned_fraction": round(judged_count / len(recommendations), 4) if recommendations else None,
        "positive_judgements": positive_count,
        "runs_with_judgement": runs_with_judgement,
        "mean_ndcg_judged_at_5": round(statistics.mean(ndcgs), 4) if ndcgs else None,
        "hit_rate_at_3_judged_runs": round(statistics.mean(hit_at_3), 4) if hit_at_3 else None,
        "label_policy": "save/like/wear=positive; skip/dislike=negative; rating >=4=positive, <=3=negative; latest explicit judgement wins",
        "limitations": [
            "Only explicit feedback is labelled; unjudged recommendations are not evidence of rejection.",
            "A stored recommendation slate was returned by the API; the database does not confirm that each card was rendered on the user's device.",
            "Metrics are descriptive and susceptible to selection and exposure bias.",
            "Do not use these metrics as a causal comparison without a randomized experiment.",
            "Small samples should not be interpreted as stable estimates.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = collect()
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
