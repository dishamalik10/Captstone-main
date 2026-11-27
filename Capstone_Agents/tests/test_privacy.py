"""ENGINEERING_PLAN 4.3: body-data minimisation and account deletion."""
import pytest
import json
import uuid
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from database import connection, init_database, row, rows, utc_now
from main import app
from services import body_analysis as ba
from services import tryon_service
from services.account_service import DELETED_USER_ID
from services.vision_service import vision_service
from settings import settings
from tests.test_virtual_tryon import needs_cv2, synthetic_person

pytestmark = pytest.mark.usefixtures("remove_new_listings")

PASSWORD = "secure-pass-123"


def jpeg(colour=(120, 120, 120), size=(64, 64)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def signup(client, tag):
    body = client.post("/auth/signup", json={"full_name": f"Privacy {tag}", "email": f"pv-{tag}-{uuid.uuid4().hex[:6]}@example.com",
                                             "password": PASSWORD}).json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['token']}"}


def _prediction(_):
    value = {"label": "Shirt", "confidence": 0.9, "top_3": [{"label": "Shirt", "confidence": 0.9}]}
    return {"product_type": value, "garment_group": value, "color_group": {**value, "label": "Blue"},
            "category": "Top", "embedding": [0.01] * 512}


@needs_cv2
def test_avatar_keeps_no_parsing_map_or_landmarks(monkeypatch):
    monkeypatch.setattr(ba, "parse_photo", lambda image: synthetic_person())
    init_database()
    tryon_service.init_tables()
    user_id = f"pv_{uuid.uuid4().hex[:8]}"
    from database import ensure_user
    ensure_user(user_id)
    before = {p.name for p in settings.upload_dir.glob("parsing_*")}
    tryon_service.create_avatar(user_id, Image.new("RGB", (600, 1000), "white"))
    record = row("SELECT * FROM avatars WHERE user_id=?", (user_id,))
    assert record["parsing_path"] == "" and json.loads(record["landmarks_json"]) == []
    assert {p.name for p in settings.upload_dir.glob("parsing_*")} == before
    # The render rebuilds them from the avatar image.
    parsing, landmarks = tryon_service.avatar_body_map(Image.open(settings.upload_dir / record["avatar_path"]))
    assert parsing.ndim == 2 and landmarks.shape == (33, 3)


def test_existing_parsing_maps_are_deleted_on_upgrade():
    init_database()
    tryon_service.init_tables()
    user_id = f"pv_{uuid.uuid4().hex[:8]}"
    from database import ensure_user
    ensure_user(user_id)
    parsing_file = settings.upload_dir / f"parsing_{uuid.uuid4().hex}.png"
    Image.new("L", (8, 8)).save(parsing_file)
    with connection() as db:
        db.execute(
            "INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at) "
            "VALUES (?,?,?,?,?,?,?,1,?)",
            (f"avatar_{uuid.uuid4().hex[:8]}", user_id, "front", "a.png", parsing_file.name, "[[1,2,0.9]]", "{}", utc_now()),
        )
    tryon_service.init_tables()
    record = row("SELECT parsing_path, landmarks_json FROM avatars WHERE user_id=?", (user_id,))
    assert record == {"parsing_path": "", "landmarks_json": "[]"}
    assert not parsing_file.exists()


def test_delete_account_needs_the_password():
    with TestClient(app) as client:
        _, auth = signup(client, "pw")
        response = client.post("/auth/delete-account", headers=auth, json={"password": "wrong-password"})
        assert response.status_code == 403
        assert client.get("/auth/me", headers=auth).status_code == 200


def test_delete_account_removes_everything_and_anonymises_orders(monkeypatch):
    monkeypatch.setattr(vision_service, "predict", _prediction)
    monkeypatch.setattr(ba, "parse_photo", lambda image: synthetic_person())
    with TestClient(app) as client:
        user_id, auth = signup(client, "gone")
        seller_id, seller = signup(client, "seller")
        buyer_id, buyer = signup(client, "buyer")
        item = client.post("/wardrobe/upload", headers=auth, data={"user_id": user_id},
                           files={"file": ("a.jpg", jpeg(), "image/jpeg")}).json()
        item_file = settings.upload_dir / Path_name(row("SELECT image_path FROM clothing_items WHERE item_id=?", (item["item_id"],))["image_path"])
        assert item_file.exists()
        # The leaving user bought from the seller, and sold a jacket to the buyer.
        theirs = client.post("/marketplace/listings", headers=seller, data={"title": "Seller tee", "price": "300", "category": "tops", "condition": "good"},
                             files=[("files", ("t.jpg", jpeg(), "image/jpeg"))]).json()
        mine = client.post("/marketplace/listings", headers=auth, data={"title": "My jacket", "price": "900", "category": "outerwear", "condition": "good"},
                           files=[("files", ("j.jpg", jpeg(), "image/jpeg"))]).json()
        unsold = client.post("/marketplace/listings", headers=auth, data={"title": "Unsold", "price": "100", "category": "tops", "condition": "good"},
                             files=[("files", ("u.jpg", jpeg(), "image/jpeg"))]).json()
        address = {"name": "Leaving Person", "phone": "9999999999", "line1": "1 Road", "city": "Pune", "pincode": "411001"}
        bought = client.post("/marketplace/orders", headers=auth, json={"product_ids": [theirs["id"]], "shipping_address": address})
        assert bought.status_code == 201, bought.text
        sold = client.post("/marketplace/orders", headers=buyer, json={"product_ids": [mine["id"]]})
        assert sold.status_code == 201, sold.text
        shipped = client.post(f"/marketplace/orders/{sold.json()['order_ids'][0]}/status", headers=auth, json={"status": "shipped"})
        assert shipped.status_code == 200, shipped.text
        client.post("/chat/messages", headers=auth, json={"content": "hello"})

        listing_files = [settings.upload_dir / "marketplace" / Path_name(url) for url in mine["imageUrls"] + unsold["imageUrls"]]
        assert all(path.exists() for path in listing_files)

        assert client.post("/auth/delete-account", headers=auth, json={"password": PASSWORD}).status_code == 204
        assert client.get("/auth/me", headers=auth).status_code == 401
        assert client.post("/auth/login", json={"email": "x", "password": PASSWORD}).status_code == 401

        assert row("SELECT 1 FROM users WHERE user_id=?", (user_id,)) is None
        for table, column in [("clothing_items", "user_id"), ("chat_messages", "user_id"), ("sessions", "user_id"),
                              ("avatars", "user_id"), ("products", "seller_id"), ("orders", "buyer_id"), ("orders", "seller_id")]:
            assert rows(f"SELECT 1 FROM {table} WHERE {column}=?", (user_id,)) == [], table
        assert not item_file.exists()
        assert not any(path.exists() for path in listing_files)

        # The seller's order history survives without the leaver's address; the pending order
        # was cancelled and the tee is back on sale.
        seller_order = row("SELECT * FROM orders WHERE product_id=?", (theirs["id"],))
        assert seller_order["buyer_id"] == DELETED_USER_ID and seller_order["shipping_address"] is None
        assert seller_order["status"] == "cancelled"
        assert row("SELECT status FROM products WHERE product_id=?", (theirs["id"],))["status"] == "active"
        # The buyer still sees their shipped jacket order, from a deleted seller, with no photos.
        buyer_order = row("SELECT * FROM orders WHERE product_id=?", (mine["id"],))
        assert buyer_order["seller_id"] == DELETED_USER_ID and buyer_order["status"] == "shipped"
        assert row("SELECT image_urls, status FROM products WHERE product_id=?", (mine["id"],)) == {"image_urls": "[]", "status": "paused"}
        assert row("SELECT 1 FROM products WHERE product_id=?", (unsold["id"],)) is None
        assert client.get("/marketplace/orders/mine", headers=buyer).status_code == 200
        # The placeholder can never be signed into.
        assert row("SELECT password_hash, email FROM users WHERE user_id=?", (DELETED_USER_ID,)) == {"password_hash": None, "email": None}


def Path_name(value: str) -> str:
    from pathlib import Path
    return Path(value).name


def test_web_sessions_last_seven_days_and_app_sessions_thirty():
    from datetime import datetime, timezone
    with TestClient(app) as client:
        email = f"pv-sess-{uuid.uuid4().hex[:6]}@example.com"
        web = client.post("/auth/signup", json={"full_name": "Web User", "email": email, "password": PASSWORD, "client": "web"}).json()
        native = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
    def days_left(token):
        import hashlib
        expires = row("SELECT expires_at FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))["expires_at"]
        return (datetime.fromisoformat(expires) - datetime.now(timezone.utc)).days
    assert days_left(web["token"]) == 6 and days_left(native["token"]) == 29


def test_log_out_of_all_devices():
    with TestClient(app) as client:
        email = f"pv-all-{uuid.uuid4().hex[:6]}@example.com"
        first = client.post("/auth/signup", json={"full_name": "Many Devices", "email": email, "password": PASSWORD}).json()["token"]
        second = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
        assert client.post("/auth/logout-all", headers={"Authorization": f"Bearer {first}"}).status_code == 204
        for token in (first, second):
            assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_operator_password_reset_replaces_password_and_ends_sessions():
    from scripts.reset_password import reset

    client = TestClient(app)
    email = f"reset-{uuid.uuid4().hex[:6]}@example.com"
    body = client.post("/auth/signup", json={"full_name": "Reset Me", "email": email, "password": PASSWORD}).json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    new_password = reset(email.upper())
    assert new_password and new_password != PASSWORD
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": new_password}).status_code == 200
    assert reset("nobody@example.com") is None
