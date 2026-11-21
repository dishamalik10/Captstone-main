"""Explain server-ranked, owned outfits with local generation and safe rule fallback."""
from __future__ import annotations

import json
import re
from typing import Any

from services.fashion_knowledge import retrieve_guidance
from services.fashion_analysis import analyze_outfit
from services.local_llm import LocalModelError, generate_response, get_model_info
from services.aura_fashion_lm import explain_outfit, model_info as fashion_lm_info
from services.fashion_contract import InvalidFashionResponse

GARMENT_TERMS = {
    "shirt", "shirts", "tee", "t-shirt", "tshirts", "blouse", "top", "tops",
    "trouser", "trousers", "pants", "jeans", "shorts", "skirt", "skirts",
    "dress", "dresses", "jacket", "jackets", "coat", "coats", "blazer", "blazers",
    "sweater", "sweaters", "jumper", "hoodie", "hoodies", "cardigan", "cardigans",
    "shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "heel", "heels",
    "sandal", "sandals", "loafer", "loafers", "accessory", "accessories", "scarf",
    "scarves", "bag", "bags", "belt", "belts", "hat", "hats", "cap", "caps",
    "garment", "garments", "clothing", "outfit", "outfits",
    "bottom", "bottoms", "footwear", "look", "looks",
    "vest", "waistcoat", "leggings", "tights", "chinos", "suit", "suits",
    "kimono", "jumpsuit", "romper", "necklace", "jewelry", "earrings", "bracelet",
    "watch", "sunglasses", "tie", "necktie", "gloves", "mittens", "socks",
    "pocket square", "tuxedo", "polo", "tank top", "crop top", "suspenders",
    "raincoat", "windbreaker", "trench", "puffer", "tights", "underwear",
}
FABRIC_TERMS = {"cotton", "wool", "silk", "linen", "leather", "denim", "polyester", "cashmere", "suede", "velvet"}
PATTERN_TERMS = {"floral", "striped", "stripe", "plaid", "checkered", "checked", "printed", "print", "polka"}
FIT_TERMS = {"fit", "fitted", "comfortable", "comfort", "relaxed", "oversized", "slim", "tailored"}
UNSUPPORTED_STYLE_CLAIMS = {
    "classic", "versatile", "professional", "polished", "comfortable", "suitable",
    "appropriate", "perfect", "ideal", "effortless", "elegant", "trendy",
    "fashionable", "stylish", "practical", "breathable", "lightweight", "warm",
}
COLOR_TERMS = {
    "black", "white", "grey", "gray", "red", "blue", "green", "yellow", "brown",
    "beige", "pink", "purple", "orange", "navy", "gold", "cream", "ivory", "olive",
    "teal", "turquoise", "mint", "lilac",
}


def _has_unlisted_garment(explanation: str, items: list[dict[str, Any]]) -> bool:
    allowed_text = " ".join(
        f"{item.get('category', '')} {item.get('subcategory', '')} {item.get('garment_group', '')}"
        for item in items
    ).lower()
    allowed = {term for term in GARMENT_TERMS if re.search(rf"\b{re.escape(term)}\b", allowed_text)}
    allowed.update({"garment", "garments", "clothing", "outfit", "outfits", "look", "looks"})
    if any(item.get("category") == "Footwear" for item in items):
        allowed.update({"shoe", "shoes", "footwear"})
    mentioned = {term for term in GARMENT_TERMS if re.search(rf"\b{re.escape(term)}\b", explanation.lower())}
    return not mentioned.issubset(allowed)


def _has_unverified_claim(
    explanation: str, items: list[dict[str, Any]], *, temperature: float, condition: str,
) -> bool:
    text = explanation.lower()
    recorded_tags = {
        str(tag).lower() for item in items
        for tag in (item.get("style_tags") or []) + (item.get("occasion_tags") or [])
    }
    recorded_colors = {
        word for item in items
        for word in re.findall(r"[a-z]+", str(item.get("color_name") or "").lower())
    }
    if any(re.search(rf"\b{re.escape(color)}\b", text) and color not in recorded_colors for color in COLOR_TERMS):
        return True
    if any(re.search(rf"\b{re.escape(term)}\b", text) and term not in recorded_tags for term in UNSUPPORTED_STYLE_CLAIMS):
        return True
    for field, terms in (("fabric", FABRIC_TERMS), ("pattern", PATTERN_TERMS), ("fit", FIT_TERMS)):
        recorded = {
            word for item in items
            for word in re.findall(r"[a-z]+", str(item.get(field) or "").lower())
        }
        if any(
            re.search(rf"\b{re.escape(term)}\b", text)
            and not set(re.findall(r"[a-z]+", term)).issubset(recorded)
            for term in terms
        ):
            return True
    weather_terms = {"sunny", "rain", "rainy", "snow", "snowy", "windy", "wind", "humid", "hot", "warm", "cold", "chilly"}
    supported_weather = set(re.findall(r"[a-z]+", condition.lower()))
    if temperature >= 30:
        supported_weather.update({"hot", "warm"})
    elif temperature <= 15:
        supported_weather.update({"cold", "chilly"})
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in weather_terms - supported_weather):
        return True
    return False


def _rule_comparison(recommendations: list[dict[str, Any]]) -> str:
    if len(recommendations) < 2:
        return "Only one distinct complete combination was available, so there is no alternative comparison."
    first, second = recommendations[:2]
    first_scores, second_scores = first.get("component_scores", {}), second.get("component_scores", {})
    differences = [
        (abs(float(first_scores.get(key, 50)) - float(second_scores.get(key, 50))), key,
         float(first_scores.get(key, 50)), float(second_scores.get(key, 50)))
        for key in ("color", "occasion", "weather", "preference", "feedback", "learned_preference", "novelty")
    ]
    differences.sort(reverse=True)
    if not differences or differences[0][0] == 0:
        return "The top options are tied on the reported rule signals; their order may be unstable. Check the garments and any missing details yourself."
    _, driver, first_value, second_value = differences[0]
    labels = {
        "color": "palette", "occasion": "occasion fit", "weather": "weather rule",
        "preference": "saved preferences", "feedback": "direct feedback",
        "learned_preference": "learned preference signals", "novelty": "recent-wear variety",
    }
    leader = "first" if first_value >= second_value else "second"
    return (f"The {leader}-ranked option leads on {labels[driver]} in the current rule signals. "
            "That is a ranking explanation, not a calibrated fashion-quality judgment; garment details may be missing.")


def _rule_outfit_note(rec: dict[str, Any]) -> str:
    items = rec.get("items", [])
    colors = list(dict.fromkeys(str(item.get("color_name") or "unknown") for item in items))
    palette = rec.get("analysis", {}).get("palette", {}).get("palette_type", "unknown_or_unclassified_color")
    tones = rec.get("analysis", {}).get("palette", {}).get("temperature_tones", "neutral_or_unknown")
    silhouette = rec.get("analysis", {}).get("proportion", {}).get("silhouette_assessment")
    palette_text = {
        "neutral_palette": "a neutral palette",
        "single_hue_family": "one recorded hue family",
        "complementary_high_contrast": "a high contrast between recorded hue families",
        "analogous": "neighboring recorded hue families",
        "two_family_palette": "two recorded hue families",
        "multiple_hue_families": "several recorded hue families",
    }.get(palette, "an incomplete or unclassified palette")
    colors_text = ", ".join(colors)
    tone_note = " The recorded palette mixes warm and cool hue families." if tones == "warm_and_cool" else ""
    silhouette_notes = {
        "roomy_top_balanced_by_fitted_bottom": " Recorded fit labels pair a roomy top with a fitted bottom, balancing the silhouette.",
        "fitted_top_balanced_by_roomy_bottom": " Recorded fit labels pair a fitted top with a roomy bottom, balancing the silhouette.",
        "recorded_top_bottom_fits_need_visual_context": " Fit labels are recorded for both pieces; their visual proportions still need a person to assess.",
    }
    silhouette_note = silhouette_notes.get(silhouette, "")
    missing = rec.get("analysis", {}).get("limitations", [])
    limits = " Fit, fabric, and pattern details are missing." if any(value in missing for value in ("fit/silhouette", "fabric", "pattern")) else ""
    if palette == "multiple_hue_families":
        return (f"This uses several recorded color families ({colors_text}), which may read as visually busy. "
                f"For a calmer effect, make one of these colors the focal point.{tone_note}{silhouette_note}{limits}")
    if palette == "complementary_high_contrast":
        return (f"{colors_text} create a high-contrast color pairing. Keep the rest of the palette quiet if you want "
                f"that contrast to stand out.{tone_note}{silhouette_note}{limits}")
    return f"Use {colors_text} as the outfit's main color palette ({palette_text}).{tone_note}{silhouette_note}{limits}"


def explain_recommendations(
    recommendations: list[dict[str, Any]], *, occasion: str, temperature: float,
    condition: str, wardrobe: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
    allow_llm: bool = True,
) -> dict[str, Any]:
    """Explain server-ranked outfits; language models cannot choose or edit items.

    Outfits already explained by the stylist LLM keep that explanation. Pass
    ``allow_llm=False`` to skip a second LLM call when the stylist already ran.
    """
    if not recommendations:
        return {"recommendations": [], "comparison_explanation": "", "comparison_source": "rules",
                "evidence_confidence": "limited", "confidence_note": "No outfit evidence was available."}
    prepared = []
    for rank, rec in enumerate(recommendations, start=1):
        stylist_text = rec.get("explanation") if rec.get("explanation_source") == "stylist_llm" else None
        rec = {**rec, "analysis": analyze_outfit(rec.get("items", []), occasion, temperature, condition),
               "explanation_source": "rules"}
        rec["explanation"] = _rule_outfit_note(rec)
        if stylist_text:
            rec["explanation"] = stylist_text
            rec["explanation_source"] = "stylist_llm"
        prepared.append(rec)
    evidence_level = "moderate" if all(rec["analysis"]["evidence_confidence"] == "moderate" for rec in prepared[:2]) else "limited"
    confidence_note = (
        f"Evidence coverage is {evidence_level}; this label reflects recorded wardrobe attributes only. "
        "The rank signals are uncalibrated and are not probabilities or human fashion ratings."
    )
    comparison = _rule_comparison(prepared)
    source = "rules"
    scratch_info = fashion_lm_info()
    if not allow_llm:
        return {
            "recommendations": prepared,
            "comparison_explanation": comparison,
            "comparison_source": "rules",
            "evidence_confidence": evidence_level,
            "confidence_note": confidence_note,
            "fashion_lm_available": False,
        }
    if scratch_info.get("weights_present"):
        # Once the scratch-trained AURA model is installed, it is the only LLM
        # used for outfit explanations. Invalid output falls back to the existing
        # evidence-grounded rule explanation; it is never silently replaced by Qwen.
        owned_wardrobe = wardrobe or [
            item for rec in prepared for item in rec.get("items", [])
        ]
        for rec in prepared[:5]:
            if rec["explanation_source"] == "stylist_llm":
                continue
            try:
                draft = explain_outfit(
                    rec.get("items", []), owned_wardrobe, occasion=occasion,
                    temperature=temperature, condition=condition,
                    preferences=preferences,
                )
                if (
                    _has_unverified_claim(
                        draft, rec.get("items", []), temperature=temperature,
                        condition=condition,
                    )
                    or _has_unlisted_garment(draft, rec.get("items", []))
                ):
                    continue
                rec["explanation"] = draft
                rec["explanation_source"] = "aura_fashion_lm"
            except (InvalidFashionResponse, RuntimeError, ValueError, OSError):
                if not fashion_lm_info().get("ready"):
                    break
                continue
        return {
            "recommendations": prepared,
            "comparison_explanation": comparison,
            "comparison_source": "rules",
            "evidence_confidence": evidence_level,
            "confidence_note": confidence_note,
            "fashion_lm_available": bool(fashion_lm_info().get("ready")),
            "fashion_lm_weights_present": True,
        }
    if get_model_info().get("present") and len(prepared) > 1:
        slate = []
        for rank, rec in enumerate(prepared[:5], start=1):
            slate.append({
                "rank": rank,
                "items": [{"category": item.get("category"), "name": item.get("subcategory"),
                           "color": item.get("color_name"), "fabric": item.get("fabric"),
                           "pattern": item.get("pattern"), "fit": item.get("fit")}
                          for item in rec.get("items", [])],
                "rule_signals": rec.get("component_scores", {}),
                "evidence": rec["analysis"],
            })
        payload = {
            "occasion": occasion,
            "weather": {"temperature_c": temperature, "condition": condition},
            "server_ordered_candidates": slate,
            "styling_knowledge": retrieve_guidance(f"{occasion} {condition} color proportion pattern fabric texture layering", 6),
        }
        try:
            raw = generate_response(
                json.dumps(payload, ensure_ascii=False),
                system_prompt=(
                    "Compare the first two server-ranked outfit options for the user's stated occasion. "
                    "Explain why the top option ranks first using recorded rule signals and state a tradeoff. "
                    "Also give each listed candidate a concise practical styling note grounded in its own recorded pieces. "
                    "The server already chose the order: never reorder, score, add, remove, or suggest garments. "
                    "Use only facts in each candidate; do not infer fit, fabric, pattern, identity, or trends. "
                    "Do not present numeric rule signals as percentages or probabilities. "
                    "Return one JSON object with a concise comparison string, an outfit_notes array of objects "
                    "(rank integer and note string), and a limitations array of strings. "
                    "Styling knowledge includes sourced paraphrases and original heuristics, identified by provenance."
                ),
                max_tokens=300,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            decoded = json.loads(raw)
            draft = decoded.get("comparison") if isinstance(decoded, dict) else None
            if not isinstance(draft, str) or not draft.strip():
                raise ValueError("Missing comparison string.")
            if len(draft.strip()) < 24 or re.search(r"\d", draft):
                raise ValueError("Comparison is too short or repeats uncalibrated score values.")
            owned_candidate_items = [item for rec in prepared for item in rec.get("items", [])]
            sentences = [
                sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", draft.strip())
                if sentence.strip()
                and not _has_unverified_claim(sentence, owned_candidate_items, temperature=temperature, condition=condition)
                and not _has_unlisted_garment(sentence, owned_candidate_items)
            ]
            if not sentences:
                raise ValueError("No grounded comparison sentence.")
            comparison = " ".join(sentences[:2])[:500]
            notes = decoded.get("outfit_notes", []) if isinstance(decoded, dict) else []
            if isinstance(notes, list):
                by_rank = {note.get("rank"): note.get("note") for note in notes if isinstance(note, dict)}
                for rank, rec in enumerate(prepared[:5], start=1):
                    note = by_rank.get(rank)
                    if not isinstance(note, str) or rec["explanation_source"] == "stylist_llm":
                        continue
                    own_items = rec.get("items", [])
                    safe_sentences = [
                        sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", note.strip())
                        if sentence.strip()
                        and not _has_unverified_claim(sentence, own_items, temperature=temperature, condition=condition)
                        and not _has_unlisted_garment(sentence, own_items)
                    ]
                    if safe_sentences:
                        rec["explanation"] = " ".join(safe_sentences[:2])[:300]
                        rec["explanation_source"] = "local_llm"
            source = "local_llm"
        except (LocalModelError, ValueError, TypeError, json.JSONDecodeError):
            pass
    return {
        "recommendations": prepared,
        "comparison_explanation": comparison,
        "comparison_source": source,
        "evidence_confidence": evidence_level,
        "confidence_note": confidence_note,
        "fashion_lm_available": False,
    }
