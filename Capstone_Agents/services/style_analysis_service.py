from __future__ import annotations

from collections import Counter
from typing import Any

from services.preference_service import get_preferences
from services.wardrobe_service import list_items


CATEGORY_TARGETS = {
    "Top": 4,
    "Bottom": 3,
    "Dress": 1,
    "Footwear": 2,
    "Outerwear": 1,
    "Accessory": 2,
}

BUY_IDEAS = {
    "Top": ("Versatile everyday top", "Choose a cut that works with at least two bottoms you own."),
    "Bottom": ("Versatile bottom", "A neutral trouser, jean, or skirt will create more complete outfits."),
    "Dress": ("One-piece outfit", "A versatile dress gives you a complete option for dates and events."),
    "Footwear": ("Everyday footwear", "One adaptable shoe can complete casual and smart-casual outfits."),
    "Outerwear": ("Layering piece", "A jacket, cardigan, or blazer adds structure and weather flexibility."),
    "Accessory": ("Finishing accessory", "A bag, belt, or jewellery piece can make existing outfits feel intentional."),
}

NEUTRALS = {"black", "white", "off white", "grey", "beige", "navy", "dark blue", "brown"}


def analyze_style(user_id: str) -> dict[str, Any]:
    items = list_items(user_id, available_only=True)
    preferences = get_preferences(user_id)
    category_counts = Counter(item["category"] for item in items)
    color_counts = Counter(item["color_name"] for item in items)
    tag_counts: Counter[str] = Counter()
    for item in items:
        tag_counts.update(str(tag).lower() for tag in item.get("style_tags", []))

    recommendations: list[dict[str, Any]] = []
    for category, target in CATEGORY_TARGETS.items():
        count = category_counts[category]
        if count >= target:
            continue
        title, reason = BUY_IDEAS[category]
        recommendations.append(
            {
                "category": category,
                "title": title,
                "reason": reason,
                "priority": "high" if count == 0 and category in {"Top", "Bottom", "Footwear"} else "medium",
                "owned": count,
                "suggestedMinimum": target,
            }
        )

    owned_colors = {color.lower() for color in color_counts}
    if items and owned_colors and owned_colors.issubset(NEUTRALS):
        recommendations.append(
            {
                "category": "Colour",
                "title": "One accent-colour piece",
                "reason": "Your wardrobe is mostly neutral. One preferred accent colour will add variety while remaining easy to match.",
                "priority": "medium",
                "owned": 0,
                "suggestedMinimum": 1,
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda value: (priority_order[value["priority"]], value["owned"]))
    dominant_colors = [
        {"name": name, "count": count}
        for name, count in color_counts.most_common(5)
    ]
    dominant_styles = [name for name, _ in tag_counts.most_common(5)]
    if not dominant_styles:
        dominant_styles = list(preferences.get("preferred_styles", []))[:5]

    coverage = round(
        100
        * sum(min(category_counts[category], target) for category, target in CATEGORY_TARGETS.items())
        / sum(CATEGORY_TARGETS.values())
    )
    return {
        "totalItems": len(items),
        "wardrobeCoverage": coverage,
        "categoryCounts": dict(category_counts),
        "dominantColors": dominant_colors,
        "dominantStyles": dominant_styles,
        "strengths": [
            f"{category}: {count} available"
            for category, count in category_counts.most_common(3)
        ],
        "recommendations": recommendations[:6],
        "disclaimer": "Buy only pieces that fit your budget, comfort, and real lifestyle. These are wardrobe gaps, not requirements.",
    }

