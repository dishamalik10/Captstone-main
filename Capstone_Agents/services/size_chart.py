"""Generic size chart (4.11, VQ6): a garment's size label -> the body measurements it is made for.

This is a *generic* chart, not any brand's: real sizes vary by brand by a size or more,
so every piece of advice built on it says "estimated". Brand-specific charts come later.

Supported labels (case and spaces don't matter):
- Letters: XS, S, M, L, XL, XXL (also 2XL). Charts: women's, men's, or (unknown) the
  average of the two, called "unisex" here.
- Women's numeric: "US 8", "UK 12", "EU 40"; a bare number from 2 to 24 is read as UK
  (India uses UK sizes for women's clothing).
- Men's chest sizes: "EU 50" (suit/jacket: chest = 2 x the number in cm); a bare number
  from 34 to 50 on a top or outerwear piece is the chest in inches (India/US shirts).
- Waist/length for bottoms: "32/32", "W32 L30", "W32", or a bare 24-44 on a bottom.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

INCH = 2.54
LETTERS = ("XS", "S", "M", "L", "XL", "XXL")

# Body measurements (cm) each letter size is made for: (chest, waist, hip) mid-points.
# Typical of published high-street charts; each size spans about +-3 cm around them.
_WOMEN = {"XS": (81, 63, 89), "S": (86, 68, 94), "M": (91, 73, 99),
          "L": (97, 79, 105), "XL": (104, 86, 112), "XXL": (112, 94, 120)}
_MEN = {"XS": (85, 73, 87), "S": (91, 79, 93), "M": (97, 85, 99),
        "L": (103, 91, 105), "XL": (109, 97, 111), "XXL": (116, 104, 118)}
_UNISEX = {size: tuple((w + m) / 2 for w, m in zip(_WOMEN[size], _MEN[size])) for size in LETTERS}
LETTER_CHARTS = {"women": _WOMEN, "men": _MEN, "unisex": _UNISEX}
HALF_RANGE = 3.0  # cm either side of a letter size's mid-point
ZONES = ("chest", "waist", "hip")


@dataclass(frozen=True)
class SizeSpec:
    """The body a size is made for. ``body`` maps zone -> (low, high) cm."""
    label: str
    system: str            # e.g. "letter (unisex)", "UK women's", "waist/length"
    body: dict[str, tuple[float, float]] = field(default_factory=dict)
    inseam_cm: float | None = None


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().upper())


def _ranges(mids: tuple[float, ...], half: float = HALF_RANGE) -> dict[str, tuple[float, float]]:
    return {zone: (round(mid - half, 1), round(mid + half, 1)) for zone, mid in zip(ZONES, mids)}


def _women_uk(uk: float, label: str, system: str) -> SizeSpec | None:
    """UK women's 4-24: UK 12 ~ chest 91, waist 73, hip 99; about 2.5 cm per step of 2."""
    if not 2 <= uk <= 26:
        return None
    step = (uk - 12) / 2 * 2.5
    return SizeSpec(label, system, _ranges((91 + step, 73 + step, 99 + step), 2.5))


def parse(label: str | None, category: str | None = None, chart: str | None = None) -> SizeSpec | None:
    """The body measurements a size label is made for, or None when it isn't recognised
    (free text, "one size", a number that doesn't fit the category)."""
    if not label or not label.strip():
        return None
    text = _norm(label)
    chart = chart if chart in LETTER_CHARTS else "unisex"
    letter = {"2XL": "XXL", "XXS": None, "3XL": None}.get(text, text)
    if letter in LETTERS:
        return SizeSpec(label.strip(), f"letter ({chart})", _ranges(LETTER_CHARTS[chart][letter]))

    waist_length = re.fullmatch(r"W?\s*(\d{2})\s*(?:/|X|\s+L|\s*L)\s*(\d{2})", text)
    if waist_length:
        waist, inseam = int(waist_length.group(1)), int(waist_length.group(2))
        if 22 <= waist <= 50 and 24 <= inseam <= 38:
            mid = waist * INCH
            return SizeSpec(label.strip(), "waist/length", {"waist": (round(mid - 2, 1), round(mid + 2, 1))},
                            inseam_cm=round(inseam * INCH, 1))
    waist_only = re.fullmatch(r"W\s*(\d{2})", text)
    if waist_only and 22 <= int(waist_only.group(1)) <= 50:
        mid = int(waist_only.group(1)) * INCH
        return SizeSpec(label.strip(), "waist", {"waist": (round(mid - 2, 1), round(mid + 2, 1))})

    prefixed = re.fullmatch(r"(US|UK|IN|EU)\s*(\d{1,2})", text)
    if prefixed:
        system, number = prefixed.group(1), int(prefixed.group(2))
        if system == "US" and number <= 20:
            return _women_uk(number + 4, label.strip(), "US women's")
        if system in {"UK", "IN"} and number <= 26:
            return _women_uk(number, label.strip(), f"{system} women's")
        if system == "EU" and 30 <= number <= 50 and chart != "men":
            return _women_uk(number - 28, label.strip(), "EU women's")
        if system == "EU" and 42 <= number <= 64:
            mid = number * 2  # men's jacket/suit: half the chest in cm
            return SizeSpec(label.strip(), "EU men's", {"chest": (mid - 2, mid + 2)})
        if system in {"IN", "US"} and 34 <= number <= 50 and category in {"Top", "Outerwear"}:
            mid = number * INCH
            return SizeSpec(label.strip(), f"{system} chest (inches)", {"chest": (round(mid - 2, 1), round(mid + 2, 1))})
        return None

    if text.isdigit():
        number = int(text)
        if category == "Bottom" and 24 <= number <= 44:
            mid = number * INCH
            return SizeSpec(label.strip(), "waist (inches)", {"waist": (round(mid - 2, 1), round(mid + 2, 1))})
        if category in {"Top", "Outerwear"} and 34 <= number <= 50:
            mid = number * INCH
            return SizeSpec(label.strip(), "chest (inches)", {"chest": (round(mid - 2, 1), round(mid + 2, 1))})
        if 2 <= number <= 24 and number % 2 == 0:
            return _women_uk(number, label.strip(), "UK women's")
    return None


def body_from_size(label: str | None, category: str | None = None) -> dict[str, float]:
    """Mid-point body measurements for a size the user says they usually wear (VQ14 fallback)."""
    spec = parse(label, category)
    if spec is None:
        return {}
    values = {zone: round((low + high) / 2, 1) for zone, (low, high) in spec.body.items()}
    if spec.inseam_cm:
        values["inseam"] = spec.inseam_cm
    return values
