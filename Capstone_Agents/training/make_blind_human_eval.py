"""Create a randomized, blinded A/B rating sheet from evaluate.py outputs."""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("generations", type=Path)
    parser.add_argument("--output", type=Path, default=Path("training/checkpoints/human-ratings.csv"))
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    rows = [json.loads(line) for line in args.generations.read_text("utf-8").splitlines() if line.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    key = {}
    columns = ["example_id", "instruction", "response_a", "response_b",
               "grounding_1_to_5", "helpfulness_1_to_5", "clarity_1_to_5",
               "invented_or_unsafe_claim", "preferred_response", "comments"]
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            reversed_order = bool(rng.getrandbits(1))
            a_name, b_name = (("adapter_response", "base_response") if reversed_order
                              else ("base_response", "adapter_response"))
            writer.writerow({"example_id": row["example_id"],
                             "instruction": row["instruction"],
                             "response_a": row[a_name], "response_b": row[b_name]})
            key[row["example_id"]] = {"A": a_name.removesuffix("_response"),
                                      "B": b_name.removesuffix("_response")}
    key_path = args.output.with_name(args.output.stem + "-blind-key.json")
    key_path.write_text(json.dumps({"seed": args.seed, "mapping": key}, indent=2), encoding="utf-8")
    print(f"Rating sheet: {args.output}\nBlinding key (keep separate from raters): {key_path}")


if __name__ == "__main__":
    main()
