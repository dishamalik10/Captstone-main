from __future__ import annotations

from collections import Counter
from typing import Any

from services.wardrobe_service import list_items


NEUTRALS = {"black", "white", "off white", "grey", "beige", "navy", "dark blue", "brown"}


def analyze_purchase_impact(
    user_id: str,
    prediction: dict[str, Any],
) -> dict[str, Any]:
    wardrobe = list_items(user_id, available_only=True)
    category = prediction["category"]
    product_type = prediction["product_type"]["label"]
    color = prediction["color_group"]["label"]
    counts = Counter(item["category"] for item in wardrobe)

    similar = [
        item for item in wardrobe
        if item["category"] == category
        and (
            item["subcategory"].lower() == product_type.lower()
            or item["color_name"].lower() == color.lower()
        )
    ]
    exact_like = [
        item for item in similar
        if item["subcategory"].lower() == product_type.lower()
        and item["color_name"].lower() == color.lower()
    ]

    tops, bottoms = counts["Top"], counts["Bottom"]
    dresses, footwear = counts["Dress"], counts["Footwear"]
    complete_bases = dresses + tops * bottoms
    if category == "Top":
        new_outfits = bottoms * max(1, footwear)
    elif category == "Bottom":
        new_outfits = tops * max(1, footwear)
    elif category == "Dress":
        new_outfits = max(1, footwear)
    elif category == "Footwear":
        new_outfits = complete_bases
    else:
        new_outfits = complete_bases

    novelty = 5 if exact_like else 18 if similar else 35
    outfit_impact = min(40, new_outfits * 7)
    gap_value = 25 if counts[category] == 0 else max(5, 20 - counts[category] * 4)
    versatility = 10 if color.lower() in NEUTRALS else 5
    score = min(100, novelty + outfit_impact + gap_value + versatility)

    if exact_like:
        verdict = "Probably skip"
        headline = "Very similar to something you own"
    elif score >= 70:
        verdict = "Strong addition"
        headline = "Adds useful outfit possibilities"
    elif score >= 48:
        verdict = "Consider"
        headline = "Useful if it fits your lifestyle"
    else:
        verdict = "Low wardrobe impact"
        headline = "May not unlock many new outfits"

    reasons = [
        f"Could create about {new_outfits} combinations with your current wardrobe.",
        f"You currently own {counts[category]} item(s) in {category.lower()}.",
    ]
    if similar:
        reasons.append(f"{len(similar)} similar item(s) already exist in your wardrobe.")
    if color.lower() in NEUTRALS:
        reasons.append(f"{color} is versatile with many wardrobe colours.")

    return {
        "detectedItem": {
            "category": category,
            "productType": product_type,
            "color": color,
            "confidence": round(float(prediction["product_type"]["confidence"]) * 100),
        },
        "purchaseScore": score,
        "verdict": verdict,
        "headline": headline,
        "newOutfits": new_outfits,
        "similarItems": [
            {
                "id": item["item_id"],
                "name": item["subcategory"],
                "color": item["color_name"],
                "imageUrl": item["image_url"],
            }
            for item in similar[:4]
        ],
        "reasons": reasons,
        "disclaimer": "This score measures wardrobe usefulness, not price, quality, fit, ethics, or whether you personally love the item.",
    }

