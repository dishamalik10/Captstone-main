"""Run deterministic recommendation checks on synthetic wardrobes in a temp DB."""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import sys
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASET = ROOT / "training" / "evaluation_cases.json"
OUTPUT = ROOT / "training" / "evaluation_scenarios_report.json"
TMP = tempfile.TemporaryDirectory(prefix="wearbefore-eval-")
os.environ["AURA_DATABASE_PATH"] = str(Path(TMP.name) / "evaluation.sqlite3")
os.environ["AURA_UPLOAD_DIR"] = str(Path(TMP.name) / "uploads")

from database import connection, init_database, rows
from services.fashion_analysis import analyze_outfit
from services.recommendation_service import recommend, feedback_score
from services.aura_fashion_lm import (
    explain_outfit as explain_with_scratch_lm,
    load_model as load_scratch_lm,
    model_info as fashion_lm_model_info,
)
from services.fashion_contract import validate_owned_outfit
from services.preference_service import get_preferences
from services.wardrobe_service import list_items
from services.recommendation_explainer import (
    _has_unlisted_garment,
    _has_unverified_claim,
    _rule_comparison,
    _rule_outfit_note,
)
from contracts.api_schemas import OutfitRecommendation


def seed(case: dict[str, Any]) -> str:
    user_id = f"eval-{case['id']}"
    now = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute("INSERT INTO users(user_id,display_name,email,password_hash,created_at) VALUES(?,?,?,?,?)",
                   (user_id, "Synthetic fixture", f"{user_id}@invalid.test", "fixture", now))
        db.execute("INSERT INTO preferences(user_id,updated_at) VALUES(?,?)", (user_id, now))
        for item in case["wardrobe"]:
            db.execute("""INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,image_path,confidence,pattern,fabric,fit,texture,seasons,style_tags,occasion_tags,available,created_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (item["id"], user_id, item["category"], item["name"], item["name"], item["color"], "", "{}", None, None, None, None,
                        json.dumps(item.get("seasons", [])), json.dumps(item.get("style_tags", [])), json.dumps(item.get("occasion_tags", [])), 1, now))
    return user_id


def pairwise_diversity(outfits: list[list[str]]) -> float | None:
    if len(outfits) < 2:
        return None
    distances = []
    for i, left in enumerate(outfits):
        for right in outfits[i + 1:]:
            union = set(left) | set(right)
            distances.append(1 - len(set(left) & set(right)) / max(1, len(union)))
    return round(statistics.mean(distances), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare rule explanations with the installed AURA scratch model.")
    parser.add_argument(
        "--require-scratch-model", action="store_true",
        help="Fail unless local AURA scratch weights load successfully; use after Colab transfer.",
    )
    parser.add_argument(
        "--pairs-output", type=Path,
        default=ROOT / "training" / "checkpoints" / "fashion-evaluation" / "scratch-vs-rules.jsonl",
    )
    args = parser.parse_args()
    init_database()
    scratch_status = fashion_lm_model_info()
    if scratch_status.get("weights_present"):
        try:
            load_scratch_lm()
        except Exception as exc:
            scratch_status = {**fashion_lm_model_info(), "load_error": str(exc)}
    else:
        scratch_status["load_error"] = "Weights are not installed; no language-model generations were attempted."
    if args.require_scratch_model and not scratch_status.get("ready"):
        raise SystemExit(
            "AURA scratch model is not loaded. Transfer the Colab final-model directory, "
            "set AURA_FASHION_LM_PATH, and retry. Status: " + json.dumps(scratch_status)
        )
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases, outputs, paired = [], [], []
    for case in dataset["cases"]:
        user_id = seed(case)
        recs, _ = recommend(user_id, case["occasion"], case["temperature_c"], "Clear", 5)
        owned = {item["id"] for item in case["wardrobe"]}
        ownership = all(set(rec["item_ids"]) <= owned for rec in recs)
        flattened_ids = [item_id for rec in recs for item_id in rec["item_ids"]]
        owned_id_count = sum(item_id in owned for item_id in flattened_ids)
        item_id_accuracy = owned_id_count / len(flattened_ids) if flattened_ids else None
        duplicate_id_count = sum(
            len(rec["item_ids"]) - len(set(rec["item_ids"])) for rec in recs
        )
        json_valid = True
        try:
            for rec in recs:
                OutfitRecommendation.model_validate(rec).model_dump_json()
        except Exception:
            json_valid = False
        complete = all(any(item["category"] == "Dress" for item in rec["items"]) or
                       ({"Top", "Bottom"} <= {item["category"] for item in rec["items"]}) for rec in recs)
        analyses = [analyze_outfit(rec["items"], case["occasion"], case["temperature_c"], "Clear") for rec in recs]
        scratch_record = {
            "attempted": False,
            "valid_structured_response": False,
            "item_ids_preserved": False,
            "unsupported_claim": None,
            "unlisted_garment": None,
            "explanation": None,
            "error": None,
        }
        if recs:
            rec = recs[0]
            rule_explanation = _rule_outfit_note({
                **rec,
                "analysis": analyze_outfit(rec["items"], case["occasion"], case["temperature_c"], "Clear"),
            })
            if scratch_status.get("ready"):
                scratch_record["attempted"] = True
                wardrobe = list_items(user_id, available_only=True)
                try:
                    scratch_explanation = explain_with_scratch_lm(
                        rec["items"], wardrobe,
                        occasion=case["occasion"],
                        temperature=case["temperature_c"],
                        condition="Clear",
                        preferences=get_preferences(user_id),
                        selection_signals=rec.get("component_scores", {}),
                    )
                    validate_owned_outfit(
                        rec["item_ids"], wardrobe, expected_ids=rec["item_ids"]
                    )
                    from services.fashion_contract import validate_explanation_json
                    validate_explanation_json(
                        json.dumps({"item_ids": rec["item_ids"], "explanation": scratch_explanation}),
                        rec["items"], wardrobe,
                    )
                    scratch_record.update(
                        valid_structured_response=True,
                        item_ids_preserved=True,
                        unsupported_claim=_has_unverified_claim(
                            scratch_explanation, rec["items"],
                            temperature=case["temperature_c"], condition="Clear",
                        ),
                        unlisted_garment=_has_unlisted_garment(scratch_explanation, rec["items"]),
                        explanation=scratch_explanation,
                    )
                    paired.append({
                        "case_id": case["id"], "occasion": case["occasion"],
                        "wardrobe": case["wardrobe"], "temperature_c": case["temperature_c"],
                        "selected_item_ids": rec["item_ids"],
                        "baseline_explanation": rule_explanation,
                        "scratch_explanation": scratch_explanation,
                    })
                except Exception as exc:
                    scratch_record["error"] = f"{type(exc).__name__}: {exc}"[:300]
            else:
                scratch_record["error"] = "Scratch model unavailable; deterministic explanation retained."
        tag_hits = sum(case["occasion"].lower() in analysis["occasion"]["recorded_tags"] for analysis in analyses)
        palette_unclassified = sum(analysis["palette"]["palette_type"] == "unknown_or_unclassified_color" for analysis in analyses)
        color_signals = [rec["component_scores"].get("color") for rec in recs if rec.get("component_scores", {}).get("color") is not None]
        occasion_signals = [rec["component_scores"].get("occasion") for rec in recs if rec.get("component_scores", {}).get("occasion") is not None]
        component_ranges = {}
        for key in ("color", "pattern", "silhouette", "fabric_weather", "occasion", "weather"):
            values = [rec.get("component_scores", {}).get(key) for rec in recs]
            values = [value for value in values if value is not None]
            component_ranges[key] = [min(values), max(values)] if values else None
        if recs:
            first_ids = recs[0]["item_ids"]
            before = feedback_score(user_id, first_ids)
            with connection() as db:
                db.execute("INSERT INTO feedback(user_id,item_ids,action,created_at) VALUES(?,?,?,?)",
                           (user_id, json.dumps(first_ids), "like", datetime.now(timezone.utc).isoformat()))
            after = feedback_score(user_id, first_ids)
            with connection() as db:
                db.execute("INSERT INTO feedback(user_id,item_ids,action,created_at) VALUES(?,?,?,?)",
                           (user_id, json.dumps(first_ids), "dislike", datetime.now(timezone.utc).isoformat()))
            after_dislike = feedback_score(user_id, first_ids)
            feedback_delta = round(after - before, 4)
            dislike_delta = round(after_dislike - after, 4)
        else:
            feedback_delta = None
            dislike_delta = None
        record = {
            "id": case["id"], "wardrobe_items": len(owned), "occasion": case["occasion"],
            "expected_outfit": case["expect_outfit"], "recommendations": len(recs),
            "expectation_met": bool(recs) == case["expect_outfit"],
            "wardrobe_compliance": ownership, "complete_outfits": complete,
            "item_id_accuracy": item_id_accuracy,
            "owned_item_id_count": owned_id_count,
            "item_id_count": len(flattened_ids),
            "duplicate_item_id_count": duplicate_id_count,
            "json_schema_valid": json_valid,
            "nonempty_explanations": sum(bool(rec.get("explanation")) for rec in recs),
            "comparison_explanation_chars": len(_rule_comparison(recs)),
            "component_score_ranges": component_ranges,
            "scratch_explanation": scratch_record,
            "top5_pairwise_diversity_jaccard_distance": pairwise_diversity([r["item_ids"] for r in recs]),
            "occasion_tag_coverage": f"{tag_hits}/{len(recs)}" if recs else "not_applicable",
            "occasion_rule_signal_range": [min(occasion_signals), max(occasion_signals)] if occasion_signals else None,
            "color_ranker_signal_range": [min(color_signals), max(color_signals)] if color_signals else None,
            "palette_type_proxy": [analysis["palette"]["palette_type"] for analysis in analyses],
            "palette_proxy_unclassified_count": palette_unclassified,
            "feedback_like_signal_delta": feedback_delta,
            "feedback_dislike_signal_delta": dislike_delta,
            "limitations": "Synthetic fixture; palette and occasion checks are metadata/rule proxies, not human style judgments.",
        }
        cases.append(record)
        outputs.extend(recs)
    report = {
        "dataset_version": dataset["dataset_version"], "dataset_provenance": dataset["provenance"],
        "cases": cases,
        "summary": {
            "case_expectations_met": sum(c["expectation_met"] for c in cases), "case_count": len(cases),
            "wardrobe_compliance_rate": sum(c["wardrobe_compliance"] for c in cases) / max(1, len(cases)),
            "item_id_accuracy": sum(c["owned_item_id_count"] for c in cases) / max(1, sum(c["item_id_count"] for c in cases)),
            "duplicate_item_id_count": sum(c["duplicate_item_id_count"] for c in cases),
            "json_schema_valid_rate": sum(c["json_schema_valid"] for c in cases) / max(1, len(cases)),
            "nonempty_explanation_rate": sum(c["nonempty_explanations"] for c in cases) / max(1, sum(c["recommendations"] for c in cases)),
            "cases_with_clarification_needed": sum(not c["expected_outfit"] for c in cases),
            "clarification_correct_rate": sum(c["expectation_met"] for c in cases if not c["expected_outfit"]) / max(1, sum(not c["expected_outfit"] for c in cases)),
            "complete_outfit_rate": sum(c["complete_outfits"] for c in cases if c["recommendations"]) / max(1, sum(bool(c["recommendations"]) for c in cases)),
            "mean_pairwise_diversity": statistics.mean([c["top5_pairwise_diversity_jaccard_distance"] for c in cases if c["top5_pairwise_diversity_jaccard_distance"] is not None]) if any(c["top5_pairwise_diversity_jaccard_distance"] is not None for c in cases) else None,
            "feedback_response_cases": sum(c["feedback_like_signal_delta"] is not None for c in cases),
            "feedback_signal_increased": sum(c["feedback_like_signal_delta"] > 0 for c in cases if c["feedback_like_signal_delta"] is not None),
            "feedback_dislike_signal_decreased": sum(c["feedback_dislike_signal_delta"] < 0 for c in cases if c["feedback_dislike_signal_delta"] is not None),
            "palette_proxy": "Per-outfit color-family labels from recorded color names; descriptive coverage only, not a harmony quality score or human judgment.",
            "occasion_proxy": "Explicit occasion-tag coverage plus the ranker's occasion component-signal range; neither is a human suitability judgment or calibrated quality score.",
        },
        "method": "Local deterministic ranking service with synthetic, hand-authored wardrobe fixtures; no LLM judged these outcomes.",
        "scratch_fashion_lm": fashion_lm_model_info(),
        "scratch_vs_rule_explanation_comparison": {
            "scenario_count": len(dataset["cases"]),
            "generations_attempted": sum(c["scratch_explanation"]["attempted"] for c in cases),
            "valid_structured_rate": (
                sum(c["scratch_explanation"]["valid_structured_response"] for c in cases)
                / max(1, sum(c["scratch_explanation"]["attempted"] for c in cases))
                if scratch_status.get("ready") else None
            ),
            "item_ids_preserved_rate": (
                sum(c["scratch_explanation"]["item_ids_preserved"] for c in cases)
                / max(1, sum(c["scratch_explanation"]["attempted"] for c in cases))
                if scratch_status.get("ready") else None
            ),
            "unsupported_claim_free_rate": (
                sum(not c["scratch_explanation"]["unsupported_claim"] for c in cases if c["scratch_explanation"]["valid_structured_response"])
                / max(1, sum(c["scratch_explanation"]["valid_structured_response"] for c in cases))
                if scratch_status.get("ready") else None
            ),
            "unlisted_garment_free_rate": (
                sum(not c["scratch_explanation"]["unlisted_garment"] for c in cases if c["scratch_explanation"]["valid_structured_response"])
                / max(1, sum(c["scratch_explanation"]["valid_structured_response"] for c in cases))
                if scratch_status.get("ready") else None
            ),
            "human_fashion_quality_rated": False,
            "interpretation": "This compares model-written explanations with the deterministic explanation for the same rule-selected outfit. It does not let the LM select or rank outfits, and automatic grounding checks are not a fashion-quality score.",
        },
    }
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if paired:
        args.pairs_output.parent.mkdir(parents=True, exist_ok=True)
        with args.pairs_output.open("w", encoding="utf-8") as stream:
            for item in paired:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Blind-rating inputs saved: {args.pairs_output}")
    print(json.dumps(report, indent=2))
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
