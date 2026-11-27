"""Slates are written atomically, tagged by surface, and store what the user saw (M6, M7)."""
import json
import uuid

import pytest

from database import connection, ensure_user, init_database, rows, utc_now
from services import app_service, recommendation_service
from services.recommendation_service import record_explanations, recommend

WARDROBE = [("Top", "Shirt", "White"), ("Top", "T-shirt", "Navy"), ("Bottom", "Jeans", "Blue"),
            ("Bottom", "Trousers", "Black"), ("Footwear", "Sneakers", "White")]


def _user():
    init_database()
    user_id = f"slate_{uuid.uuid4().hex[:8]}"
    ensure_user(user_id)
    with connection() as db:
        for index, (category, sub, colour) in enumerate(WARDROBE):
            db.execute(
                """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                   image_path,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (f"{user_id}_{index}", user_id, category, sub, "g", colour, f"{user_id}_{index}.jpg",
                 json.dumps({"product_type": {"label": sub, "confidence": 0.9, "top_3": []}}), utc_now()),
            )
    return user_id


def _stored(user_id):
    return rows("SELECT * FROM recommendations WHERE user_id=? ORDER BY rank_position", (user_id,))


def test_a_failure_part_way_through_a_slate_stores_nothing(monkeypatch):
    user_id = _user()
    real = recommendation_service.analyze_outfit
    calls = []

    def fail_on_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(recommendation_service, "analyze_outfit", fail_on_second)
    with pytest.raises(RuntimeError):
        recommend(user_id, "casual", 22.0, "Clear", 3)
    assert _stored(user_id) == []


def test_slate_rows_are_tagged_with_their_surface_and_explanation_source():
    user_id = _user()
    results, _ = recommend(user_id, "casual", 22.0, "Clear", 3)
    stored = _stored(user_id)
    assert len(stored) == len(results) == 3
    assert {r["surface"] for r in stored} == {"recommend"}
    assert {r["explanation_source"] for r in stored} == {"rules"}
    assert len({r["run_id"] for r in stored}) == 1


def test_the_explanation_the_user_saw_is_stored():
    user_id = _user()
    results, _ = recommend(user_id, "casual", 22.0, "Clear", 2)
    shown = [{**results[0], "explanation": "Final explainer text", "explanation_source": "aura_fashion_lm"}, results[1]]
    record_explanations(user_id, shown)
    first = _stored(user_id)[0]
    assert (first["explanation"], first["explanation_source"]) == ("Final explainer text", "aura_fashion_lm")


def test_chat_keeps_only_the_outfit_it_showed(monkeypatch):
    from services import llm_stylist

    user_id = _user()
    monkeypatch.setattr(app_service, "_choose_outfit", lambda *args, **kwargs: 0)
    monkeypatch.setattr(llm_stylist, "stylist_reply", lambda **kwargs: "Wear the navy tee with jeans.")
    response = app_service.chat(user_id, "What should I wear for a date?", "slate-test")
    assert response["outfit"]
    stored = _stored(user_id)
    assert len(stored) == 1, "chat must not persist outfits the user never saw"
    assert stored[0]["recommendation_id"] == response["outfit"]["id"]
    assert stored[0]["surface"] == "chat"
    assert (stored[0]["explanation"], stored[0]["explanation_source"]) == ("Wear the navy tee with jeans.", "chat_reply")


def test_offline_evaluation_ignores_chat_rows(monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("evaluate_feedback", Path(__file__).parents[1] / "scripts" / "evaluate_feedback.py")
    evaluate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluate)
    before = evaluate.collect()["recommendation_items_returned"]
    from services import llm_stylist

    user_id = _user()
    monkeypatch.setattr(app_service, "_choose_outfit", lambda *args, **kwargs: 0)
    monkeypatch.setattr(llm_stylist, "stylist_reply", lambda **kwargs: "reply")
    app_service.chat(user_id, "Outfit for a party please", "slate-eval")
    assert evaluate.collect()["recommendation_items_returned"] == before
    recommend(user_id, "casual", 22.0, "Clear", 2)
    assert evaluate.collect()["recommendation_items_returned"] == before + 2
