"""Garment size -> try-on mask shape (4.11, VQ8). CatVTON is unchanged; only its mask moves.

- Hem: from the garment's measured length (tops, dresses) or inseam (bottoms) scaled by
  the user's height; otherwise from words in the garment's name (crop top, kurta, shorts,
  midi, maxi...). Garments with neither keep today's mask.
- Width (only with AURA_TRYON_FIT_WIDEN=1, off by default): a garment with more ease than
  a regular cut widens the mask by the extra ease's radius on each side. In the first render
  check the extra width came out as a flat bar, not looser fabric, so it is not used yet.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

import numpy as np

from services import body_analysis as ba
from services import fit_advice
from services.body_measurements import _crotch
from settings import settings

# (pattern, anchor, fraction): hem = anchor row + fraction of the span to the next anchor.
_UPPER_WORDS = [
    (r"\bcrop", "torso", 0.62),
    (r"\b(kurta|kurti|tunic|longline)\b", "knee", 0.0),
    (r"\b(trench|overcoat|long coat|duster)\b", "calf", 0.2),
]
_LOWER_WORDS = [
    (r"\bshorts?\b", "thigh", 0.55),
    (r"\bmini\b", "thigh", 0.5),
    (r"\b(capri|culottes?|cropped)\b", "calf", 0.5),
    (r"\bmidi\b", "calf", 0.45),
    (r"\b(maxi|gown|anarkali)\b", "ankle", 0.0),
]
MAIN_ZONE = {"Top": "chest", "Outerwear": "chest", "Dress": "chest", "Bottom": "hip"}


def _rows(lm: np.ndarray) -> dict[str, float]:
    def mid(a: int, b: int) -> float:
        return float((lm[a, 1] + lm[b, 1]) / 2)
    return {"shoulder": mid(ba.L_SHOULDER, ba.R_SHOULDER), "hip": mid(ba.L_HIP, ba.R_HIP),
            "knee": mid(ba.L_KNEE, ba.R_KNEE), "ankle": mid(ba.L_ANKLE, ba.R_ANKLE)}


def _word_hem(name: str, category: str, at: dict[str, float]) -> float | None:
    words = _UPPER_WORDS if category in {"Top", "Outerwear"} else _LOWER_WORDS
    torso = at["hip"] - at["shoulder"]
    for pattern, anchor, fraction in words:
        if re.search(pattern, name, re.IGNORECASE):
            if anchor == "torso":
                return at["shoulder"] + torso * fraction
            if anchor == "thigh":
                return at["hip"] + (at["knee"] - at["hip"]) * fraction
            if anchor == "calf":
                return at["knee"] + (at["ankle"] - at["knee"]) * fraction
            return at[anchor]
    return None


def mask_fit(
    item: dict[str, Any], parsing: np.ndarray, lm: np.ndarray,
    height_cm: float | None, body: dict[str, dict[str, Any]], fit_preference: str | None = None,
) -> ba.MaskFit | None:
    """The mask adjustment for one wardrobe item, or None to keep the default mask."""
    category = item["category"]
    if category not in MAIN_ZONE:
        return None
    size = item.get("size") or {}
    measured = size.get("measurements") or {}
    at = _rows(lm)
    person = np.nonzero((parsing != ba.BACKGROUND).any(axis=1))[0]
    cm_per_px = height_cm / float(person.max() - person.min() + 1) if height_cm and person.size else None

    hem = None
    if cm_per_px and category in {"Top", "Outerwear", "Dress"} and measured.get("length_cm"):
        hem = at["shoulder"] + (float(measured["length_cm"]) - fit_advice.HPS_ABOVE_SHOULDER_CM) / cm_per_px
    elif cm_per_px and category == "Bottom" and measured.get("inseam_cm"):
        body_mask = np.isin(parsing, (ba.BODY_SKIN, ba.CLOTHES, ba.OTHER))
        centre_x = float(lm[[ba.L_HIP, ba.R_HIP], 0].mean())
        crotch = _crotch(body_mask, centre_x, at["hip"], at["knee"])
        if crotch is not None:
            hem = crotch + float(measured["inseam_cm"]) / cm_per_px
    if hem is None:
        hem = _word_hem(f"{item.get('subcategory') or ''} {item.get('name') or ''}", category, at)

    widen = 0
    zone = MAIN_ZONE[category]
    target = fit_advice.TARGET_EASE[category].get(zone, 0)
    garment, _basis, _ = fit_advice.garment_circumferences(category, size, item.get("fit"))
    body_cm = (body.get(zone) or {}).get("value")
    excess = 0.0
    if zone in garment and body_cm is not None:
        excess = garment[zone] - float(body_cm) - target
    else:
        excess = float(max(0, fit_advice._word(item.get("fit"), fit_advice.CUT_SHIFT)))
    if settings.tryon_fit_widen and cm_per_px and excess > 0:
        span = float(np.hypot(*(lm[ba.L_SHOULDER, :2] - lm[ba.R_SHOULDER, :2])))
        widen = int(min(span * 0.25, excess / (2 * math.pi) / cm_per_px))
    if hem is None and widen == 0:
        return None
    return ba.MaskFit(hem_y=hem, widen_px=widen)


def signature(items: list[dict[str, Any]], height_cm: float | None, body: dict[str, dict[str, Any]]) -> str | None:
    """A short hash of everything ``mask_fit`` reads, for the render cache key; None when
    no item has size information (so earlier cached renders stay valid)."""
    relevant = [
        {"id": item["item_id"], "size": item.get("size"), "fit": item.get("fit"), "name": item.get("subcategory")}
        for item in items
        if item.get("size") or any(re.search(p, item.get("subcategory") or "", re.IGNORECASE)
                                   for p, _, _ in _UPPER_WORDS + _LOWER_WORDS)
        or fit_advice._word(item.get("fit"), fit_advice.CUT_SHIFT) > 0
    ]
    if not relevant:
        return None
    data = json.dumps({"items": relevant, "height": height_cm,
                       "body": {k: (body.get(k) or {}).get("value") for k in ("chest", "hip")}}, sort_keys=True)
    return hashlib.sha1(data.encode()).hexdigest()[:12]
