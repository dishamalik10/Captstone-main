from __future__ import annotations

import json
import re
from typing import Any

from services.local_llm import LocalModelError
from services.fashion_knowledge import retrieve_guidance
from services.recommendation_explainer import _has_unlisted_garment, _has_unverified_claim



def generate_response(prompt: str, **kwargs: Any) -> str:
    """Chat generation on the fine-tuned stylist when installed, else the base chat model."""
    from services.stylist_selector import chat_llm

    return chat_llm().generate_response(prompt, **kwargs)


def stylist_reply(*, message: str, user: dict[str, Any], wardrobe: list[dict[str, Any]],
                  recommendation: dict[str, Any] | None,
                  conversation_history: list[dict[str, str]], wants_outfit: bool,
                  fallback: str | None = None) -> str:
    """Generate the stylist response locally; failures are surfaced to the caller."""
    owned_ids = {str(item.get("item_id")) for item in wardrobe if item.get("item_id")}
    if recommendation is not None:
        selected_ids = {str(item_id) for item_id in recommendation.get("item_ids", [])}
        if not selected_ids or not selected_ids.issubset(owned_ids):
            raise LocalModelError("Recommendation failed the owned-wardrobe validation.")
    context = {
        "user_profile": {"name": user.get("fullName"), "location": user.get("location"),
                         "style_preferences": user.get("stylePreferences", []),
                         "skin_tone": user.get("skinTone")},
        "uploaded_wardrobe": [{"id": item.get("item_id"), "name": item.get("subcategory"),
                                "category": item.get("category"), "color": item.get("color_name"),
                                "style_tags": item.get("style_tags", []), "fabric": item.get("fabric"),
                                "pattern": item.get("pattern"), "fit": item.get("fit")}
                               for item in wardrobe[:40]],
        "selected_recommendation": (None if recommendation is None else {
            "item_ids": recommendation.get("item_ids", []),
            "compatibility_score": recommendation.get("compatibility_score"),
            "explanation": recommendation.get("explanation")}),
        "wants_outfit": wants_outfit,
        "recent_conversation": conversation_history[-12:],
        "user_message": message,
        "fashion_guidance": retrieve_guidance(
            f"{message} {recommendation.get('explanation', '') if recommendation else ''}",
            limit=4,
        ),
    }
    response = generate_response(
        json.dumps(context, ensure_ascii=False),
        system_prompt=("You are AURA, a concise practical fashion stylist. Use only the provided "
                       "owned wardrobe and, for outfits, only selected recommendation item IDs. "
                       "Never invent owned garments. You explain the server-selected recommendation; "
                       "you do not select or add garments. If no recommendation is provided, do not "
                       "suggest garments; explain missing wardrobe categories. "
                       "Use fashion_guidance only as general heuristic context, never as research or trend evidence. "
                       "Keep the reply under 120 words."),
        max_tokens=220,
    )
    validation_items = recommendation.get("items", []) if recommendation is not None else wardrobe
    grounded_sentences = [
        sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", response)
        if sentence.strip()
        and not _has_unlisted_garment(sentence, validation_items)
        and not _has_unverified_claim(sentence, validation_items, temperature=25.0, condition="Unknown")
    ]
    if grounded_sentences:
        return " ".join(grounded_sentences[:3])[:600]
    if fallback and fallback.strip():
        return fallback[:600]
    raise LocalModelError("Local model response failed wardrobe grounding validation.")
