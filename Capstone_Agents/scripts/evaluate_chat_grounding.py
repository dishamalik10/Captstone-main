"""Invented-piece rate of the chat stylist on a fixed prompt set (ENGINEERING_PLAN 4.5).

    python -m scripts.evaluate_chat_grounding [--out training/chat_grounding_results.json]

Runs the configured chat model (the same one /chat/messages uses) over FIXED prompts and
a FIXED wardrobe, so numbers are comparable between runs and model versions. Reports:
- first_draft_invented_rate: replies whose first draft named an unowned garment (the
  model's own behaviour, before the 4.5 check);
- regenerated_rate: replies that needed the one regeneration;
- fallback_rate: replies replaced by the deterministic text after two failures;
- shown_invented_rate: replies shown to the user that still name an unowned garment
  (should be 0 — the check runs on everything shown).
Generation is sampled (temperature 0.7), so expect a few points of run-to-run variation.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.chat_grounding import invented_garments  # noqa: E402

WARDROBE = [
    {"item_id": "w1", "category": "Top", "subcategory": "T-shirt", "garment_group": "Jersey Basic", "color_name": "White"},
    {"item_id": "w2", "category": "Top", "subcategory": "Shirt", "garment_group": "Shirt", "color_name": "Light Blue"},
    {"item_id": "w3", "category": "Bottom", "subcategory": "Jeans", "garment_group": "Trousers Denim", "color_name": "Dark Blue"},
    {"item_id": "w4", "category": "Bottom", "subcategory": "Trousers", "garment_group": "Trousers", "color_name": "Beige"},
    {"item_id": "w5", "category": "Dress", "subcategory": "Dress", "garment_group": "Dresses Ladies", "color_name": "Black"},
    {"item_id": "w6", "category": "Footwear", "subcategory": "Sneakers", "garment_group": "Shoes", "color_name": "White"},
    {"item_id": "w7", "category": "Outerwear", "subcategory": "Jacket", "garment_group": "Outdoor", "color_name": "Olive"},
]
OUTFITS = {
    "casual": ["w1", "w3", "w6"],
    "office": ["w2", "w4", "w6"],
    "date": ["w5", "w7"],
}
# (message, occasion with a shown outfit, or None for a conversational reply)
PROMPTS = [
    ("What should I wear to college tomorrow?", "casual"),
    ("Suggest something casual for a weekend brunch", "casual"),
    ("I need an outfit for a client meeting", "office"),
    ("What's a good office look for Monday?", "office"),
    ("Plan an outfit for a dinner date", "date"),
    ("I have a party tonight, what should I wear?", "date"),
    ("Something comfortable for a long flight", "casual"),
    ("What goes well with my beige trousers?", None),
    ("How do I style a black dress?", None),
    ("Which colours suit a light blue shirt?", None),
    ("Is it okay to wear sneakers to the office?", None),
    ("What's trending this season?", None),
    ("I don't own a blazer. What do I wear to an interview?", None),
    ("Can I wear my olive jacket in the rain?", None),
    ("Make my outfit look more formal", None),
    ("kal shaadi hai, kya pehnu?", None),  # Hinglish: "wedding tomorrow, what do I wear?"
    ("What shoes go with my dark jeans?", None),
    ("How should I layer for a cold morning?", None),
    ("Give me three ways to wear my white t-shirt", None),
    ("thanks, that helps!", None),
]
FALLBACK = "I can help with outfits from the clothes you've uploaded."


def run() -> dict:
    from services.llm_stylist import _piece, stylist_reply

    by_id = {item["item_id"]: item for item in WARDROBE}
    results = []
    for message, occasion in PROMPTS:
        recommendation = None
        fallback = FALLBACK
        if occasion:
            items = [by_id[i] for i in OUTFITS[occasion]]
            recommendation = {"item_ids": OUTFITS[occasion], "items": items}
            fallback = f"For {occasion}, wear your {', '.join(_piece(item) for item in items)}."
        trace: dict = {}
        started = time.monotonic()
        reply = stylist_reply(message=message, user={"fullName": "Asha"}, wardrobe=WARDROBE,
                              recommendation=recommendation, conversation_history=[],
                              wants_outfit=occasion is not None, fallback=fallback,
                              occasion=occasion, trace=trace)
        results.append({"message": message, "occasion": occasion, "reply": reply,
                        "seconds": round(time.monotonic() - started, 1),
                        "shown_invented": invented_garments(reply, WARDROBE), **trace})
        print(f"[{trace['source']:8}] first={trace['first_invented']} {message}", flush=True)
    n = len(results)

    def rate(predicate) -> float:
        return round(sum(1 for r in results if predicate(r)) / n, 3)

    from services.stylist_selector import chat_model_source

    return {
        "model": chat_model_source(),
        "prompts": n,
        "first_draft_invented_rate": rate(lambda r: r["first_invented"]),
        "regenerated_rate": rate(lambda r: r["attempts"] == 2),
        "fallback_rate": rate(lambda r: r["source"] == "fallback"),
        "shown_invented_rate": rate(lambda r: r["shown_invented"]),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    summary = run()
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    if args.out:
        args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
