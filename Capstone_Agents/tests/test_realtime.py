from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from main import app


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 32), (90, 90, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


def account(client, name, email):
    response = client.post("/auth/signup", json={"full_name": name, "email": email, "password": "secure-pass-123"})
    body = response.json()
    return body["user"]["id"], body["token"], {"Authorization": f"Bearer {body['token']}"}


def open_socket(client, token):
    socket = client.websocket_connect("/ws")
    ws = socket.__enter__()
    ws.send_json({"type": "auth", "token": token})
    ready = ws.receive_json()
    assert ready["type"] == "ready"
    return socket, ws, ready


def next_event(ws, kind):
    for _ in range(10):
        event = ws.receive_json()
        if event["type"] == kind:
            return event
    raise AssertionError(f"no {kind} event")


def test_socket_requires_auth_message():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "not-a-real-token"})
            assert ws.receive_json()["type"] == "error"
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4401


def test_live_chat_typing_read_presence_and_orders():
    with TestClient(app) as client:
        seller_id, seller_token, seller = account(client, "Live Seller", "rt-seller@example.com")
        buyer_id, buyer_token, buyer = account(client, "Live Buyer", "rt-buyer@example.com")
        _, stranger_token, _ = account(client, "Snoop", "rt-snoop@example.com")
        product = client.post("/marketplace/listings", headers=seller, data={
            "title": "Linen shirt", "price": "800", "category": "tops", "condition": "good"},
            files=[("files", ("a.jpg", jpeg(), "image/jpeg"))]).json()
        conversation = client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).json()
        assert conversation["otherUser"]["id"] == seller_id

        seller_socket, seller_ws, _ = open_socket(client, seller_token)
        buyer_socket, buyer_ws, ready = open_socket(client, buyer_token)
        assert ready["online"] == [seller_id]                          # buyer sees seller is online
        assert next_event(seller_ws, "presence") == {"type": "presence", "userId": buyer_id, "online": True}
        listed = client.get("/marketplace/conversations", headers=buyer).json()["conversations"][0]
        assert listed["otherUser"]["online"] is True

        # Typing indicator is relayed only to the other member.
        buyer_ws.send_json({"type": "typing", "conversationId": conversation["id"]})
        assert next_event(seller_ws, "typing") == {"type": "typing", "conversationId": conversation["id"], "userId": buyer_id}

        # A message sent over REST arrives on the seller's socket instantly.
        sent = client.post(f"/marketplace/conversations/{conversation['id']}/messages", headers=buyer, json={"body": "Hi! Still available?"}).json()
        pushed = next_event(seller_ws, "message")
        assert pushed["conversationId"] == conversation["id"]
        assert pushed["message"]["id"] == sent["id"] and pushed["message"]["mine"] is False
        assert next_event(buyer_ws, "message")["message"]["mine"] is True  # sender's other tabs

        # Seller opens the thread -> buyer gets a read receipt.
        client.get(f"/marketplace/conversations/{conversation['id']}", headers=seller)
        assert next_event(buyer_ws, "read") == {"type": "read", "conversationId": conversation["id"]}

        # Someone outside the conversation cannot inject typing events.
        snoop_socket, snoop_ws, _ = open_socket(client, stranger_token)
        snoop_ws.send_json({"type": "typing", "conversationId": conversation["id"]})
        snoop_ws.send_json({"type": "ping"})
        assert snoop_ws.receive_json() == {"type": "pong"}
        snoop_socket.__exit__(None, None, None)

        # Orders notify the other party live.
        order_id = client.post("/marketplace/orders", headers=buyer, json={"product_ids": [product["id"]]}).json()["order_ids"][0]
        placed = next_event(seller_ws, "order")
        assert placed["event"] == "placed" and placed["orderId"] == order_id and placed["productTitle"] == "Linen shirt"
        client.post(f"/marketplace/orders/{order_id}/status", headers=seller, json={"status": "shipped"})
        assert next_event(buyer_ws, "order")["event"] == "shipped"

        # Buyer disconnects -> seller sees them go offline.
        buyer_socket.__exit__(None, None, None)
        assert next_event(seller_ws, "presence") == {"type": "presence", "userId": buyer_id, "online": False}
        seller_socket.__exit__(None, None, None)
