"""Validate a human-authored CSV and convert it to the training JSONL format.

This utility transforms supplied records only; it does not generate training text.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path


REQUIRED_COLUMNS = ("participant_id", "instruction", "response", "source", "license")


def convert(source: Path, output: Path) -> dict[str, int]:
    if source.resolve() == output.resolve():
        raise ValueError("Input CSV and output JSONL must be different files.")
    counts = {"records": 0, "participants": 0}
    participants: set[str] = set()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with source.open("r", encoding="utf-8-sig", newline="") as input_stream:
        reader = csv.DictReader(input_stream)
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise ValueError("CSV column names must be unique.")
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        try:
            with temporary.open("w", encoding="utf-8") as output_stream:
                for line_number, raw in enumerate(reader, start=2):
                    if None in raw:
                        raise ValueError(f"CSV row {line_number} has more fields than the header.")
                    row = {key: " ".join((raw.get(key) or "").split()) for key in REQUIRED_COLUMNS}
                    blank = [key for key, value in row.items() if not value]
                    if blank:
                        raise ValueError(f"CSV row {line_number} has empty fields: {', '.join(blank)}")
                    if "@" in row["participant_id"]:
                        raise ValueError(f"CSV row {line_number}: use a pseudonymous participant_id, not an email.")
                    if len(row["instruction"]) > 12000 or len(row["response"]) > 12000:
                        raise ValueError(f"CSV row {line_number}: instruction/response exceeds 12,000 characters.")
                    output_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    participants.add(row["participant_id"])
                    counts["records"] += 1
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    counts["participants"] = len(participants)
    if not counts["records"]:
        temporary.unlink(missing_ok=True)
        raise ValueError("CSV contains no training records.")
    os.replace(temporary, output)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("training/data/raw.jsonl"))
    args = parser.parse_args()
    try:
        result = convert(args.csv_file, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
