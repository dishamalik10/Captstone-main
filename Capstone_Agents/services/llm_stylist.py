from __future__ import annotations

import json
import re
from typing import Any

from services.local_llm import LocalModelError
from services.fashion_knowledge import retrieve_guidance


def generate_response(prompt: str, **kwargs: Any) -> str:
    """Chat generation on the configured chat model (base model unless AURA_CHAT_USE_STYLIST=1)."""
    from services.stylist_selector import chat_llm

    return chat_llm().generate_response(prompt, **kwargs)


SYSTEM_PROMPT = """You are AURA, {name}'s personal stylist. You have a strong, practical fashion sense: \
colour theory (neutrals, contrast, warm vs cool tones, tonal dressing), proportion and silhouette, \
dress codes for different occasions, layering, and how shoes and accessories finish a look.

How to talk:
- Chat naturally like a friendly, confident stylist. Answer exactly what {name} asked, and \
explain the reasoning behind your advice in plain words.
- Reply in English, even if {name} writes in Hinglish.
- Keep replies short: usually 2 to 5 sentences. No headings or markdown.

What you know about {name}'s wardrobe (these are the ONLY clothes they own):
{wardrobe}
{outfit}
Rules:
- Build outfits only from the owned clothes above. Never say {name} owns something that is not listed.
- You may suggest optional finishing touches they did not upload (shoes, a belt, jewellery, a bag), \
but phrase them as ideas, for example "if you have white sneakers, they would keep it casual".
- A dress is a complete outfit on its own. Never pair a dress with a t-shirt, top, sweater, trousers, jeans \
or a skirt; only add outerwear (like a jacket), shoes or accessories to it.
- You have no live trend data. If asked what is trending, say so briefly, then share timeless colour \
and styling advice that fits their wardrobe.
- If the wardrobe is missing something needed for the occasion, say what is missing.
{guidance}"""


def _piece(item: dict[str, Any]) -> str:
    return f"{item.get('color_name') or ''} {item.get('subcategory') or 'piece'}".strip().lower()


def _describe(item: dict[str, Any]) -> str:
    """One wardrobe line for the system prompt, with the category and any recorded details."""
    details = [str(item.get(key)).lower() for key in ("fit", "pattern", "fabric")
               if item.get(key) and str(item.get(key)).lower() not in {"unknown", "none"}]
    category = (item.get("category") or "").lower()
    if category == "dress":
        category = "dress, worn on its own (only a jacket, shoes or accessories go with it)"
    line = f"{_piece(item)} — {category}" if category else _piece(item)
    return f"{line}; {', '.join(details)}" if details else line


_SEPARATES = r"(t-?shirt|top|shirt|sweater|blouse|trousers|jeans|pants|skirt|shorts)"


def _pairs_dress_with_separates(reply: str, wardrobe: list[dict[str, Any]]) -> bool:
    """True when the reply puts an owned dress together with a top or bottom in the same sentence."""
    dresses = [_piece(item) for item in wardrobe if (item.get("category") or "").lower() == "dress"]
    for sentence in re.split(r"(?<=[.!?])\s+", reply.lower()):
        if any(dress in sentence or "dress" in sentence for dress in dresses) and re.search(
                rf"\b(with|and|over|under|pair|add|layer)\b.*\b{_SEPARATES}\b|\b{_SEPARATES}\b.*\b(with|and|over|under)\b.*dress",
                sentence):
            return True
    return False


def stylist_reply(*, message: str, user: dict[str, Any], wardrobe: list[dict[str, Any]],
                  recommendation: dict[str, Any] | None,
                  conversation_history: list[dict[str, str]], wants_outfit: bool,
                  fallback: str | None = None, occasion: str | None = None) -> str:
    """Chat with the local model as a stylist that knows the user's wardrobe.

    Model failures (missing weights, busy) are raised so the API reports them; the fallback text
    is used only if the model returns nothing.
    """
    owned_ids = {str(item.get("item_id")) for item in wardrobe if item.get("item_id")}
    if recommendation is not None:
        selected_ids = {str(item_id) for item_id in recommendation.get("item_ids", [])}
        if not selected_ids or not selected_ids.issubset(owned_ids):
            raise LocalModelError("Recommendation failed the owned-wardrobe validation.")

    name = (user.get("fullName") or "").split(" ")[0].title() or "the user"
    wardrobe_text = "\n".join(f"- {_describe(item)}" for item in wardrobe[:40]) or "- (nothing uploaded yet)"
    outfit_text = ""
    if recommendation is not None and recommendation.get("items"):
        pieces = " + ".join(_piece(item) for item in recommendation["items"])
        is_dress = any((item.get("category") or "").lower() == "dress" for item in recommendation["items"])
        outfit_text = (
            f"\nYou have chosen this outfit for {occasion or 'this request'}, and its photo is shown under "
            f"your reply: {pieces}.\n"
            "Recommend it in your own voice (say \"I'd go with...\" or \"wear your...\"; never say the app "
            "picked it), name each piece, and explain why it works for the occasion: colours, contrast and "
            "how dressy it feels. You can mention one other owned combination as an alternative.\n"
            + ("This outfit is a dress: do not suggest adding any top, t-shirt, sweater or bottom to it; "
               "only a jacket, shoes or accessories.\n" if is_dress else "")
        )
    guidance = retrieve_guidance(f"{message} {occasion or ''}", limit=3)
    guidance_text = ""
    if guidance:
        notes = " ".join(entry["guidance"] for entry in guidance if entry.get("guidance"))
        guidance_text = f"\nBackground styling notes you may draw on: {notes}"

    history = [
        {"role": "assistant" if turn.get("role") == "assistant" else "user",
         "content": str(turn.get("content", ""))[:600]}
        for turn in conversation_history[-8:]
        if str(turn.get("content", "")).strip()
    ]
    system_prompt = SYSTEM_PROMPT.format(
        name=name, wardrobe=wardrobe_text, outfit=outfit_text, guidance=guidance_text,
    )
    if recommendation is not None and recommendation.get("items"):
        chosen = " + ".join(_piece(item) for item in recommendation["items"])
        user_turn = (f"{message}\n\n(The outfit shown under your reply is: {chosen}. Recommend exactly "
                     "this outfit as your main suggestion.)")
    else:
        user_turn = message
    response = generate_response(
        user_turn, system_prompt=system_prompt, history=history, max_tokens=260, temperature=0.7,
    )
    if _pairs_dress_with_separates(response, wardrobe):
        # Small models sometimes ignore the dress rule; ask once more with the mistake pointed out.
        response = generate_response(
            f"{user_turn}\n\n(Note: a dress is worn on its own. Do not pair the dress with a t-shirt, top, "
            "sweater, trousers, jeans or skirt; only suggest a jacket, shoes or accessories with it.)",
            system_prompt=system_prompt, history=history, max_tokens=260, temperature=0.5,
        )
    # The app renders plain text, so strip markdown emphasis and heading marks.
    response = re.sub(r"(?m)^\s*#+\s*", "", response)
    response = re.sub(r"\*\*|__|`", "", response).strip()
    if response:
        return response[:1200]
    if fallback and fallback.strip():
        return fallback[:700]
    raise LocalModelError("Local model returned an empty response.")


PICK_SCHEMA = {
    "type": "object",
    "properties": {"choice": {"type": "integer"}},
    "required": ["choice"],
}

PICK_SYSTEM_PROMPT = """You are an expert personal stylist choosing ONE outfit from a numbered list of \
outfits the user already owns. Think like a stylist: match how dressy the outfit is to the occasion \
(for example a dress or a darker, sharper look for a date or party; a neat, simple, layered look for a \
meeting or office; comfortable, easy pieces for travel), use colour and contrast well, and follow any \
wish the user expressed (bolder, simpler, a colour, warmer). Prefer an outfit that has not already been \
suggested in this chat, unless the user asks for the same one. Answer only with JSON: {"choice": <number>}."""


def pick_outfit(*, message: str, occasion: str, candidates: list[dict[str, Any]],
                conversation_history: list[dict[str, str]],
                already_shown: list[set[str]]) -> int:
    """Let the chat model pick the best candidate for the user's request; 0 if it cannot."""
    if len(candidates) < 2:
        return 0
    lines = []
    for number, candidate in enumerate(candidates, start=1):
        pieces = " + ".join(_piece(item) for item in candidate.get("items", []))
        shown = set(map(str, candidate.get("item_ids", []))) in already_shown
        lines.append(f"{number}. {pieces}" + (" (already suggested in this chat)" if shown else ""))
    recent = "\n".join(
        f"{turn.get('role')}: {str(turn.get('content', ''))[:200]}" for turn in conversation_history[-4:]
    )
    prompt = (
        (f"Recent chat:\n{recent}\n\n" if recent else "")
        + f'User\'s request: "{message}"\nOccasion: {occasion}\n\nOutfits they own:\n' + "\n".join(lines)
        + "\n\nWhich number is the best outfit for this request?"
    )
    try:
        raw = generate_response(
            prompt, system_prompt=PICK_SYSTEM_PROMPT, max_tokens=20, temperature=0.2,
            response_format={"type": "json_object", "schema": PICK_SCHEMA},
        )
        choice = int(json.loads(raw)["choice"])
    except (LocalModelError, ValueError, TypeError, KeyError):
        return 0
    return choice - 1 if 1 <= choice <= len(candidates) else 0
