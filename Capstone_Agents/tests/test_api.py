import os
import tempfile
from io import BytesIO

os.environ["AURA_DATABASE_PATH"] = str(
    (tempfile.mkdtemp(prefix="aura-test-") + "/test.db")
)
os.environ["AURA_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="aura-uploads-")

from fastapi.testclient import TestClient
from PIL import Image

from main import app
from services.vision_service import vision_service


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), (230, 230, 230)).save(buffer, format="JPEG")
    return buffer.getvalue()


def prediction(product: str, garment: str, color: str, category: str):
    def value(label: str):
        return {
            "label": label,
            "confidence": 0.95,
            "top_3": [{"label": label, "confidence": 0.95}],
        }

    return {
        "product_type": value(product),
        "garment_group": value(garment),
        "color_group": value(color),
        "category": category,
        "color_sample": {"rgb": [230, 230, 230], "hex": "#E6E6E6", "method": "test_fixture"},
    }


def test_complete_wardrobe_recommendation_flow(monkeypatch):
    predictions = iter(
        [
            prediction("Shirt", "Garment Upper body", "White", "Top"),
            prediction("Trousers", "Garment Lower body", "Black", "Bottom"),
            prediction("Sneakers", "Shoes", "White", "Footwear"),
        ]
    )
    monkeypatch.setattr(vision_service, "predict", lambda _: next(predictions))

    with TestClient(app) as client:
        account = client.post("/auth/signup", json={"full_name":"Wardrobe Owner", "email":"wardrobe-owner@example.com", "password":"secure-pass-123"})
        assert account.status_code == 201, account.text
        user_id = account.json()["user"]["id"]
        auth = {"Authorization": f"Bearer {account.json()['token']}"}
        preference = client.put(
            f"/users/{user_id}/preferences",
            headers=auth,
            json={
                "preferred_colors": ["Black", "White"],
                "preferred_styles": ["Minimal"],
            },
        )
        assert preference.status_code == 200

        for _ in range(3):
            response = client.post(
                "/wardrobe/upload",
                headers=auth,
                data={"user_id": user_id},
                files={"file": ("item.jpg", image_bytes(), "image/jpeg")},
            )
            assert response.status_code == 201, response.text

        wardrobe = client.get(f"/wardrobe/{user_id}", headers=auth)
        assert wardrobe.status_code == 200
        assert len(wardrobe.json()) == 3
        assert wardrobe.json()[0]["color_sample"]["hex"] == "#E6E6E6"

        recommendation = client.post(
            "/recommend",
            headers=auth,
            json={
                "user_id": user_id,
                "occasion": "meeting",
                "temperature_c": 24,
                "condition": "Clear",
            },
        )
        assert recommendation.status_code == 200, recommendation.text
        result = recommendation.json()["recommendations"][0]
        assert len(result["item_ids"]) == 3
        assert set(result["item_ids"]).issubset(
            {item["item_id"] for item in wardrobe.json()}
        )
        assert 0 <= result["compatibility_score"] <= 100
        image_url = wardrobe.json()[0]["image_url"]
        assert client.get(image_url).status_code == 200
        assert client.get(image_url.replace("signature=", "signature=0")).status_code == 404
        trace = recommendation.json()["agent_trace"]
        assert trace["plan"]["intent"] == "outfit_recommendation"
        assert "fashion_critic" in trace["plan"]["tools"]
        assert "owned_items_only" in trace["guardrails"]
        from database import rows
        impression = rows(
            "SELECT run_id,rank_position FROM recommendations WHERE recommendation_id=?",
            (result["recommendation_id"],),
        )[0]
        assert impression["run_id"]
        assert impression["rank_position"] == 1

        feedback = client.post(
            "/feedback",
            headers=auth,
            json={
                "user_id": user_id,
                "recommendation_id": result["recommendation_id"],
                "item_ids": result["item_ids"],
                "action": "wear",
            },
        )
        assert feedback.status_code == 201
        for action in ("like", "save", "dislike"):
            signal = client.post(
                "/feedback", headers=auth,
                json={"user_id": user_id, "recommendation_id": result["recommendation_id"],
                      "item_ids": result["item_ids"], "action": action},
            )
            assert signal.status_code == 201, signal.text
        alternatives = client.post(
            "/recommend", headers=auth,
            json={"user_id": user_id, "occasion":"meeting", "limit":5,
                  "exclude_recommendation_ids":[result["recommendation_id"]]},
        )
        assert alternatives.status_code == 422
        assert "No new outfit combinations" in alternatives.json()["detail"]
        invalid_feedback = client.post(
            "/feedback",
            headers=auth,
            json={
                "user_id": user_id,
                "recommendation_id": result["recommendation_id"],
                "item_ids": ["unowned-item"],
                "action": "like",
            },
        )
        assert invalid_feedback.status_code == 422


def test_private_wardrobe_routes_require_authentication_and_owner():
    with TestClient(app) as client:
        one = client.post("/auth/signup", json={"full_name":"One", "email":"one-owner@example.com", "password":"secure-pass-123"})
        two = client.post("/auth/signup", json={"full_name":"Two", "email":"two-owner@example.com", "password":"secure-pass-456"})
        id_one = one.json()["user"]["id"]
        auth_two = {"Authorization": f"Bearer {two.json()['token']}"}
        public = client.get(f"/users/{id_one}").json()
        assert "email" not in public
        assert "skinTone" not in public and "heightCm" not in public and "topSize" not in public
        assert client.get(f"/wardrobe/{id_one}").status_code == 401
        assert client.get(f"/users/{id_one}/preferences").status_code == 401
        assert client.post("/recommend", json={"user_id":id_one,"occasion":"casual"}).status_code == 401
        assert client.post("/feedback", json={"user_id":id_one,"item_ids":[],"action":"like"}).status_code == 401
        assert client.get(f"/wardrobe/{id_one}", headers=auth_two).status_code == 403
        assert client.get(f"/users/{id_one}/preferences", headers=auth_two).status_code == 403
        assert client.put(f"/users/{id_one}/preferences", headers=auth_two, json={"preferred_colors":["Red"]}).status_code == 403
        assert client.post("/wardrobe/upload", headers=auth_two, data={"user_id":id_one}, files={"file":("item.jpg", image_bytes(), "image/jpeg")}).status_code == 403
        assert client.post("/recommend", headers=auth_two, json={"user_id":id_one,"occasion":"casual"}).status_code == 403


def test_scratch_fashion_model_status_is_exposed_without_loading_weights():
    with TestClient(app) as client:
        status = client.get("/models/fashion-language/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["engine"] == "AURA scratch fashion GPT"
        assert payload["role"].startswith("explanation only")
        assert payload["ready"] is False
        health = client.get("/health").json()
        assert "fashion_lm" in health


def test_authored_fashion_guidance_retrieval_is_local_and_labeled():
    from services.fashion_knowledge import knowledge_metadata, retrieve_guidance
    metadata = knowledge_metadata()
    assert "not model training data" in metadata["provenance"]
    assert "Mixed" in metadata["license"]
    from services.fashion_knowledge import source_registry
    assert {
        "gray2014_color_coordination", "rmit2023_colour_theory",
        "apple2023_apparel_production", "reddybest2020_dress_diversity",
    } <= {entry["id"] for entry in source_registry()}
    assert retrieve_guidance("smart casual office meeting")
    assert retrieve_guidance("pattern stripes")


def test_local_explainer_cannot_change_server_selected_items(monkeypatch):
    from services import recommendation_explainer as explainer
    owned = {"recommendation_id":"rec-1", "item_ids":["owned-top"],
             "items":[{"item_id":"owned-top", "category":"Top", "subcategory":"Shirt", "color_name":"Black"}],
             "compatibility_score":90, "explanation":"Rule rationale"}
    monkeypatch.setattr(explainer, "get_model_info", lambda: {"present":True})
    monkeypatch.setattr(explainer, "generate_response", lambda *a, **k: '{"comparison":"The first option has the strongest palette signal, while the second has a different tradeoff."}')
    result = explainer.explain_recommendations([owned], occasion="casual", temperature=22, condition="Clear")
    assert result["recommendations"][0]["item_ids"] == ["owned-top"]
    assert result["comparison_source"] == "rules"  # one outfit cannot be compared
    assert "Black" in result["recommendations"][0]["explanation"]
    assert "details are missing" in result["recommendations"][0]["explanation"]

    second = {**owned, "recommendation_id":"rec-2", "item_ids":["owned-top", "owned-shoe"],
              "items":owned["items"] + [{"item_id":"owned-shoe", "category":"Footwear", "subcategory":"Sneakers", "color_name":"White"}],
              "component_scores":{"color":80, "occasion":70}}
    result = explainer.explain_recommendations([owned, second], occasion="casual", temperature=22, condition="Clear")
    assert result["recommendations"][0]["item_ids"] == ["owned-top"]
    assert result["comparison_source"] == "local_llm"

    monkeypatch.setattr(explainer, "generate_response", lambda *a, **k: '{"comparison":"Wear a jacket with it."}')
    rejected = explainer.explain_recommendations([owned, second], occasion="casual", temperature=22, condition="Clear")
    assert rejected["recommendations"][0]["item_ids"] == ["owned-top"]
    assert rejected["comparison_source"] == "rules"
    assert "Black" in rejected["recommendations"][0]["explanation"]


def test_chat_detects_item_styling_and_returns_model_reply(monkeypatch):
    from services.app_service import _requests_outfit
    from services import llm_stylist
    assert _requests_outfit("Style my black shirt for a minimal look")
    monkeypatch.setattr(llm_stylist, "generate_response", lambda *a, **k: "Add a red jacket for contrast.")
    response = llm_stylist.stylist_reply(
        message="Style my black shirt",
        user={"fullName":"A"},
        wardrobe=[{"item_id":"owned-shirt","category":"Top","subcategory":"Shirt","color_name":"Black"}],
        recommendation={"item_ids":["owned-shirt"],"compatibility_score":80,"explanation":"Owned shirt"},
        conversation_history=[],
        wants_outfit=True,
        fallback="Use your black shirt with the selected owned items.",
    )
    assert response == "Add a red jacket for contrast."


def test_real_account_profile_marketplace_and_chat(monkeypatch):
    from services.local_llm import local_llm
    monkeypatch.setattr(local_llm, "generate_response", lambda *args, **kwargs: "Wear a polished outfit from your wardrobe.")
    with TestClient(app) as client:
        seller = client.post(
            "/auth/signup",
            json={"full_name": "Real Seller", "email": "seller@example.com", "password": "secure-pass-123"},
        )
        assert seller.status_code == 201, seller.text
        seller_auth = {"Authorization": f"Bearer {seller.json()['token']}"}

        profile = client.patch(
            "/users/me",
            headers=seller_auth,
            json={"location": "Delhi", "stylePreferences": ["minimalist"], "profileComplete": True},
        )
        assert profile.status_code == 200
        assert profile.json()["location"] == "Delhi"

        product = client.post(
            "/marketplace/products",
            headers=seller_auth,
            json={
                "title": "Real Jacket", "price": 1499, "image_urls": ["https://example.com/jacket.jpg"],
                "category": "outerwear", "condition": "good", "description": "One owner jacket",
            },
        )
        assert product.status_code == 201, product.text

        buyer = client.post(
            "/auth/signup",
            json={"full_name": "Real Buyer", "email": "buyer@example.com", "password": "secure-pass-456"},
        )
        buyer_auth = {"Authorization": f"Bearer {buyer.json()['token']}"}
        order = client.post(
            "/marketplace/orders",
            headers=buyer_auth,
            json={"product_ids": [product.json()["id"]]},
        )
        assert order.status_code == 201, order.text

        message = client.post("/chat/messages", headers=buyer_auth, json={"content": "What should I wear?"})
        assert message.status_code == 201
        assert message.json()["content"].strip()


def test_logout_returns_no_content_and_revokes_session():
    with TestClient(app) as client:
        signup = client.post(
            "/auth/signup",
            json={
                "full_name": "Logout User",
                "email": "logout@example.com",
                "password": "secure-pass-789",
            },
        )
        assert signup.status_code == 201, signup.text
        auth = {"Authorization": f"Bearer {signup.json()['token']}"}

        response = client.post("/auth/logout", headers=auth)
        assert response.status_code == 204
        assert response.content == b""
        assert client.get("/auth/me", headers=auth).status_code == 401


def test_chat_returns_clear_error_when_local_model_is_missing(monkeypatch, tmp_path):
    from dataclasses import asdict
    from services.local_llm import local_llm
    from settings import settings
    import services.local_llm as local_llm_module
    settings_values = asdict(settings)
    import services.stylist_selector as stylist_selector_module
    settings_values["llm_model_path"] = tmp_path / "missing.gguf"
    # Chat prefers the fine-tuned stylist GGUF when it is installed, so hide that one too.
    settings_values["stylist_llm_model_path"] = tmp_path / "missing-stylist.gguf"
    test_settings = type("TestSettings", (), settings_values)()
    monkeypatch.setattr(local_llm_module, "settings", test_settings)
    monkeypatch.setattr(stylist_selector_module, "settings", test_settings)
    monkeypatch.setattr(local_llm, "_model", None)
    with TestClient(app) as client:
        signup = client.post(
            "/auth/signup",
            json={"full_name": "Local Model User", "email": "local@example.com", "password": "secure-pass-999"},
        )
        auth = {"Authorization": f"Bearer {signup.json()['token']}"}
        response = client.post("/chat/messages", headers=auth, json={"content": "Hello"})
        assert response.status_code == 503
        assert "weights are missing" in response.json()["detail"]
