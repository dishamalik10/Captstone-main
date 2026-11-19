"""Inspectable, qualitative outfit evidence derived from wardrobe fields."""
from __future__ import annotations

from typing import Any

NEUTRALS = {"black", "white", "off white", "grey", "gray", "dark grey", "light grey", "beige", "navy", "brown", "cream", "ivory"}
FAMILY = {
    "red": "red", "dark red": "red", "light red": "red", "pink": "red", "dark pink": "red", "light pink": "red",
    "orange": "orange", "dark yellow": "orange", "yellow": "yellow", "light yellow": "yellow",
    "green": "green", "dark green": "green", "light green": "green", "olive": "green",
    "teal": "bluegreen", "turquoise": "bluegreen", "mint": "bluegreen",
    "blue": "blue", "dark blue": "blue", "light blue": "blue", "navy": "blue",
    "purple": "purple", "dark purple": "purple", "light purple": "purple", "lilac": "purple",
}
WHEEL = ("red", "orange", "yellow", "green", "bluegreen", "blue", "purple")
WARM_FAMILIES = {"red", "orange", "yellow"}
COOL_FAMILIES = {"green", "bluegreen", "blue", "purple"}


def _color_read(items: list[dict[str, Any]]) -> dict[str, Any]:
    colors = [str(item.get("color_name") or "").strip().lower() for item in items]
    unknown = [color for color in colors if not color or color == "unknown"]
    chromatic = [FAMILY[color] for color in colors if color and color not in NEUTRALS and color in FAMILY]
    unclassified = [color for color in colors if color and color not in NEUTRALS and color not in FAMILY]
    unique = sorted(set(chromatic), key=lambda value: WHEEL.index(value))
    label = "unknown_or_unclassified_color" if unknown or unclassified else ""
    if not label:
        if not unique:
            label = "neutral_palette"
        elif len(unique) == 1:
            label = "single_hue_family"
        elif len(unique) == 2:
            distance = abs(WHEEL.index(unique[0]) - WHEEL.index(unique[1]))
            distance = min(distance, len(WHEEL) - distance)
            label = "complementary_high_contrast" if distance == 3 else "analogous" if distance == 1 else "two_family_palette"
        else:
            label = "multiple_hue_families"
    tone_families = set(chromatic)
    has_warm = bool(tone_families & WARM_FAMILIES)
    has_cool = bool(tone_families & COOL_FAMILIES)
    temperature_tones = (
        "warm_and_cool" if has_warm and has_cool else "warm" if has_warm else
        "cool" if has_cool else "neutral_or_unknown"
    )
    return {
        "palette_type": label,
        "temperature_tones": temperature_tones,
        "reported_colors": [item.get("color_name") for item in items],
        "note": "Descriptive color-family heuristic; labels are approximate and this is not a calibrated quality score.",
    }


def analyze_outfit(items: list[dict[str, Any]], occasion: str, temperature: float, condition: str) -> dict[str, Any]:
    count = max(1, len(items))
    patterns = [str(item["pattern"]) for item in items if item.get("pattern")]
    fabrics = [str(item["fabric"]) for item in items if item.get("fabric")]
    textures = [str(item["texture"]) for item in items if item.get("texture")]
    fits = [str(item["fit"]) for item in items if item.get("fit")]
    seasons = sorted({str(season).lower() for item in items for season in item.get("seasons", [])})
    occasion_tags = sorted({str(tag).lower() for item in items for tag in item.get("occasion_tags", [])})
    style_tags = sorted({str(tag).lower() for item in items for tag in item.get("style_tags", [])})
    outerwear = [item.get("subcategory") for item in items if item.get("category") == "Outerwear"]
    top = next((item for item in items if item.get("category") == "Top"), None)
    bottom = next((item for item in items if item.get("category") == "Bottom"), None)

    def fit_volume(item: dict[str, Any] | None) -> str | None:
        fit = str((item or {}).get("fit") or "").lower()
        if any(value in fit for value in ("oversized", "relaxed", "loose", "wide")):
            return "roomy"
        if any(value in fit for value in ("fitted", "slim", "skinny", "tailored")):
            return "fitted"
        return "regular_or_unclassified" if fit else None

    top_volume, bottom_volume = fit_volume(top), fit_volume(bottom)
    if top_volume == "roomy" and bottom_volume == "fitted":
        silhouette = "roomy_top_balanced_by_fitted_bottom"
    elif top_volume == "fitted" and bottom_volume == "roomy":
        silhouette = "fitted_top_balanced_by_roomy_bottom"
    elif top_volume and bottom_volume:
        silhouette = "recorded_top_bottom_fits_need_visual_context"
    else:
        silhouette = "fit_or_base_category_data_missing"
    known_count = sum(bool(item.get(key)) for item in items for key in ("pattern", "fabric", "texture", "fit", "style_tags", "occasion_tags", "seasons"))
    coverage = known_count / (count * 7)
    confidence = "moderate" if coverage >= 0.45 else "limited"
    missing = []
    for key, label in (("pattern", "pattern"), ("fabric", "fabric"), ("texture", "texture"), ("fit", "fit/silhouette"), ("occasion_tags", "occasion"), ("seasons", "season")):
        if not any(item.get(key) for item in items):
            missing.append(label)
    return {
        "palette": _color_read(items),
        "pattern": {"reported": patterns, "assessment": "one_known_pattern" if len(patterns) == 1 else "multiple_patterns_scale_unknown" if len(patterns) > 1 else "not_recorded"},
        "fabric_texture": {"fabrics": fabrics, "textures": textures, "assessment": "attributes_recorded" if fabrics or textures else "not_recorded"},
        "proportion": {"recorded_fit": fits, "top_fit_group": top_volume,
                       "bottom_fit_group": bottom_volume, "silhouette_assessment": silhouette,
                       "assessment": "partial_fit_metadata" if fits else "not_recorded"},
        "layering": {"selected_outerwear": outerwear, "temperature_c": temperature, "condition": condition, "assessment": "owned_outerwear_selected" if outerwear else "no_outerwear_selected"},
        "occasion": {"requested": occasion, "recorded_tags": occasion_tags, "style_tags": style_tags},
        "season_tags": seasons,
        "evidence_confidence": confidence,
        "confidence_note": "Confidence describes wardrobe metadata coverage only. The rank score is heuristic and uncalibrated; it is not a probability or human fashion rating.",
        "limitations": missing,
    }
