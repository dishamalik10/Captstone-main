"""Validate, deduplicate, provenance-stamp, and split licensed JSONL records.

Input fields: participant_id, instruction, response, source, and license.
No records are generated here; participant IDs must be pseudonymous.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

from settings import settings


def prepare(
    source: Path, output: Path, seed: int = 23, group_field: str = "participant_id"
) -> dict[str, int]:
    records = {}
    source_record_count = 0
    for line_number, line in enumerate(source.read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Record {line_number} is not valid JSON: {exc.msg}.") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Record {line_number} must be a JSON object.")
        if not isinstance(row.get("instruction"), str) or not isinstance(row.get("response"), str):
            raise ValueError(f"Record {line_number} instruction and response must be strings.")
        instruction = " ".join(row["instruction"].split())
        response = " ".join(row["response"].split())
        provenance = str(row.get("source", "")).strip()
        license_name = str(row.get("license", "")).strip()
        group = str(row.get(group_field, "")).strip()
        if not instruction or not response or not provenance or not license_name or not group:
            raise ValueError(
                f"Record {line_number} needs instruction, response, source, license, and {group_field}."
            )
        if "@" in group or len(group) > 64:
            raise ValueError(f"Record {line_number} participant_id must be a short pseudonymous ID, not an email.")
        if len(instruction) > 12000 or len(response) > 12000:
            raise ValueError(f"Record {line_number} exceeds the 12,000-character quality limit.")
        digest = hashlib.sha256((instruction + "\0" + response).encode()).hexdigest()
        source_record_count += 1
        row_provenance = {"source": provenance, "license": license_name}
        if digest not in records:
            records[digest] = {"instruction": instruction, "response": response,
                               "source": provenance, "license": license_name,
                               "participant_id": group,
                               "provenance": [row_provenance], "record_id": digest}
        elif row_provenance not in records[digest]["provenance"]:
            records[digest]["provenance"].append(row_provenance)
    values = list(records.values())
    n = len(values)
    groups: dict[str, list[dict]] = {}
    for record in values:
        groups.setdefault(record["participant_id"], []).append(record)
    if len(groups) < 3:
        raise ValueError("At least three distinct participant_id groups are required for leakage-safe splits.")
    group_ids = list(groups)
    random.Random(seed).shuffle(group_ids)  # randomizes equal-size group tie breaks
    group_ids.sort(key=lambda group_id: len(groups[group_id]), reverse=True)
    targets = {"train": .8, "validation": .1, "test": .1}
    group_splits: dict[str, set[str]] = {name: set() for name in targets}
    example_counts = {name: 0 for name in targets}
    for group_id in group_ids:
        split = min(targets, key=lambda name: (example_counts[name] / targets[name], len(group_splits[name])))
        group_splits[split].add(group_id)
        example_counts[split] += len(groups[group_id])
    splits = {
        split: [record for record in values if record["participant_id"] in group_ids_for_split]
        for split, group_ids_for_split in group_splits.items()
    }
    output.mkdir(parents=True, exist_ok=True)
    for split, rows in splits.items():
        with (output / f"{split}.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    content_for_version = json.dumps(values, sort_keys=True, ensure_ascii=False)
    all_provenance = [p for r in values for p in r["provenance"]]
    split_quality = {}
    for split, split_rows in splits.items():
        participant_sizes = [
            sum(record["participant_id"] == participant for record in split_rows)
            for participant in group_splits[split]
        ]
        lengths = [len(row["instruction"]) + len(row["response"]) for row in split_rows]
        split_quality[split] = {
            "participant_groups": len(group_splits[split]),
            "min_records_per_participant": min(participant_sizes),
            "median_records_per_participant": statistics.median(participant_sizes),
            "max_records_per_participant": max(participant_sizes),
            "median_instruction_plus_response_chars": statistics.median(lengths),
        }
    manifest = {"version": hashlib.sha256(content_for_version.encode()).hexdigest()[:16],
                "seed": seed, "records": n, "source_records": source_record_count,
                "deduplicated_examples": source_record_count - n,
                "splits": {k: len(v) for k, v in splits.items()},
                "group_field": group_field,
                "groups_per_split": {k: len(v) for k, v in group_splits.items()},
                "split_quality": split_quality,
                "sources": sorted({p["source"] for p in all_provenance}),
                "licenses": sorted({p["license"] for p in all_provenance}),
                "deduplicated_records": sum(len(r["provenance"]) > 1 for r in values)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest["splits"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=settings.dataset_path)
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--group-field", default="participant_id")
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.output, args.seed, args.group_field)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
