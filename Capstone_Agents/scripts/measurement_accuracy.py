"""Volunteer tape-measure check for photo measurements (ENGINEERING_PLAN 4.11, VQ11).

Protocol: training/MEASUREMENT_ACCURACY_PROTOCOL.md. Fill a CSV with one row per
volunteer and zone (no names: use V1, V2, ...):

    volunteer,zone,tape_cm,app_cm
    V1,chest,94,97.2

then run

    python -m scripts.measurement_accuracy results.csv

A zone passes when its mean absolute error is at most 4 cm AND at least 80% of its
volunteers are within +-4 cm, with at least 5 volunteers. The summary is written to
training/measurement_accuracy_results.json; the app reads it and shows passing zones as
a single number. Zones that fail (or are missing) keep being shown only as a range.
Delete the CSV afterwards: it is body data.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.body_measurements import ACCURACY_RESULTS, ZONES  # noqa: E402

TARGET_CM = 4.0
MIN_SHARE_WITHIN = 0.8
MIN_VOLUNTEERS = 5


def summarise(rows: list[dict[str, str]]) -> dict:
    by_zone: dict[str, list[float]] = {}
    for line in rows:
        zone = line["zone"].strip().lower()
        if zone not in ZONES:
            raise ValueError(f"Unknown zone {zone!r}; use one of {', '.join(ZONES)}.")
        by_zone.setdefault(zone, []).append(float(line["app_cm"]) - float(line["tape_cm"]))
    zones = {}
    for zone, errors in sorted(by_zone.items()):
        absolute = [abs(e) for e in errors]
        mae = sum(absolute) / len(absolute)
        within = sum(a <= TARGET_CM for a in absolute) / len(absolute)
        zones[zone] = {
            "volunteers": len(errors),
            "mean_abs_error_cm": round(mae, 2),
            "mean_signed_error_cm": round(sum(errors) / len(errors), 2),  # + means the app reads high
            "share_within_4cm": round(within, 2),
            "pass": len(errors) >= MIN_VOLUNTEERS and mae <= TARGET_CM and within >= MIN_SHARE_WITHIN,
        }
    return {"checked_on": date.today().isoformat(), "target_cm": TARGET_CM,
            "rule": f"MAE <= {TARGET_CM} cm and >= {int(MIN_SHARE_WITHIN * 100)}% within, >= {MIN_VOLUNTEERS} volunteers",
            "zones": zones}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print the summary without writing it")
    args = parser.parse_args()
    with args.csv.open(newline="") as handle:
        summary = summarise(list(csv.DictReader(handle)))
    print(json.dumps(summary, indent=2))
    if not args.dry_run:
        ACCURACY_RESULTS.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"Written to {ACCURACY_RESULTS.relative_to(ROOT)}. Restart is not needed.")


if __name__ == "__main__":
    main()
