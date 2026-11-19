"""Tests for the hybrid stylist: candidate coverage, item-level compatibility,
LLM option selection and the shared prompt contract."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

from database import connection, ensure_user, init_database, utc_now
from ml import stylist_prompt
from ml.outfit_compat import build_model, encode_outfits
from services import outfit_compat_service, recommendation_service, stylist_selector
from services.item_embeddings import pack_embedding
from services.recommendation_service import _candidates, recommend
from settings import settings


def _items(category: str, count: int) -> list[dict]:
    return [{"item_id": f"{category}{index}", "category": category} for index in range(count)]


def test_candidate_budget_reaches_every_top_and_bottom():
    wardrobe = (_items("Top", 16) + _items("Bottom", 12) + _items("Footwear", 6)
                + _items("Outerwear", 5) + _items("Accessory", 6) + _items("Dress", 3))
    candidates = _candidates(wardrobe)
    used = {item["item_id"] for candidate in candidates for item in candidate}
    assert {f"Top{i}" for i in range(16)} <= used
    assert {f"Bottom{i}" for i in range(12)} <= used
    assert {f"Dress{i}" for i in range(3)} <= used
    assert len(candidates) <= 750
    # Every candidate has shoes when the wardrobe has shoes.
    assert all(any(item["category"] == "Footwear" for item in candidate) for candidate in candidates)


def test_candidate_budget_with_huge_wardrobe_stays_bounded():
    wardrobe = _items("Top", 40) + _items("Bottom", 40) + _items("Footwear", 3)
    candidates = _candidates(wardrobe)
    assert 0 < len(candidates) <= 750


def _seed_wardrobe(user_id: str, with_embeddings: bool = True) -> dict[str, np.ndarray]:
    init_database()
    ensure_user(user_id)
    rng = np.random.default_rng(7)
    embeddings = {}
    rows_to_add = [("Top", "Shirt", "White"), ("Top", "T-shirt", "Navy"), ("Top", "Blouse", "Pink"),
                   ("Bottom", "Trousers", "Black"), ("Bottom", "Jeans", "Blue"),
                   ("Footwear", "Sneakers", "White"), ("Footwear", "Boots", "Brown")]
    with connection() as db:
        for category, subcategory, color in rows_to_add:
            item_id = f"cloth_{uuid.uuid4().hex[:12]}"
            vector = rng.normal(size=512).astype(np.float32)
            embeddings[item_id] = vector
            confidence = {"product_type": {"label": subcategory, "confidence": 0.9, "top_3": []}}
            db.execute(
                """INSERT INTO clothing_items(item_id,user_id,category,subcategory,garment_group,color_name,
                   image_path,confidence,created_at,embedding) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (item_id, user_id, category, subcategory, "g", color, f"/missing/{item_id}.jpg",
                 json.dumps(confidence), utc_now(), pack_embedding(vector) if with_embeddings else None),
            )
    return embeddings


@pytest.fixture
def installed_compat_model(tmp_path, monkeypatch):
    model = build_model({"num_layers": 1, "model_dim": 64, "ff_dim": 64, "num_heads": 2})
    weights = tmp_path / "outfit_compat.weights.h5"
    config = tmp_path / "outfit_compat.config.json"
    model.save_weights(str(weights))
    config.write_text(json.dumps({
        "model_config": {"num_layers": 1, "model_dim": 64, "ff_dim": 64, "num_heads": 2},
        "training_split": "test-fixture",
        "test_metrics": {"auc": None},
    }))
    object.__setattr__(settings, "outfit_compat_weights_path", weights)
    object.__setattr__(settings, "outfit_compat_config_path", config)
    outfit_compat_service.reset_for_tests()
    yield model
    object.__setattr__(settings, "outfit_compat_weights_path", tmp_path / "absent.h5")
    object.__setattr__(settings, "outfit_compat_config_path", tmp_path / "absent.json")
    outfit_compat_service.reset_for_tests()


def test_item_level_model_scores_each_garment_combination(installed_compat_model):
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    _seed_wardrobe(user_id)
    recommendations, trace = recommend(user_id, "office", 22.0, "Clear", 5)
    assert recommendations
    assert all(rec["compatibility_source"] == "item_level" for rec in recommendations)
    scoring = next(step for step in trace["agents"] if step["agent"] == "scoring_agents")
    assert scoring["compatibility_sources"] == ["item_level"]
    visual_scores = {rec["component_scores"]["learned_compatibility"] for rec in recommendations}
    # Category-only scoring gave every top+bottom+shoe outfit the same value; this must not.
    assert len(visual_scores) > 1
    assert outfit_compat_service.status()["available"] is True


def test_missing_embeddings_fall_back_without_crashing(installed_compat_model):
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    _seed_wardrobe(user_id, with_embeddings=False)  # images are missing too -> no backfill
    recommendations, _ = recommend(user_id, "casual", 25.0, "Unknown", 3)
    assert recommendations
    assert all(rec["compatibility_source"] != "item_level" for rec in recommendations)


class FakeLLM:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls: list[dict] = []

    def generate_response(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return self.answer


def _use_fake_llm(monkeypatch, answer: str) -> FakeLLM:
    fake = FakeLLM(answer)
    monkeypatch.setattr(stylist_selector, "_llm", lambda: fake)
    monkeypatch.setattr(stylist_selector, "model_source", lambda: "test_double")
    return fake


def test_stylist_llm_choice_becomes_first_recommendation(monkeypatch):
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    _seed_wardrobe(user_id)
    baseline, _ = recommend(user_id, "office", 22.0, "Clear", 5)
    third = baseline[2]
    third_types = " and ".join(item["subcategory"].lower() for item in third["items"][:2])
    fake = _use_fake_llm(monkeypatch, json.dumps({"choice": 3, "reason": f"The {third_types} give a clean office line."}))
    with connection() as db:
        db.execute("UPDATE users SET profile_json=? WHERE user_id=?",
                   (json.dumps({"bodyShape": "Rectangle", "heightCm": 170}), user_id))
    recommendations, trace = recommend(user_id, "office", 22.0, "Clear", 3, use_stylist=True)
    assert sorted(recommendations[0]["item_ids"]) == sorted(third["item_ids"])
    assert recommendations[0]["explanation_source"] == "stylist_llm"
    payload = json.loads(fake.calls[0]["prompt"])
    assert payload["body_shape"] == "Rectangle" and payload["occasion"] == "office"
    assert "cloth_" not in fake.calls[0]["prompt"]  # the LLM never sees item IDs
    step = next(step for step in trace["agents"] if step["agent"] == "stylist_llm_agent")
    assert step["chosen_option"] == 3 and step["may_add_or_change_items"] is False


def test_invalid_stylist_answer_keeps_ranker_order(monkeypatch):
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    _seed_wardrobe(user_id)
    baseline, _ = recommend(user_id, "office", 22.0, "Clear", 3)
    _use_fake_llm(monkeypatch, '{"choice": 9, "reason": "Option nine is great."}')
    recommendations, trace = recommend(user_id, "office", 22.0, "Clear", 3, use_stylist=True)
    assert sorted(recommendations[0]["item_ids"]) == sorted(baseline[0]["item_ids"])
    assert recommendations[0].get("explanation_source") != "stylist_llm"
    step = next(step for step in trace["agents"] if step["agent"] == "stylist_llm_agent")
    assert step["status"] == "skipped"


def test_hallucinated_reason_keeps_choice_but_uses_rule_text(monkeypatch):
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    _seed_wardrobe(user_id)
    _use_fake_llm(monkeypatch, '{"choice": 2, "reason": "Add a red leather jacket and a scarf for drama."}')
    recommendations, _ = recommend(user_id, "office", 22.0, "Clear", 3, use_stylist=True)
    assert recommendations[0].get("explanation_source") != "stylist_llm"
    assert "jacket" not in recommendations[0]["explanation"].lower()


def test_prompt_contract_round_trip():
    context = {"occasion": "date", "weather": {"temperature_c": 12, "condition": "Rain"},
               "body_shape": "Pear", "preferences": {"preferred_colors": ["Navy"], "avoided_colors": []}}
    options = [{"visual_match": 0.82, "items": [{"category": "Top", "type": "Blouse", "color": "Navy"}]},
               {"visual_match": 0.2, "items": [{"category": "Dress", "type": "Dress", "color": "Red", "fit": None}]}]
    payload = json.loads(stylist_prompt.build_user_payload(context, options))
    assert payload["options"][0]["visual_match"] == "high"
    assert payload["options"][1]["visual_match"] == "low"
    assert "fit" not in payload["options"][1]["items"][0]
    assert payload["preferences"] == {"preferred_colors": ["Navy"]}
    answer = stylist_prompt.format_answer(2, "The red dress suits a date.")
    assert stylist_prompt.parse_answer(answer, 2) == (2, "The red dress suits a date.")
    assert stylist_prompt.parse_answer("```json\n" + answer + "\n```", 2)[0] == 2
    with pytest.raises(ValueError):
        stylist_prompt.parse_answer('{"choice": 3, "reason": "Out of range option."}', 2)
    with pytest.raises(ValueError):
        stylist_prompt.parse_answer("I like option 1", 2)


def test_feedback_heavy_users_are_scored_quickly():
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    embeddings = _seed_wardrobe(user_id)
    ids = list(embeddings)
    with connection() as db:
        for index in range(250):
            db.execute("INSERT INTO feedback(user_id,item_ids,action,created_at) VALUES(?,?,?,?)",
                       (user_id, json.dumps(ids[index % 3:index % 3 + 3]), "like", utc_now()))
    started = time.perf_counter()
    recommendations, _ = recommend(user_id, "casual", 25.0, "Unknown", 5)
    assert recommendations
    assert time.perf_counter() - started < 2.0


def test_notebooks_embed_the_exact_shared_model_code():
    root = Path(__file__).resolve().parents[1]
    for notebook, module in (
        ("training/AURA_Outfit_Compatibility_Polyvore_Colab.ipynb", "ml/outfit_compat.py"),
        ("training/AURA_Stylist_LLM_LoRA_Colab.ipynb", "ml/stylist_prompt.py"),
        ("training/AURA_Stylist_LLM_LoRA_Colab.ipynb", "ml/outfit_compat.py"),
    ):
        cells = json.loads((root / notebook).read_text("utf-8"))["cells"]
        sources = ["".join(cell["source"]) for cell in cells if cell["cell_type"] == "code"]
        expected = (root / module).read_text("utf-8")
        header = f"%%writefile aura_ml/{Path(module).name}\n"
        assert any(source == header + expected for source in sources), (notebook, module)


def test_real_cnn_returns_embedding_and_reads_phone_rotation(tmp_path):
    pytest.importorskip("tensorflow")
    if not settings.model_path.is_file():
        pytest.skip("garment CNN artifact not present")
    from PIL import Image
    from services.vision_service import vision_service

    upright = Image.new("RGB", (120, 240), (20, 30, 120))
    upright.paste((240, 240, 240), (0, 0, 120, 60))
    upright_path = tmp_path / "upright.jpg"
    upright.save(upright_path)
    # Same photo stored sideways with EXIF orientation 6 (rotate 90 CW on display).
    sideways = upright.rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 6
    sideways_path = tmp_path / "sideways.jpg"
    sideways.save(sideways_path, exif=exif.tobytes())

    prediction = vision_service.predict(upright_path)
    assert len(prediction["embedding"]) == 512
    assert set(prediction) >= {"product_type", "garment_group", "color_group", "category", "embedding"}
    a = np.asarray(vision_service.embed(upright_path))
    b = np.asarray(vision_service.embed(sideways_path))
    cosine = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    assert cosine > 0.95


def test_recommend_api_returns_stylist_choice(monkeypatch):
    from io import BytesIO
    from fastapi.testclient import TestClient
    from PIL import Image
    from main import app
    from services.vision_service import vision_service

    def prediction(product, garment, color, category):
        value = lambda label: {"label": label, "confidence": 0.95, "top_3": [{"label": label, "confidence": 0.95}]}
        return {"product_type": value(product), "garment_group": value(garment), "color_group": value(color),
                "category": category, "embedding": [0.01] * 512}

    uploads = iter([
        prediction("Shirt", "Garment Upper body", "White", "Top"),
        prediction("Blouse", "Blouses", "Pink", "Top"),
        prediction("Trousers", "Garment Lower body", "Black", "Bottom"),
        prediction("Sneakers", "Shoes", "White", "Footwear"),
    ])
    monkeypatch.setattr(vision_service, "predict", lambda _: next(uploads))
    fake = _use_fake_llm(monkeypatch, '{"choice": 2, "reason": "The pink blouse with black trousers feels right for a date."}')
    with TestClient(app) as client:
        account = client.post("/auth/signup", json={"full_name": "Stylist Test", "email": f"s{uuid.uuid4().hex[:6]}@example.com", "password": "secure-pass-123"})
        user_id, token = account.json()["user"]["id"], account.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        client.patch("/users/me", headers=auth, json={"bodyShape": "pear", "skinTone": "olive", "heightCm": 160})
        buffer = BytesIO(); Image.new("RGB", (32, 32)).save(buffer, format="JPEG")
        for _ in range(4):
            response = client.post("/wardrobe/upload", headers=auth, data={"user_id": user_id},
                                   files={"file": ("x.jpg", buffer.getvalue(), "image/jpeg")})
            assert response.status_code == 201, response.text
        response = client.post("/recommend", headers=auth, json={"user_id": user_id, "occasion": "date", "limit": 3})
        assert response.status_code == 200, response.text
        body = response.json()
        first = body["recommendations"][0]
        assert first["explanation_source"] == "stylist_llm"
        assert "pink" in first["explanation"].lower()
        assert any(item["subcategory"] == "Blouse" for item in first["items"])
        prompt = json.loads(fake.calls[0]["prompt"])
        assert prompt["body_shape"] == "pear" and prompt["skin_tone"] == "olive"
        assert prompt["weather"]["temperature_c"] is None  # no weather supplied
        assert client.get("/models/stylist/status").json()["source"] == "test_double"
        assert "available" in client.get("/models/outfit-compatibility/status").json()


def test_rainy_weather_with_unrecorded_fabric_does_not_crash():
    # Regression: weather_score called None.lower() when it rained and fabric was unrecorded.
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    _seed_wardrobe(user_id)
    recommendations, _ = recommend(user_id, "meeting", 18.0, "Rain", 3)
    assert recommendations
