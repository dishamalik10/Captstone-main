"""Chat grounding (ENGINEERING_PLAN 4.5, KNOWN_ISSUES M16).

A stylist reply may only name garments the user owns. Two kinds of sentence may mention
other garments, because the system prompt asks for them:
- an optional idea, phrased conditionally: "if you have white sneakers, ...";
- a gap: "you don't have a blazer", "the only thing missing is a jacket".

Words that are also common verbs or generic nouns ("this suits you", "tie the look
together", "on top", "accessories") count as garments only right after a colour
("a beige suit"). A garment named with a colour must match an owned piece in that
colour: owning a white t-shirt does not make "your light blue t-shirt" grounded.
"""
from __future__ import annotations

import re
from typing import Any

from services.recommendation_explainer import COLOR_TERMS, GARMENT_TERMS

_AMBIGUOUS = {
    "tie", "necktie", "watch", "suit", "suits", "cap", "caps", "top", "tops", "bottom", "bottoms",
    "look", "looks", "accessory", "accessories", "garment", "garments", "clothing", "outfit", "outfits",
    "footwear", "heel", "heels", "trench",
}
TERMS = sorted((GARMENT_TERMS | {"t-shirts", "tee-shirt"}) - _AMBIGUOUS, key=len, reverse=True)  # longest first: "tank top" before "top"
_TERM_RE = re.compile(r"\b(" + "|".join(re.escape(term) for term in TERMS) + r")\b")
_AMBIGUOUS_TERMS = sorted(_AMBIGUOUS - {"look", "looks", "outfit", "outfits", "garment", "garments", "clothing",
                                         "accessory", "accessories", "footwear"}, key=len, reverse=True)
_COLOURS = sorted(COLOR_TERMS | {"khaki", "maroon", "charcoal", "tan", "denim", "burgundy", "mustard"}, key=len, reverse=True)
_SHADES = {"light", "dark", "pale", "deep", "bright"}
_COLOUR = r"(?:(?:light|dark|pale|deep|bright)\s+)?(?:" + "|".join(_COLOURS) + r")"
# "<colour> <garment>", also catching ambiguous words when a colour makes them nouns.
_COLOURED_RE = re.compile(
    r"\b(" + _COLOUR + r")\s+(" + "|".join(re.escape(t) for t in TERMS + _AMBIGUOUS_TERMS) + r")\b"
)

# Same garment, different words.
_SYNONYMS = {
    "tee": "t-shirt", "tshirt": "t-shirt", "tshirts": "t-shirt",
    "pants": "trouser", "chinos": "trouser",
    "t-shirts": "t-shirt", "tee-shirt": "t-shirt",
    "jumper": "sweater",
    "scarves": "scarf",
}
_EXCUSED = re.compile(
    r"\bif you (?:have|own|'ve got|have got)\b|\bif you've\b|\b(?:don't|do not|doesn't|does not|haven't|have not)"
    r" (?:have|own)\b|\bno\b|\bwithout\b|\bmissing\b|\black\b|\bisn't\b|\baren't\b|\bnot in your\b",
)


def canonical(term: str) -> str:
    term = term.lower()
    if term in _SYNONYMS:
        return _SYNONYMS[term]
    for suffix in ("es", "s"):
        if term.endswith(suffix) and term[: -len(suffix)] in GARMENT_TERMS | set(_SYNONYMS):
            term = term[: -len(suffix)]
            break
    return _SYNONYMS.get(term, term)


def _colour_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", text.lower()) if word in _COLOURS or word in _SHADES}


def owned_pieces(items: list[dict[str, Any]]) -> list[tuple[set[str], set[str]]]:
    """(garment terms, colour words) for each owned item."""
    pieces = []
    for item in items:
        text = f"{item.get('subcategory') or ''} {item.get('garment_group') or ''} {item.get('category') or ''}".lower()
        garments = {canonical(match) for match in _TERM_RE.findall(text)}
        if (item.get("category") or "").lower() == "footwear":
            garments.add("shoe")
        pieces.append((garments, _colour_words(str(item.get("color_name") or ""))))
    return pieces


def owned_terms(items: list[dict[str, Any]]) -> set[str]:
    owned: set[str] = set()
    for item in items:
        text = f"{item.get('subcategory') or ''} {item.get('garment_group') or ''} {item.get('category') or ''}".lower()
        owned.update(canonical(match) for match in _TERM_RE.findall(text))
        if (item.get("category") or "").lower() == "footwear":
            owned.add("shoe")  # "your shoes" is fine with any owned footwear; "boots" needs boots
    return owned


def invented_garments(reply: str, items: list[dict[str, Any]]) -> list[str]:
    """Garments the reply presents as owned or worn that are not in ``items``."""
    owned = owned_terms(items)
    pieces = owned_pieces(items)
    invented: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", reply.lower()):
        if _EXCUSED.search(sentence):
            continue
        for colour, garment in _COLOURED_RE.findall(sentence):
            term = canonical(garment)
            wanted = _colour_words(colour)
            # "light blue" needs an item whose colour includes both words.
            if not any(term in garments and wanted <= colours for garments, colours in pieces):
                phrase = f"{colour} {garment}"
                if phrase not in invented:
                    invented.append(phrase)
        for match in _TERM_RE.findall(sentence):
            if canonical(match) not in owned and match not in invented and not any(
                    phrase.endswith(" " + match) for phrase in invented):
                invented.append(match)
    return invented
