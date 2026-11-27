"""Bandit persistence and query shape (M18)."""
import json
import threading
import time
import uuid

import numpy as np

from database import connection, ensure_user, init_database, row, utc_now
from services import bandit_ranker, wardrobe_service
from services.bandit_ranker import RULE_WEIGHTS, BanditModel
from settings import settings

SCORES = {name: 60.0 for name in (*RULE_WEIGHTS, "learned_compatibility")}


def _user_with_recommendation():
    init_database()
    user_id = f"bandit_{uuid.uuid4().hex[:8]}"
    ensure_user(user_id)
    items = []
    with connection() as db:
        for index, (category, sub) in enumerate((("Top", "Shirt"), ("Bottom", "Jeans"))):
            item_id = f"{user_id}_{index}"
            items.append(item_id)
            db.execute(
                """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                   image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item_id, user_id, category, sub, "g", "Blue", f"{item_id}.jpg", "{}", utc_now()),
            )
        rec_id = f"rec_{uuid.uuid4().hex[:12]}"
        db.execute(
            """INSERT INTO recommendations(recommendation_id,user_id,occasion,item_ids,total_score,
               component_scores,explanation,created_at) VALUES(?,?,?,?,?,?,?,?)""",
            (rec_id, user_id, "casual", json.dumps(items), 70.0, json.dumps(SCORES), "", utc_now()),
        )
    return user_id, rec_id, items


def test_prior_uses_the_same_compatibility_weight_as_the_live_ranker():
    assert bandit_ranker.COMPAT_WEIGHT == settings.outfit_compat_weight


def test_two_reactions_at_once_are_both_learned(monkeypatch):
    user_id, rec_id, _ = _user_with_recommendation()
    original_update = BanditModel.update
    first = threading.Event()

    def slow_update(self, *args, **kwargs):
        if not first.is_set():
            first.set()
            time.sleep(0.5)  # the second reaction arrives while the first is mid-update
        return original_update(self, *args, **kwargs)

    monkeypatch.setattr(BanditModel, "update", slow_update)
    threads = [threading.Thread(target=bandit_ranker.learn_from_feedback, args=(user_id, rec_id, action))
               for action in ("like", "save")]
    threads[0].start()
    assert first.wait(5)
    threads[1].start()
    for thread in threads:
        thread.join(15)
    assert row("SELECT updates FROM bandit_models WHERE user_id=?", (user_id,))["updates"] == 2


def test_learning_loads_only_the_outfits_items(monkeypatch):
    user_id, rec_id, items = _user_with_recommendation()
    monkeypatch.setattr(wardrobe_service, "list_items", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the whole wardrobe was loaded")))
    assert bandit_ranker.learn_from_feedback(user_id, rec_id, "like")
    assert sorted(i["item_id"] for i in wardrobe_service.items_by_ids(user_id, items)) == sorted(items)


def test_ranking_looks_up_embeddings_once_per_slate(monkeypatch):
    user_id, rec_id, items = _user_with_recommendation()
    bandit_ranker.learn_from_feedback(user_id, rec_id, "like")
    calls = []
    from services import item_embeddings

    def counting(user, wanted):
        calls.append(len(wanted))
        return {str(item["item_id"]): np.ones(512, dtype=np.float32) for item in wanted}

    monkeypatch.setattr(item_embeddings, "embeddings_for_items", counting)
    entries = [{"component_scores": SCORES, "items": [{"item_id": items[0], "category": "Top", "subcategory": "Shirt",
                                                       "color_name": "Blue"},
                                                      {"item_id": items[1], "category": "Bottom", "subcategory": "Jeans",
                                                       "color_name": "Blue"}]} for _ in range(25)]
    assert bandit_ranker.rank(user_id, entries, "casual", rng=np.random.default_rng(0))
    assert calls == [2]  # one query for 25 candidates sharing 2 garments
    assert all("bandit_score" in entry for entry in entries)
