"""Classify garments as Summer, Winter or all-season, and map live temperature to a season.

The CNN predicts garment type and colour but not season, so season is inferred
from the garment's type name, garment group, fabric, texture and style tags.
A season the user set explicitly always wins over the inferred one.
"""
from __future__ import annotations

import re
from typing import Any, Literal

ALL_SEASONS = ["Spring", "Summer", "Autumn", "Winter"]
SUMMER_ONLY = ["Summer"]
WINTER_ONLY = ["Winter"]

# Temperature bands (°C) used to pick which season's clothes to suggest.
# Hot starts just above 25 °C because /recommend uses 25 °C as its "no weather" placeholder.
HOT_FROM_C = 26.0
COLD_UNTIL_C = 16.0

TargetSeason = Literal["Summer", "Winter", "Mild"]

WINTER_TERMS = (
    "coat", "overcoat", "trench", "parka", "puffer", "down jacket", "down coat", "quilted", "padded",
    "sweater", "jumper", "pullover", "cardigan", "hoodie", "sweatshirt", "fleece",
    "wool", "woollen", "woolen", "cashmere", "merino", "angora", "mohair", "sherpa",
    "fur", "faux fur", "shearling", "thermal", "turtleneck", "polo neck", "knitwear",
    "chunky knit", "cable knit", "velvet", "corduroy", "tweed", "flannel", "boots",
    "boot", "beanie", "scarf", "gloves", "mittens", "earmuffs", "shawl", "poncho",
    "leg warmer", "tights", "jacket",
)
SUMMER_TERMS = (
    "shorts", "t-shirt", "tshirt", "tee", "tank", "vest top", "camisole",
    "cami", "sleeveless", "short sleeve", "crop top", "linen", "seersucker", "chiffon",
    "sundress", "sun dress", "swimwear", "swimsuit", "bikini", "swim", "sandals",
    "sandal", "flip flop", "flip-flop", "slides", "espadrilles", "espadrille",
    "sunglasses", "sun hat", "straw", "kaftan", "sarong", "romper", "playsuit",
    "mesh", "eyelet", "broderie",
)


def _text(item: dict[str, Any]) -> str:
    parts = [
        item.get("subcategory"), item.get("garment_group"), item.get("fabric"),
        item.get("texture"), item.get("name"), " ".join(item.get("style_tags") or []),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}s?\b", text) for term in terms)


def classify_seasons(item: dict[str, Any]) -> list[str]:
    """Infer seasons from the garment's own attributes: Summer, Winter, or all four."""
    text = _text(item)
    winter = _has(text, WINTER_TERMS)
    summer = _has(text, SUMMER_TERMS)
    if winter and not summer:
        return list(WINTER_ONLY)
    if summer and not winter:
        return list(SUMMER_ONLY)
    # Both (e.g. "linen blazer" vs "wool shorts") or neither: wearable most of the year.
    return list(ALL_SEASONS)


def effective_seasons(item: dict[str, Any]) -> list[str]:
    """The user's saved seasons if any, otherwise the inferred ones."""
    saved = [str(season).title() for season in item.get("seasons") or []]
    return saved or classify_seasons(item)


def season_label(seasons: list[str]) -> Literal["Summer", "Winter", "All-season"]:
    names = {season.lower() for season in seasons}
    if "summer" in names and "winter" not in names:
        return "Summer"
    if "winter" in names and "summer" not in names:
        return "Winter"
    return "All-season"


def target_season(temperature_c: float | None) -> TargetSeason:
    """Which season's clothes suit the current temperature."""
    if temperature_c is None:
        return "Mild"
    if temperature_c >= HOT_FROM_C:
        return "Summer"
    if temperature_c <= COLD_UNTIL_C:
        return "Winter"
    return "Mild"
