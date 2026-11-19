"""Validate provenance, uniqueness, splits, chat format, and wardrobe IDs."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "training" / "fashion_sft"
TOPIC_COUNT = 21
EXPECTED_BASE = {"train": 80 * TOPIC_COUNT, "valid": 10 * TOPIC_COUNT, "test": 10 * TOPIC_COUNT}
EXPECTED_CURATED = {"train": 18, "valid": 3, "test": 3}
EXPECTED = {split: EXPECTED_BASE[split] + EXPECTED_CURATED[split] for split in EXPECTED_BASE}
NEAR_DUPLICATE_THRESHOLD = 0.80


def wardrobe_signature(prompt: dict) -> set[tuple]:
    fields = ("category", "name", "color", "fabric", "pattern", "fit", "texture", "seasons")
    return {tuple(tuple(item.get(field, [])) if isinstance(item.get(field), list) else item.get(field)
                  for field in fields) for item in prompt.get("available_wardrobe", [])}


def wardrobe_similarity(left: dict, right: dict) -> float:
    a, b = wardrobe_signature(left), wardrobe_signature(right)
    return len(a & b) / max(1, min(len(a), len(b)))


def validate() -> dict:
    knowledge = json.loads((ROOT / "knowledge" / "fashion_heuristics.json").read_text("utf-8"))
    allowed_sources = {source["id"] for source in knowledge["sources"]}
    records = []
    prompts = {}
    row_splits = {}
    scenario_rows = {}
    split_for_scenario = {}
    split_counts = {}
    seen_instruction, seen_pair = set(), set()
    errors = []
    for split, expected in EXPECTED.items():
        path = DATA / f"{split}.jsonl"
        rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
        split_counts[split] = len(rows)
        if len(rows) != expected:
            errors.append(f"{split} has {len(rows)} rows; expected {expected}.")
        for number, row in enumerate(rows, start=1):
            if row.get("synthetic") is not True:
                errors.append(f"{split}:{number} is not labeled synthetic.")
            if any(source not in allowed_sources for source in row.get("source_ids", [])):
                errors.append(f"{split}:{number} has an unknown source ID.")
            if not row.get("license"):
                errors.append(f"{split}:{number} has no license/provenance label.")
            if any("rmit2023_colour_theory" == source for source in row.get("source_ids", [])):
                errors.append(f"{split}:{number} uses the excluded NC-licensed RMIT source.")
            messages = row.get("messages", [])
            if [message.get("role") for message in messages] != ["system", "user", "assistant"]:
                errors.append(f"{split}:{number} must use system/user/assistant chat format.")
                continue
            if messages[1].get("content") != row.get("instruction") or messages[2].get("content") != row.get("response"):
                errors.append(f"{split}:{number} message and flat fields disagree.")
            try:
                prompt = json.loads(row["instruction"])
                answer = json.loads(row["response"])
            except (KeyError, json.JSONDecodeError):
                errors.append(f"{split}:{number} instruction/response are not JSON.")
                continue
            available_ids = {item.get("item_id") for item in prompt.get("available_wardrobe", [])}
            candidate_ids = {item_id for values in prompt.get("candidate_outfits", {}).values() for item_id in values}
            if not candidate_ids <= available_ids:
                errors.append(f"{split}:{number} candidate references an item outside the wardrobe.")
            selected_ids = answer.get("selected_item_ids")
            if not isinstance(selected_ids, list) or not set(selected_ids) <= available_ids:
                errors.append(f"{split}:{number} selects an item not in the supplied wardrobe.")
            if len(available_ids) != len(prompt.get("available_wardrobe", [])):
                errors.append(f"{split}:{number} has duplicate wardrobe IDs.")
            instruction_hash = hashlib.sha256(row["instruction"].encode()).hexdigest()
            pair_hash = hashlib.sha256((row["instruction"] + "\0" + row["response"]).encode()).hexdigest()
            if instruction_hash in seen_instruction:
                errors.append(f"Duplicate instruction in {split}:{number}.")
            if pair_hash in seen_pair:
                errors.append(f"Duplicate instruction/response pair in {split}:{number}.")
            seen_instruction.add(instruction_hash)
            seen_pair.add(pair_hash)
            prior_split = split_for_scenario.setdefault(row["scenario_id"], split)
            if prior_split != split:
                errors.append(f"Scenario group {row['scenario_id']} leaked across splits.")
            records.append(row)
            prompts[row["record_id"]] = prompt
            row_splits[row["record_id"]] = split
            scenario_rows.setdefault(row["scenario_id"], []).append((split, row, prompt, answer))
    if errors:
        raise ValueError("\n".join(errors[:30]))
    scenario_splits = {scenario: {entry[0] for entry in entries} for scenario, entries in scenario_rows.items()}
    if any(len(splits) != 1 for splits in scenario_splits.values()):
        raise ValueError("A wardrobe scenario appears in more than one split.")
    max_near_similarity = 0.0
    for left_split, right_split in (("train", "valid"), ("train", "test"), ("valid", "test")):
        left_rows = [(r, prompts[r["record_id"]]) for r in records if row_splits[r["record_id"]] == left_split]
        right_rows = [(r, prompts[r["record_id"]]) for r in records if row_splits[r["record_id"]] == right_split]
        # Distinct wardrobe compositions and attributes are the meaningful
        # duplicate signal; boilerplate Qwen chat tokens are excluded.
        for left, right in product(left_rows, right_rows):
            if left[0]["topic"] != right[0]["topic"]:
                continue
            score = wardrobe_similarity(left[1], right[1])
            max_near_similarity = max(max_near_similarity, score)
            if score >= NEAR_DUPLICATE_THRESHOLD:
                raise ValueError(f"Near-duplicate wardrobe across {left_split}/{right_split}: {left[0]['scenario_id']} and {right[0]['scenario_id']} ({score:.2f}).")
    for scenario, entries in scenario_rows.items():
        for _, row, prompt, answer in entries:
            if row.get("authorship", "").startswith("original_manual"):
                candidates = prompt.get("candidate_outfits", {})
                options = [candidates.get("option_a_item_ids"), candidates.get("option_b_item_ids")]
                if answer.get("selected_item_ids") not in options:
                    raise ValueError(f"Curated row {row['record_id']} does not select one supplied candidate.")
    topics = Counter(row["topic"] for row in records)
    report = {"status":"valid", "records":len(records), "splits":split_counts,
              "unique_instructions":len(seen_instruction), "scenario_groups":len(split_for_scenario),
              "topic_counts":dict(sorted(topics.items())),
              "source_ids_used":sorted({source for row in records for source in row["source_ids"]}),
              "synthetic_only":all(row["synthetic"] for row in records)}
    report["curated_manual_examples"] = sum(row.get("authorship", "").startswith("original_manual") for row in records)
    report["nc_licensed_training_rows"] = sum("NC" in row["license"] for row in records)
    report["near_duplicate_wardrobe_similarity_threshold"] = NEAR_DUPLICATE_THRESHOLD
    report["max_cross_split_same_topic_wardrobe_similarity"] = round(max_near_similarity, 4)
    report["cross_split_scenario_leaks"] = 0
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
