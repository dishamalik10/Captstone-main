"""Ranking snapshot: a fixed wardrobe and fixed feedback must produce a fixed order.

This is a guard rail, not a quality test. Any change to rule weights, candidate
generation, the bandit prior or feedback handling that moves these outfits will fail
here, so ranking changes are always made on purpose. When a change is intended,
regenerate the expected lists (run with AURA_PRINT_SNAPSHOT=1 and copy the output)
and say why in the commit message.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from database import connection, ensure_user, init_database, utc_now
from services import bandit_ranker, outfit_compat_service
from services.recommendation_service import recommend, save_feedback
from settings import settings

WARDROBE = [
    ("snap_top_white_shirt", "Top", "Shirt", "White", "formal"),
    ("snap_top_navy_tee", "Top", "T-shirt", "Navy", "casual"),
    ("snap_top_pink_blouse", "Top", "Blouse", "Pink", "party"),
    ("snap_top_grey_sweater", "Top", "Sweater", "Grey", "casual"),
    ("snap_bottom_black_trousers", "Bottom", "Trousers", "Black", "formal"),
    ("snap_bottom_blue_jeans", "Bottom", "Jeans", "Blue", "casual"),
    ("snap_bottom_beige_skirt", "Bottom", "Skirt", "Beige", "party"),
    ("snap_dress_red", "Dress", "Dress", "Red", "party"),
    ("snap_shoe_white_sneakers", "Footwear", "Sneakers", "White", "casual"),
    ("snap_shoe_brown_boots", "Footwear", "Boots", "Brown", "casual"),
    ("snap_shoe_black_heels", "Footwear", "Heels", "Black", "party"),
    ("snap_outer_denim_jacket", "Outerwear", "Jacket", "Blue", "casual"),
]

EXPECTED_COLD_START = [
    ["snap_bottom_blue_jeans", "snap_shoe_white_sneakers", "snap_top_navy_tee"],
    ["snap_bottom_blue_jeans", "snap_shoe_brown_boots", "snap_top_grey_sweater"],
    ["snap_bottom_black_trousers", "snap_outer_denim_jacket", "snap_shoe_brown_boots", "snap_top_navy_tee"],
    ["snap_bottom_beige_skirt", "snap_outer_denim_jacket", "snap_shoe_white_sneakers", "snap_top_grey_sweater"],
    ["snap_bottom_blue_jeans", "snap_shoe_white_sneakers", "snap_top_grey_sweater"],
]
# Feedback on the first slate: like, dislike, wear, skip, save (in that order).
EXPECTED_AFTER_FEEDBACK = [
    ["snap_bottom_black_trousers", "snap_shoe_brown_boots", "snap_top_navy_tee"],
    ["snap_bottom_blue_jeans", "snap_shoe_black_heels", "snap_top_navy_tee"],
    ["snap_bottom_black_trousers", "snap_shoe_black_heels", "snap_top_navy_tee"],
    ["snap_bottom_blue_jeans", "snap_shoe_brown_boots", "snap_top_navy_tee"],
    ["snap_bottom_black_trousers", "snap_shoe_white_sneakers", "snap_top_navy_tee"],
]


def _seed(user_id: str) -> None:
    init_database()
    ensure_user(user_id)
    with connection() as db:
        db.execute("DELETE FROM clothing_items WHERE user_id=?", (user_id,))
        for name, category, subcategory, color, occasion in WARDROBE:
            item_id = f"{user_id}:{name}"  # item IDs are global, so namespace them per user
            confidence = {"product_type": {"label": subcategory, "confidence": 0.9, "top_3": []}}
            db.execute(
                """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                   occasion_tags,image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (item_id, user_id, category, subcategory, "g", color, json.dumps([occasion]),
                 f"/missing/{item_id}.jpg", json.dumps(confidence), utc_now()),
            )


@pytest.fixture
def deterministic_ranking(monkeypatch):
    """Seed the bandit's Thompson sample and keep optional models out of the result."""
    original_rank = bandit_ranker.rank
    monkeypatch.setattr(
        bandit_ranker, "rank",
        lambda *args, **kwargs: original_rank(*args, **{**kwargs, "rng": np.random.default_rng(1234)}),
    )
    # The snapshot covers AURA's own ranking logic; the Polyvore model is optional
    # and its weights may or may not be installed on the machine running the tests.
    monkeypatch.setattr(outfit_compat_service, "_load", lambda: None)
    monkeypatch.setattr(outfit_compat_service, "_model", None)
    previous = settings.bandit_enabled
    object.__setattr__(settings, "bandit_enabled", True)
    yield
    object.__setattr__(settings, "bandit_enabled", previous)


def _order(results: list[dict]) -> list[list[str]]:
    return [sorted(item["item_id"].split(":", 1)[1] for item in result["items"]) for result in results]


def _maybe_print(label: str, value) -> None:
    if os.getenv("AURA_PRINT_SNAPSHOT"):
        print(f"\n{label} = {json.dumps(value, indent=4)}")


def test_cold_start_order_is_stable(deterministic_ranking):
    user_id = "snapshot_cold"
    _seed(user_id)
    results, _ = recommend(user_id, "casual", 22.0, "Clear", 5)
    order = _order(results)
    _maybe_print("EXPECTED_COLD_START", order)
    assert order == EXPECTED_COLD_START


def test_order_after_fixed_feedback_is_stable(deterministic_ranking):
    user_id = "snapshot_feedback"
    _seed(user_id)
    with connection() as db:
        db.execute("DELETE FROM feedback WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM bandit_models WHERE user_id=?", (user_id,))
    first, _ = recommend(user_id, "casual", 22.0, "Clear", 5)
    for result, action in zip(first, ("like", "dislike", "wear", "skip", "save")):
        save_feedback({
            "user_id": user_id,
            "recommendation_id": result["recommendation_id"],
            "item_ids": [item["item_id"] for item in result["items"]],
            "action": action,
        })
    results, _ = recommend(user_id, "casual", 22.0, "Clear", 5)
    order = _order(results)
    _maybe_print("EXPECTED_AFTER_FEEDBACK", order)
    assert order == EXPECTED_AFTER_FEEDBACK
