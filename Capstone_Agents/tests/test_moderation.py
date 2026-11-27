"""ENGINEERING_PLAN 4.4: report and block."""
import json
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from database import connection, row
from main import app

pytestmark = pytest.mark.usefixtures("remove_new_listings")
PASSWORD = "secure-pass-123"


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 32), (90, 90, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


def account(client, tag):
    body = client.post("/auth/signup", json={"full_name": f"Mod {tag}", "email": f"mod-{tag}-{uuid.uuid4().hex[:6]}@example.com",
                                             "password": PASSWORD}).json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['token']}"}


def listing(client, auth, title="Mod jacket"):
    return client.post("/marketplace/listings", headers=auth, data={"title": title, "price": "500", "category": "outerwear",
                                                                    "condition": "good"},
                       files=[("files", ("j.jpg", jpeg(), "image/jpeg"))]).json()


def test_report_a_listing_keeps_a_snapshot_and_is_idempotent():
    with TestClient(app) as client:
        seller_id, seller = account(client, "s")
        _, reporter = account(client, "r")
        product = listing(client, seller, "Fake designer bag")
        body = {"target_type": "listing", "target_id": product["id"], "reason": "scam", "details": "Too cheap to be real"}
        assert client.post("/reports", headers=reporter, json=body).status_code == 201
        assert client.post("/reports", headers=reporter, json=body).status_code == 201
        with connection() as db:
            reports = db.execute("SELECT * FROM reports WHERE target_id=?", (product["id"],)).fetchall()
        assert len(reports) == 1
        assert reports[0]["target_owner_id"] == seller_id and reports[0]["status"] == "open"
        assert json.loads(reports[0]["snapshot_json"])["title"] == "Fake designer bag"
        # Own content, unknown content and unknown reasons are refused.
        assert client.post("/reports", headers=seller, json=body).status_code == 409
        assert client.post("/reports", headers=reporter, json={**body, "target_id": "nope"}).status_code == 404
        assert client.post("/reports", headers=reporter, json={**body, "reason": "dislike"}).status_code == 422


def test_only_members_can_report_a_conversation():
    with TestClient(app) as client:
        _, seller = account(client, "cs")
        buyer_id, buyer = account(client, "cb")
        _, stranger = account(client, "cx")
        product = listing(client, seller)
        conversation = client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).json()
        client.post(f"/marketplace/conversations/{conversation['id']}/messages", headers=buyer, json={"body": "pay me upfront"})
        body = {"target_type": "conversation", "target_id": conversation["id"], "reason": "harassment"}
        assert client.post("/reports", headers=stranger, json=body).status_code == 404
        assert client.post("/reports", headers=seller, json=body).status_code == 201
        report = row("SELECT target_owner_id, snapshot_json FROM reports WHERE target_id=?", (conversation["id"],))
        assert report["target_owner_id"] == buyer_id
        assert json.loads(report["snapshot_json"])["recent_messages"][0]["body"] == "pay me upfront"


def test_blocking_stops_messages_both_ways_and_hides_content():
    with TestClient(app) as client:
        seller_id, seller = account(client, "bs")
        buyer_id, buyer = account(client, "bb")
        product = listing(client, seller, "Blocked seller coat")
        conversation = client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).json()
        assert client.post(f"/users/{seller_id}/block", headers=buyer).status_code == 204
        assert [b["id"] for b in client.get("/users/me/blocks", headers=buyer).json()] == [seller_id]

        url = f"/marketplace/conversations/{conversation['id']}/messages"
        assert client.post(url, headers=buyer, json={"body": "hi"}).status_code == 403
        assert client.post(url, headers=seller, json={"body": "hi"}).status_code == 403  # two-way
        assert client.get("/marketplace/conversations", headers=buyer).json()["conversations"] == []
        # The blocker no longer sees the seller's listings; everyone else still does.
        assert product["id"] not in [p["id"] for p in client.get("/marketplace/products", headers=buyer).json()]
        assert product["id"] in [p["id"] for p in client.get("/marketplace/products").json()]
        assert client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).status_code in (200, 201, 403)

        assert client.delete(f"/users/{seller_id}/block", headers=buyer).status_code == 204
        assert client.post(url, headers=buyer, json={"body": "hi again"}).status_code == 201


def test_blocked_users_posts_are_hidden_from_the_feed():
    from services.app_service import create_post

    with TestClient(app) as client:
        poster_id, _ = account(client, "fp")
        _, viewer = account(client, "fv")
        post = create_post(poster_id, {"outfit_image_url": "/marketplace/images/" + "a" * 32 + ".jpg", "caption": "look"})
        assert post["id"] in [p["id"] for p in client.get("/social/feed", headers=viewer).json()]
        client.post(f"/users/{poster_id}/block", headers=viewer)
        assert post["id"] not in [p["id"] for p in client.get("/social/feed", headers=viewer).json()]


def test_cannot_block_yourself_or_nobody():
    with TestClient(app) as client:
        me, auth = account(client, "self")
        assert client.post(f"/users/{me}/block", headers=auth).status_code == 409
        assert client.post("/users/user_nobody/block", headers=auth).status_code == 404


def test_review_script_resolves_and_removes(capsys):
    from scripts import review_reports

    with TestClient(app) as client:
        _, seller = account(client, "rs")
        _, reporter = account(client, "rr")
        product = listing(client, seller, "Counterfeit")
        client.post("/reports", headers=reporter, json={"target_type": "listing", "target_id": product["id"], "reason": "prohibited_item"})
    report_id = row("SELECT report_id FROM reports WHERE target_id=?", (product["id"],))["report_id"]
    review_reports.list_open()
    assert report_id in capsys.readouterr().out
    review_reports.resolve(report_id, remove=True)
    assert row("SELECT status FROM reports WHERE report_id=?", (report_id,))["status"] == "removed"
    assert row("SELECT status FROM products WHERE product_id=?", (product["id"],))["status"] == "paused"
