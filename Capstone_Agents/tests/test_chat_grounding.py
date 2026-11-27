"""ENGINEERING_PLAN 4.5: chat replies may only name garments the user owns."""
import pytest

from services import llm_stylist
from services.chat_grounding import invented_garments
from services.local_llm import LocalModelError

WARDROBE = [
    {"item_id": "i1", "category": "Top", "subcategory": "T-shirt", "garment_group": "Jersey Basic", "color_name": "White"},
    {"item_id": "i2", "category": "Bottom", "subcategory": "Jeans", "garment_group": "Trousers Denim", "color_name": "Blue"},
    {"item_id": "i3", "category": "Footwear", "subcategory": "Sneakers", "garment_group": "Shoes", "color_name": "White"},
]


@pytest.mark.parametrize("reply", [
    "Wear your white tee with the blue jeans and sneakers.",
    "Wear your blue jeans with the white sneakers and white t-shirt.",
    "Pair the t-shirt with your pants; your shoes keep it easy.",
    "This suits a casual day, and the white ties the look together.",  # verbs, not garments
    "If you have a leather belt, it would finish the outfit.",          # optional idea
    "You don't have a blazer, so keep it relaxed for the meeting.",     # a gap
    "The only thing missing for a wedding is a jacket.",
])
def test_grounded_replies_pass(reply):
    assert invented_garments(reply, WARDROBE) == []


@pytest.mark.parametrize("reply,invented", [
    ("Layer your navy blazer over the tee.", ["navy blazer"]),
    ("Wear your jeans with your brown boots.", ["brown boots"]),
    # Owned garment types in colours the user doesn't own (seen in the 4.5 model run).
    ("Wear the light blue t-shirt with white jeans.", ["light blue t-shirt", "white jeans"]),
    ("It would look right with white sneakers or a beige suit.", ["beige suit"]),
    ("Throw on the hoodie and the skirt.", ["hoodie", "skirt"]),
])
def test_invented_garments_are_found(reply, invented):
    assert invented_garments(reply, WARDROBE) == invented


def _reply(monkeypatch, outputs, fallback="For casual, wear your white t-shirt, blue jeans and white sneakers."):
    calls = []

    def generate(prompt, **kwargs):
        calls.append(prompt)
        return outputs[len(calls) - 1]

    monkeypatch.setattr(llm_stylist, "generate_response", generate)
    trace: dict = {}
    text = llm_stylist.stylist_reply(
        message="what should I wear today?", user={"fullName": "Asha"}, wardrobe=WARDROBE,
        recommendation={"item_ids": ["i1", "i2", "i3"], "items": WARDROBE}, conversation_history=[],
        wants_outfit=True, fallback=fallback, occasion="casual", trace=trace,
    )
    return text, calls, trace


def test_grounded_first_reply_is_used_without_regenerating(monkeypatch):
    text, calls, trace = _reply(monkeypatch, ["I'd go with your white tee and blue jeans."])
    assert text == "I'd go with your white tee and blue jeans." and len(calls) == 1
    assert trace == {"attempts": 1, "first_invented": [], "final_invented": [], "source": "model"}


def test_invented_piece_triggers_one_regeneration_naming_it(monkeypatch):
    text, calls, trace = _reply(monkeypatch, ["Add your black blazer.", "Wear your white tee with blue jeans."])
    assert text == "Wear your white tee with blue jeans." and len(calls) == 2
    assert "blazer is not in Asha's wardrobe" in calls[1]
    assert trace["first_invented"] == ["black blazer"] and trace["source"] == "model"


def test_second_invention_falls_back_to_the_deterministic_reply(monkeypatch):
    text, calls, trace = _reply(monkeypatch, ["Add your black blazer.", "Your blazer and loafers."])
    assert text.startswith("For casual, wear your white t-shirt") and len(calls) == 2
    assert trace["source"] == "fallback" and trace["final_invented"] == ["blazer", "loafers"]


def test_without_a_fallback_an_ungrounded_reply_is_an_error(monkeypatch):
    with pytest.raises(LocalModelError):
        _reply(monkeypatch, ["Add your blazer.", "Add your blazer."], fallback="")
