"""Body measurements in cm (4.11, VQ2-VQ5, VQ10, VQ11, VQ13).

Estimate: the front avatar gives widths, a side photo gives depths, both measured on the
MediaPipe body outline (no new model). Each photo is scaled by the user's height (the
person's outline, head to feet, is their height). Chest, waist and hip circumferences
treat each width/depth pair as an ellipse (Ramanujan's perimeter approximation).

Rules:
- Height is required (it is the scale).
- Photos that fail the checks raise ``BodyPhotoError``; soft problems (loose clothing,
  arms against the body, low landmark confidence) mean *no estimate*: the user enters
  their own values instead.
- Values the user types always win over estimates; each value says where it came from.
- The side photo is never stored: it is read, measured and dropped. Only numbers are kept.
- Until the volunteer accuracy check (scripts/measurement_accuracy.py) shows a zone is
  within +-4 cm, that zone's estimate is shown only as a range.
- Measurements are body data (4.3): deleted with "Delete my body data" and with the
  account, never logged, never shown to other users.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from database import connection, row, utc_now
from services import body_analysis as ba

ZONES = ("chest", "waist", "hip", "shoulder", "inseam", "arm", "torso")
CIRCUMFERENCES = ("chest", "waist", "hip")
LABELS = {"chest": "Chest", "waist": "Waist", "hip": "Hip", "shoulder": "Shoulder width",
          "inseam": "Inseam", "arm": "Arm length", "torso": "Shoulder to hip"}
# Plausible adult ranges (cm); an estimate outside them is dropped, a typed value refused.
BOUNDS = {"chest": (60, 170), "waist": (45, 170), "hip": (60, 180), "shoulder": (25, 65),
          "inseam": (50, 100), "arm": (40, 85), "torso": (30, 75), "height": (120, 230)}
# Range shown around an unvalidated estimate (fraction of the value).
RANGE_FRACTION = {"chest": 0.05, "waist": 0.05, "hip": 0.05, "shoulder": 0.05,
                  "inseam": 0.04, "arm": 0.04, "torso": 0.05}
ROOT = Path(__file__).resolve().parents[1]
ACCURACY_RESULTS = ROOT / "training" / "measurement_accuracy_results.json"
METHOD = ("Estimated from your front and side photos, scaled by your height: widths and depths of "
          "your outline, with chest, waist and hip treated as ellipses. Not a tape measurement.")


class MeasurementError(ValueError):
    """Shown to the user as is."""


# -- geometry -------------------------------------------------------------------------

def ellipse_circumference(width: float, depth: float) -> float:
    """Ramanujan's approximation of an ellipse's perimeter from its two diameters."""
    a, b = width / 2, depth / 2
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


@dataclass
class Outline:
    """Pixel geometry of one photo."""
    top: int
    bottom: int
    shoulder_y: float
    hip_y: float
    centre_x: float
    widths: dict[str, float]   # chest / waist / hip run widths (px)
    shoulder_w: float = 0.0
    crotch_y: float | None = None
    arm_px: float | None = None

    @property
    def height_px(self) -> float:
        return float(self.bottom - self.top + 1)


def _rows(start: float, end: float, limit: int) -> range:
    return range(max(0, int(start)), min(limit, int(end)) + 1)


def outline(parsing: np.ndarray, lm: np.ndarray, *, side: bool = False) -> Outline:
    """Chest/waist/hip widths (front) or depths (side) of the body outline, in pixels."""
    person = parsing != ba.BACKGROUND
    ys = np.nonzero(person.any(axis=1))[0]
    if ys.size == 0:
        raise MeasurementError("No body outline was found in the photo.")
    body = np.isin(parsing, (ba.BODY_SKIN, ba.CLOTHES, ba.OTHER))
    shoulder_y = float((lm[ba.L_SHOULDER, 1] + lm[ba.R_SHOULDER, 1]) / 2)
    hip_y = float((lm[ba.L_HIP, 1] + lm[ba.R_HIP, 1]) / 2)
    torso = max(1.0, hip_y - shoulder_y)
    centre_x = float((lm[ba.L_SHOULDER, 0] + lm[ba.R_SHOULDER, 0] + lm[ba.L_HIP, 0] + lm[ba.R_HIP, 0]) / 4)
    span = float(np.hypot(*(lm[ba.L_SHOULDER, :2] - lm[ba.R_SHOULDER, :2])))
    # Front: arms erased so they don't count as torso width. Side: arms hang inside the depth.
    trunk = body if side else ba._remove_arms(body, lm, max(span, torso * 0.4))
    height = parsing.shape[0]

    def widths(start: float, end: float) -> list[int]:
        return [w for w in (ba._row_width(trunk, y, centre_x) for y in _rows(start, end, height - 1)) if w > 0]

    chest = widths(shoulder_y + torso * 0.20, shoulder_y + torso * 0.32)
    waist = widths(shoulder_y + torso * 0.45, shoulder_y + torso * 0.85)
    hip = widths(hip_y - torso * 0.05, hip_y + torso * 0.30)
    if not (chest and waist and hip):
        raise MeasurementError("Your outline could not be measured. Use a plain background and good light.")
    result = Outline(
        top=int(ys.min()), bottom=int(ys.max()), shoulder_y=shoulder_y, hip_y=hip_y, centre_x=centre_x,
        widths={
            # Side depths: the chest and seat are the deepest rows, the waist a typical one.
            "chest": float(np.percentile(chest, 90 if side else 50)),
            "waist": float(np.percentile(waist, 50 if side else 10)),
            "hip": float(np.percentile(hip, 90)),
        },
    )
    if not side:
        result.shoulder_w = float(ba._row_width(body, int(shoulder_y + torso * 0.06), centre_x))
        result.crotch_y = _crotch(body, centre_x, hip_y, float((lm[ba.L_KNEE, 1] + lm[ba.R_KNEE, 1]) / 2))
        arm = [float(np.hypot(*(lm[a, :2] - lm[b, :2]))) for a, b in
               ((ba.L_SHOULDER, ba.L_ELBOW), (ba.L_ELBOW, ba.L_WRIST),
                (ba.R_SHOULDER, ba.R_ELBOW), (ba.R_ELBOW, ba.R_WRIST))]
        if ba._visible(lm, ba.L_ELBOW, ba.L_WRIST, ba.R_ELBOW, ba.R_WRIST, threshold=0.5):
            result.arm_px = (arm[0] + arm[1] + arm[2] + arm[3]) / 2
    return result


def _crotch(body: np.ndarray, centre_x: float, hip_y: float, knee_y: float) -> float | None:
    """First row below the hips where the gap between the legs starts (3 empty rows in a row)."""
    cx = int(round(centre_x))
    if not 0 <= cx < body.shape[1]:
        return None
    empty = 0
    for y in _rows(hip_y, knee_y, body.shape[0] - 1):
        empty = empty + 1 if not body[y, max(0, cx - 1):cx + 2].any() else 0
        if empty == 3:
            return float(y - 2)
    return None


def estimate(front: Outline, side: Outline, height_cm: float) -> dict[str, float]:
    """Measurements (cm) from a front and a side outline scaled by height. Values outside
    plausible ranges are left out."""
    f_scale = height_cm / front.height_px
    s_scale = height_cm / side.height_px
    values: dict[str, float] = {}
    for zone in CIRCUMFERENCES:
        values[zone] = ellipse_circumference(front.widths[zone] * f_scale, side.widths[zone] * s_scale)
    values["shoulder"] = front.shoulder_w * f_scale
    values["torso"] = (front.hip_y - front.shoulder_y) * f_scale
    if front.crotch_y is not None:
        values["inseam"] = (front.bottom - front.crotch_y) * f_scale
    if front.arm_px:
        values["arm"] = front.arm_px * f_scale
    return {zone: round(value, 1) for zone, value in values.items()
            if BOUNDS[zone][0] <= value <= BOUNDS[zone][1]}


# -- photo checks -----------------------------------------------------------------------

def side_photo(photo: Image.Image) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Parse and check a side photo. Returns (parsing, landmarks, soft problems)."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    photo.thumbnail((1600, 1600), Image.LANCZOS)
    parsed = ba.parse_photo(photo)
    lm = parsed.landmarks
    width, height = parsed.image.size
    if height < ba.MIN_PHOTO_HEIGHT:
        raise ba.BodyPhotoError(f"The photo is too small ({width}x{height}). Use one at least {ba.MIN_PHOTO_HEIGHT}px tall.")
    if not (ba._visible(lm, ba.L_SHOULDER, ba.L_HIP) or ba._visible(lm, ba.R_SHOULDER, ba.R_HIP)):
        raise ba.BodyPhotoError("Your shoulder and hip need to be visible. Stand side-on, full body in frame.")
    if not (ba._visible(lm, ba.L_ANKLE, threshold=0.35) or ba._visible(lm, ba.R_ANKLE, threshold=0.35)):
        raise ba.BodyPhotoError("Your feet are cut off. Use a full-body photo from head to feet.")
    torso = abs((lm[ba.L_HIP, 1] + lm[ba.R_HIP, 1]) / 2 - (lm[ba.L_SHOULDER, 1] + lm[ba.R_SHOULDER, 1]) / 2)
    if torso and abs(lm[ba.L_SHOULDER, 0] - lm[ba.R_SHOULDER, 0]) / torso > 0.35:
        raise ba.BodyPhotoError("This looks like a front photo. Turn sideways (left or right side to the camera).")
    parsing = ba.keep_person_only(parsed.parsing)
    if (parsing != ba.BACKGROUND).mean() < 0.04:
        raise ba.BodyPhotoError("You are too small in the photo. Stand closer so your body fills most of the frame.")
    return parsing, lm, _soft_problems(parsing, lm, [])


def _soft_problems(parsing: np.ndarray, lm: np.ndarray, warnings: list[str]) -> list[str]:
    problems = list(warnings)
    body = np.isin(parsing, (ba.BODY_SKIN, ba.CLOTHES, ba.OTHER))
    if float((parsing == ba.CLOTHES).sum() / max(1, body.sum())) > 0.85:
        problems.append("Loose or layered clothing hides your outline. Wear fitted clothing.")
    return problems


def front_photo(avatar: Image.Image) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Re-read the stored front avatar (its body map is not stored, 4.3) and check it."""
    parsed = ba.parse_photo(avatar)
    warnings = ba.validate(parsed)
    parsing = ba.keep_person_only(parsed.parsing)
    lm = parsed.landmarks
    if min(lm[i, 2] for i in (ba.L_SHOULDER, ba.R_SHOULDER, ba.L_HIP, ba.R_HIP)) < 0.8:
        warnings = warnings + ["Your shoulders and hips were hard to find in the front photo."]
    return parsing, lm, _soft_problems(parsing, lm, warnings)


# -- storage --------------------------------------------------------------------------

def validated_zones() -> set[str]:
    """Zones whose estimates met +-4 cm in the volunteer check (training/measurement_accuracy_results.json)."""
    try:
        results = json.loads(ACCURACY_RESULTS.read_text())
    except (OSError, ValueError):
        return set()
    return {zone for zone, result in (results.get("zones") or {}).items() if isinstance(result, dict) and result.get("pass")}


def _record(user_id: str) -> dict[str, Any]:
    record = row("SELECT * FROM body_measurements WHERE user_id=?", (user_id,))
    if record is None:
        return {"estimate": {}, "manual": {}, "meta": {}}
    return {"estimate": json.loads(record["estimate_json"]), "manual": json.loads(record["manual_json"]),
            "meta": json.loads(record["meta_json"])}


def _save(user_id: str, *, estimate: dict | None = None, manual: dict | None = None, meta: dict | None = None) -> None:
    current = _record(user_id)
    with connection() as db:
        db.execute(
            """INSERT INTO body_measurements(user_id, estimate_json, manual_json, meta_json, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET estimate_json=excluded.estimate_json,
                 manual_json=excluded.manual_json, meta_json=excluded.meta_json, updated_at=excluded.updated_at""",
            (user_id, json.dumps(current["estimate"] if estimate is None else estimate),
             json.dumps(current["manual"] if manual is None else manual),
             json.dumps(current["meta"] if meta is None else meta), utc_now()),
        )


def merged(user_id: str) -> dict[str, dict[str, Any]]:
    """zone -> {"value", "source": "you" | "estimated", "low", "high", "range_only"}.
    Typed values always win."""
    record = _record(user_id)
    validated = validated_zones()
    view: dict[str, dict[str, Any]] = {}
    for zone in ZONES:
        if record["manual"].get(zone) is not None:
            view[zone] = {"value": record["manual"][zone], "source": "you"}
        elif record["estimate"].get(zone) is not None:
            value = record["estimate"][zone]
            spread = value * RANGE_FRACTION[zone]
            view[zone] = {"value": value, "source": "estimated", "low": round(value - spread),
                          "high": round(value + spread), "range_only": zone not in validated}
    return view


def public(user_id: str, height_cm: float | None) -> dict[str, Any]:
    record = _record(user_id)
    return {
        "height_cm": height_cm,
        "measurements": merged(user_id),
        "labels": LABELS,
        "estimate": record["meta"].get("estimate"),  # {"at", "height_cm", "problems", "status"}
        "method": METHOD,
    }


def set_manual(user_id: str, values: dict[str, float | None]) -> None:
    """Typed values; None clears a typed value (the estimate shows again)."""
    manual = dict(_record(user_id)["manual"])
    for zone, value in values.items():
        if zone not in ZONES:
            continue
        if value is None:
            manual.pop(zone, None)
            continue
        low, high = BOUNDS[zone]
        if not low <= float(value) <= high:
            raise MeasurementError(f"{LABELS[zone]} must be between {low} and {high} cm.")
        manual[zone] = round(float(value), 1)
    _save(user_id, manual=manual)


def estimate_from_photos(user_id: str, avatar: Image.Image, side: Image.Image, height_cm: float) -> dict[str, Any]:
    """Measure the front avatar and a side photo. The side photo is only held in memory."""
    low, high = BOUNDS["height"]
    if not low <= height_cm <= high:
        raise MeasurementError(f"Height must be between {low} and {high} cm.")
    f_parsing, f_lm, f_problems = front_photo(avatar)
    s_parsing, s_lm, s_problems = side_photo(side)
    del side
    problems = f_problems + s_problems
    meta = {"at": utc_now(), "height_cm": height_cm, "problems": problems}
    if problems:
        # Low confidence: no estimate (VQ5). Earlier estimates are cleared so stale numbers aren't shown.
        _save(user_id, estimate={}, meta={"estimate": {**meta, "status": "not_estimated"}})
        return {"status": "not_estimated", "problems": problems}
    values = estimate(outline(f_parsing, f_lm), outline(s_parsing, s_lm, side=True), height_cm)
    if not all(zone in values for zone in CIRCUMFERENCES):
        _save(user_id, estimate={}, meta={"estimate": {**meta, "status": "not_estimated",
                                                        "problems": ["The measurements came out implausible. Retake the photos."]}})
        return {"status": "not_estimated", "problems": ["The measurements came out implausible. Retake the photos."]}
    _save(user_id, estimate=values, meta={"estimate": {**meta, "status": "estimated"}})
    return {"status": "estimated", "problems": []}


def delete(user_id: str) -> None:
    with connection() as db:
        db.execute("DELETE FROM body_measurements WHERE user_id=?", (user_id,))
