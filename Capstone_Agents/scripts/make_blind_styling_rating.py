"""Create a blinded human comparison sheet from scratch-vs-rules generations.

The input must come from scripts/evaluate_scenarios.py after the scratch model is
actually loaded. The output is an evaluation artifact, not training data.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any


def create_sheet(pairs_path: Path, output_path: Path, *, seed: int = 23) -> Path:
    pairs = [
        json.loads(line)
        for line in pairs_path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    if not pairs:
        raise ValueError("No paired generations found; run the evaluator after the scratch model is loaded.")
    rng = random.Random(seed)
    key: dict[str, dict[str, str]] = {}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id", "occasion", "temperature_c", "wardrobe_and_selected_items",
        "response_a", "response_b", "grounding_1_to_5", "fashion_rationale_1_to_5",
        "occasion_weather_fit_1_to_5", "clarity_1_to_5", "unsupported_claim",
        "preferred_response", "comments",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for pair in pairs:
            reverse = bool(rng.getrandbits(1))
            a_source, b_source = (
                ("scratch_explanation", "baseline_explanation")
                if reverse else ("baseline_explanation", "scratch_explanation")
            )
            case_id = str(pair["case_id"])
            writer.writerow({
                "case_id": case_id,
                "occasion": pair.get("occasion", ""),
                "temperature_c": pair.get("temperature_c", ""),
                "wardrobe_and_selected_items": json.dumps({
                    "wardrobe": pair.get("wardrobe", []),
                    "selected_item_ids": pair.get("selected_item_ids", []),
                }, ensure_ascii=False),
                "response_a": pair[a_source],
                "response_b": pair[b_source],
            })
            key[case_id] = {
                "A": "scratch" if a_source.startswith("scratch") else "deterministic_baseline",
                "B": "scratch" if b_source.startswith("scratch") else "deterministic_baseline",
            }
    key_path = output_path.with_name(output_path.stem + "-blind-key.json")
    key_path.write_text(json.dumps({"seed": seed, "mapping": key}, indent=2), encoding="utf-8")
    return key_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pairs", type=Path,
        nargs="?",
        default=Path("training/checkpoints/fashion-evaluation/scratch-vs-rules.jsonl"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("training/checkpoints/fashion-evaluation/fashion-ratings.csv"),
    )
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()
    key_path = create_sheet(args.pairs, args.output, seed=args.seed)
    print(f"Blind rating sheet: {args.output}\nKeep the key separate from raters: {key_path}")


if __name__ == "__main__":
    main()
