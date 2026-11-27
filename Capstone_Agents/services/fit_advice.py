"""Size advice (4.11, VQ7): how a garment is likely to fit, zone by zone.

Display only (VQ15): nothing here changes recommendation scores.

Each circumference zone is rated tight / snug / regular / relaxed / loose from the *ease*
(garment circumference minus body circumference) compared with the ease a regular fit of
that garment type normally has, shifted by the user's fit preference. Garment
circumferences come from the garment's own flat measurements (2 x the flat width) when
given; otherwise from the generic size chart (``size_chart``): a size is made for a body
range, so a regular garment of that size is assumed to have the target ease over the
range's mid-point. Lengths (top hem, inseam) are rated short / regular / long when the
garment's length is known.
"""
from __future__ import annotations

from typing import Any

from services import size_chart

# Ease (cm of circumference) a regular fit normally has over the body.
TARGET_EASE = {
    "Top": {"chest": 10, "waist": 10},
    "Outerwear": {"chest": 16, "waist": 16},
    "Dress": {"chest": 6, "waist": 6, "hip": 8},
    "Bottom": {"waist": 2, "hip": 6},
}
# A garment's own cut (the item's "fit" field) changes its circumference vs. a regular cut
# of the same size (size-chart path only; measured garments already include it).
CUT_SHIFT = {"slim": -5, "skinny": -6, "fitted": -4, "tailored": -3, "regular": 0,
             "relaxed": 8, "loose": 8, "boxy": 10, "oversized": 16, "baggy": 14, "wide": 10}
# The user's fit preference moves the ease they would call "regular".
PREFERENCE_SHIFT = {"slim": -4, "fitted": -4, "tailored": -2, "regular": 0,
                    "relaxed": 6, "loose": 6, "oversized": 10}
RATINGS = ("tight", "snug", "regular", "relaxed", "loose")
HPS_ABOVE_SHOULDER_CM = 4.0  # a top's length is measured from the high point of the shoulder


def _word(value: str | None, table: dict[str, int]) -> int:
    text = (value or "").lower()
    return next((shift for word, shift in table.items() if word in text), 0)


def rate(delta: float) -> str:
    """Ease minus target ease (cm) -> rating. Boundaries: < -8 tight, < -3 snug,
    <= 4 regular, <= 12 relaxed, else loose."""
    if delta < -8:
        return "tight"
    if delta < -3:
        return "snug"
    if delta <= 4:
        return "regular"
    if delta <= 12:
        return "relaxed"
    return "loose"


def _length_rating(difference: float, short: str = "short", long: str = "long") -> str:
    if difference < -4:
        return short
    if difference > 4:
        return long
    return "regular"


def garment_circumferences(category: str, size: dict[str, Any] | None, cut: str | None) -> tuple[dict[str, float], str | None, float | None]:
    """(zone -> garment circumference cm, basis, inseam cm) for a garment."""
    size = size or {}
    measured = size.get("measurements") or {}
    targets = TARGET_EASE.get(category, {})
    garment: dict[str, float] = {}
    for zone in targets:
        flat = measured.get(f"{zone}_flat_cm")
        if flat:
            garment[zone] = 2 * float(flat)
    inseam = measured.get("inseam_cm")
    if garment:
        return garment, "garment measurements", inseam
    spec = size_chart.parse(size.get("label"), category, size.get("chart"))
    if spec is None:
        return {}, None, inseam
    shift = _word(cut, CUT_SHIFT)
    for zone, (low, high) in spec.body.items():
        if zone in targets:
            garment[zone] = (low + high) / 2 + targets[zone] + shift
    return garment, f"generic size chart ({spec.system})", inseam or spec.inseam_cm


def advise(
    category: str,
    size: dict[str, Any] | None,
    body: dict[str, dict[str, Any]],
    *,
    cut: str | None = None,
    fit_preference: str | None = None,
    usual_sizes: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Size advice for one garment.

    ``body`` is the merged measurement view (zone -> {"value", "source"}), see
    ``body_measurements.merged``. ``usual_sizes`` ({"top": ..., "bottom": ...}) are the
    profile's usual sizes, used for zones without a measurement (VQ14)."""
    if category not in TARGET_EASE:
        return {"available": False, "reason": "Size advice covers tops, bottoms, dresses and outerwear."}
    garment, garment_basis, inseam = garment_circumferences(category, size, cut)
    if not garment and not inseam:
        return {"available": False, "reason": "Add a size label (for example M, UK 12 or 32/32) or the garment's measurements."}

    usual = usual_sizes or {}
    usual_label = usual.get("bottom") if category == "Bottom" else usual.get("top")
    fallback = size_chart.body_from_size(usual_label, category)
    preference = _word(fit_preference, PREFERENCE_SHIFT)
    zones, sources = [], set()
    for zone, garment_cm in garment.items():
        entry = body.get(zone) or {}
        body_cm = entry.get("value")
        source = entry.get("source")
        if body_cm is None and zone in fallback:
            body_cm, source = fallback[zone], "usual size"
        if body_cm is None:
            continue
        sources.add(source)
        ease = garment_cm - float(body_cm)
        delta = ease - (TARGET_EASE[category][zone] + preference)
        zones.append({"zone": zone, "rating": rate(delta), "body_cm": round(float(body_cm), 1),
                      "garment_cm": round(garment_cm, 1), "ease_cm": round(ease, 1)})

    lengths = []
    measured = (size or {}).get("measurements") or {}
    if category == "Bottom" and inseam:
        entry = body.get("inseam") or {}
        if entry.get("value") is not None:
            sources.add(entry.get("source"))
            difference = float(inseam) - float(entry["value"])
            lengths.append({"zone": "inseam", "rating": _length_rating(difference), "difference_cm": round(difference, 1)})
    if category in {"Top", "Outerwear", "Dress"} and measured.get("length_cm"):
        entry = body.get("torso") or {}
        if entry.get("value") is not None:
            sources.add(entry.get("source"))
            # Where the hem falls relative to the hip line (+ below, - above).
            difference = float(measured["length_cm"]) - HPS_ABOVE_SHOULDER_CM - float(entry["value"])
            rating = "cropped" if difference < -12 else _length_rating(difference)
            lengths.append({"zone": "length", "rating": rating, "difference_cm": round(difference, 1)})

    if not zones and not lengths:
        return {"available": False, "reason": "Add your measurements (or your usual sizes in your profile) to see size advice."}
    ratings = {zone["rating"] for zone in zones}
    if "tight" in ratings:
        verdict = "Likely too small"
    elif "loose" in ratings:
        verdict = "Likely too big"
    elif "snug" in ratings:
        verdict = "Should fit, on the snug side"
    elif "relaxed" in ratings:
        verdict = "Should fit, with room"
    elif zones:
        verdict = "Should fit well"
    else:
        verdict = "Length only"
    estimated = garment_basis is None or garment_basis.startswith("generic") or bool(sources & {"estimated", "usual size"})
    notes = []
    if garment_basis and garment_basis.startswith("generic"):
        notes.append("Based on a generic size chart; brands differ by up to a size.")
    if "estimated" in sources:
        notes.append("Uses measurements estimated from your photos.")
    if "usual size" in sources:
        notes.append("Uses your usual size from your profile, not your measurements.")
    return {
        "available": True,
        "verdict": verdict,
        "estimated": estimated,
        "zones": zones,
        "lengths": lengths,
        "garment_basis": garment_basis or "garment measurements",
        "notes": notes,
    }


LISTING_TO_WARDROBE = {"tops": "Top", "bottoms": "Bottom", "dresses": "Dress", "outerwear": "Outerwear",
                       "shoes": "Footwear", "accessories": "Accessory"}


def for_user(user_id: str, category: str, size: dict[str, Any] | None, cut: str | None = None) -> dict[str, Any]:
    """``advise`` with this user's measurements, usual sizes and fit preference. Only ever
    returned to ``user_id`` themselves (VQ10)."""
    import json

    from database import row
    from services import body_measurements

    user = row("SELECT profile_json FROM users WHERE user_id=?", (user_id,)) or {}
    profile = json.loads(user.get("profile_json") or "{}")
    preference = row("SELECT fit_preference FROM preferences WHERE user_id=?", (user_id,)) or {}
    return advise(
        category, size, body_measurements.merged(user_id), cut=cut,
        fit_preference=preference.get("fit_preference"),
        usual_sizes={"top": profile.get("topSize"), "bottom": profile.get("bottomSize")},
    )


def for_listing(user_id: str, product: dict[str, Any]) -> dict[str, Any]:
    """Advice for a marketplace listing, for the viewer. A listing made from a wardrobe
    item also uses that item's garment measurements (garment data, not body data)."""
    import json

    from database import row

    category = LISTING_TO_WARDROBE.get(product.get("category") or "", "")
    size: dict[str, Any] = {"label": product.get("size") or None}
    item = None
    if product.get("wardrobeItemId"):
        item = row("SELECT size_json, fit FROM clothing_items WHERE item_id=?", (product["wardrobeItemId"],))
    if item and item.get("size_json"):
        stored = json.loads(item["size_json"])
        size = {"label": size["label"] or stored.get("label"), "chart": stored.get("chart"),
                "measurements": stored.get("measurements")}
    return for_user(user_id, category, size, cut=(item or {}).get("fit"))
