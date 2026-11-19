"""Run a reproducible, held-out MLX generation audit for base or LoRA model.

This reports structural/wardrobe-grounding measures. It does not claim that
heuristic checks measure fashion taste or styling expertise.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "training/fashion_sft/test.jsonl"


def parse_json(text: str):
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def heldout_cases():
    rows = [json.loads(line) for line in DATA.open(encoding="utf-8")]
    # One complete and one incomplete held-out wardrobe, every task family.
    chosen = [r for r in rows if r["scenario_id"] in {"wardrobe_012", "wardrobe_045"}]
    return sorted(chosen, key=lambda r: (r["scenario_id"], r["topic"]))


def evaluate(model_path: str, adapter_path: str | None, output: Path):
    import mlx.core as mx
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import greedy_sampler

    model, tokenizer = load(model_path, adapter_path=adapter_path)
    predictions = []
    durations = []
    prompt_tokens = []
    generated_tokens = []
    for row in heldout_cases():
        messages = row["messages"][:2]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        prompt_tokens.append(len(tokenizer.encode(prompt)))
        start = time.perf_counter()
        completion = generate(model, tokenizer, prompt, max_tokens=192, sampler=greedy_sampler, verbose=False)
        durations.append(time.perf_counter() - start)
        output_tokens = len(tokenizer.encode(completion))
        generated_tokens.append(output_tokens)
        parsed = parse_json(completion)
        wardrobe_ids = {x["item_id"] for x in json.loads(row["instruction"])["available_wardrobe"]}
        selected = parsed.get("selected_item_ids", []) if isinstance(parsed, dict) else []
        valid_ids = (parsed is not None and isinstance(selected, list)
                     and all(isinstance(x, str) and x in wardrobe_ids for x in selected))
        predictions.append({
            "record_id": row["record_id"], "scenario_id": row["scenario_id"], "topic": row["topic"],
            "reference_source_ids": row["source_ids"], "raw_output": completion,
            "json_valid": parsed is not None, "selected_item_ids": selected,
            "selected_ids_in_wardrobe": valid_ids,
            "has_explanation": isinstance(parsed, dict) and isinstance(parsed.get("answer"), str) and bool(parsed["answer"].strip()),
        })
    valid = [p for p in predictions if p["json_valid"]]
    metrics = {
        "heldout_examples": len(predictions),
        "json_valid_count": len(valid),
        "json_parse_rate": len(valid) / len(predictions) if predictions else None,
        "wardrobe_id_compliant_count": sum(p["selected_ids_in_wardrobe"] for p in predictions),
        "nonempty_explanation_count": sum(p["has_explanation"] for p in predictions),
        "unique_outfit_sets": len({tuple(sorted(set(p["selected_item_ids"]))) for p in predictions if p["json_valid"]}),
        "median_generation_seconds": statistics.median(durations) if durations else None,
        "mean_generation_seconds": statistics.mean(durations) if durations else None,
        "mean_prompt_tokens": statistics.mean(prompt_tokens) if prompt_tokens else None,
        "mean_generated_tokens": statistics.mean(generated_tokens) if generated_tokens else None,
        "mlx_active_memory_gb_at_end": float(mx.get_active_memory() / 1e9),
        "interpretation": "Structural proxies only; outfit suitability, color harmony, and taste require human review. No user-feedback history exists in this synthetic test set.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"model_path": model_path, "adapter_path": adapter_path, "metrics": metrics, "predictions": predictions}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=str(ROOT / "model_artifacts/mlx_base"))
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evaluate(args.model, args.adapter, Path(args.output))
