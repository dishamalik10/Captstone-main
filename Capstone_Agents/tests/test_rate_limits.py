"""ENGINEERING_PLAN 4.1: rate limits on logins, sign-ups, chat, outfits, uploads and sockets."""
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from database import connection, init_database
from main import app
from services import rate_limits
from services.rate_limits import Limit, RateLimited
from settings import settings
from tests.test_realtime import account, jpeg, next_event, open_socket

pytestmark = pytest.mark.usefixtures("remove_new_listings")

PASSWORD = "secure-pass-123"


@pytest.fixture(autouse=True)
def limits_on():
    init_database()
    with connection() as db:
        db.execute("DELETE FROM rate_events")
    previous = settings.rate_limits_enabled
    object.__setattr__(settings, "rate_limits_enabled", True)  # frozen settings dataclass
    yield
    object.__setattr__(settings, "rate_limits_enabled", previous)


def _email(tag):
    return f"rl-{tag}-{uuid.uuid4().hex[:6]}@example.com"


def _signup(client, email, ip):
    return client.post("/auth/signup", headers={"CF-Connecting-IP": ip},
                       json={"full_name": "Limit Test", "email": email, "password": PASSWORD})


def test_five_failed_logins_lock_the_account_for_fifteen_minutes():
    with TestClient(app) as client:
        email = _email("login")
        assert _signup(client, email, "10.0.0.1").status_code == 201
        other = _email("login-other")
        assert _signup(client, other, "10.0.0.1").status_code == 201
        for _ in range(5):
            assert client.post("/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
        locked = client.post("/auth/login", json={"email": email.upper(), "password": PASSWORD})
        assert locked.status_code == 429
        assert 0 < int(locked.headers["Retry-After"]) <= 15 * 60
        assert client.post("/auth/login", json={"email": other, "password": PASSWORD}).status_code == 200


def test_successful_logins_do_not_count():
    with TestClient(app) as client:
        email = _email("ok")
        _signup(client, email, "10.0.0.2")
        for _ in range(8):
            assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def test_five_signups_per_ip_per_day():
    with TestClient(app) as client:
        for n in range(5):
            assert _signup(client, _email(f"s{n}"), "203.0.113.9").status_code == 201
        assert _signup(client, _email("s6"), "203.0.113.9").status_code == 429
        assert _signup(client, _email("other-ip"), "203.0.113.10").status_code == 201


@pytest.mark.parametrize("method,path,bucket,body", [
    ("post", "/chat/messages", "chat", {"json": {"content": "hi"}}),
    ("post", "/recommend", "recommend", {"json": {"user_id": "USER", "occasion": "casual"}}),
    ("post", "/wardrobe/upload", "upload", {"data": {"user_id": "USER"}, "files": {"file": ("a.jpg", b"x", "image/png")}}),
    ("post", "/wardrobe/purchase-impact", "upload", {"files": {"file": ("a.jpg", b"x", "image/png")}}),
    ("post", "/avatar", "upload", {"files": {"file": ("a.jpg", b"x", "text/plain")}}),
    ("post", "/marketplace/listings", "upload", {"data": {"title": "t", "price": "5", "category": "tops", "condition": "good"}}),
    ("post", "/wardrobe/import-link", "link_import", {"json": {"user_id": "USER", "url": "http://127.0.0.1/x"}}),
    ("post", "/wardrobe/USER/missing/remove-model", "upload", {}),
])
def test_each_limited_route_returns_429_once_its_limit_is_used(monkeypatch, method, path, bucket, body):
    monkeypatch.setitem(rate_limits.LIMITS, bucket, Limit(1, 3600, "Limit reached."))
    with TestClient(app) as client:
        user_id, _, auth = account(client, "Limited", _email("route"))
        path = path.replace("USER", user_id)
        kwargs = {key: ({k: (user_id if v == "USER" else v) for k, v in value.items()} if key in {"json", "data"} else value)
                  for key, value in body.items()}
        first = getattr(client, method)(path, headers=auth, **kwargs)
        assert first.status_code != 429, first.text
        second = getattr(client, method)(path, headers=auth, **kwargs)
    assert second.status_code == 429 and second.json() == {"detail": "Limit reached."}
    assert second.headers["Retry-After"]


def test_events_leave_the_window():
    rate_limits.LIMITS["test"] = Limit(2, 60, "x")
    try:
        rate_limits.hit("test", "k", now=1000)
        rate_limits.hit("test", "k", now=1010)
        with pytest.raises(RateLimited) as limited:
            rate_limits.hit("test", "k", now=1020)
        assert limited.value.retry_after == 40
        rate_limits.hit("test", "k", now=1061)  # the first event has expired
    finally:
        del rate_limits.LIMITS["test"]


def test_concurrent_requests_cannot_slip_under_the_limit():
    rate_limits.LIMITS["test"] = Limit(5, 3600, "x")
    results = []
    try:
        threads = [threading.Thread(target=lambda: results.append(_try_hit())) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        del rate_limits.LIMITS["test"]
    assert results.count(True) == 5


def _try_hit():
    try:
        rate_limits.hit("test", "race")
        return True
    except RateLimited:
        return False


def test_cf_connecting_ip_is_used_when_present():
    assert rate_limits.client_ip({"cf-connecting-ip": "198.51.100.7"}, "127.0.0.1") == "198.51.100.7"
    assert rate_limits.client_ip({}, "127.0.0.1") == "127.0.0.1"


def test_at_most_three_sockets_per_user():
    with TestClient(app) as client:
        _, token, _ = account(client, "Sockets", _email("ws"))
        opened = [open_socket(client, token) for _ in range(3)]
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "error"
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4429
        opened[0][0].__exit__(None, None, None)
        socket, _, _ = open_socket(client, token)  # a slot is free again
        for entry in [socket, *(o[0] for o in opened[1:])]:
            entry.__exit__(None, None, None)


def test_typing_events_are_throttled():
    with TestClient(app) as client:
        _, seller_token, seller = account(client, "T Seller", _email("ts"))
        _, buyer_token, buyer = account(client, "T Buyer", _email("tb"))
        product = client.post("/marketplace/listings", headers=seller, data={
            "title": "Shirt", "price": "800", "category": "tops", "condition": "good"},
            files=[("files", ("a.jpg", jpeg(), "image/jpeg"))]).json()
        conversation = client.post("/marketplace/conversations", headers=buyer, json={"product_id": product["id"]}).json()
        seller_socket, seller_ws, _ = open_socket(client, seller_token)
        buyer_socket, buyer_ws, _ = open_socket(client, buyer_token)
        next_event(seller_ws, "presence")
        for _ in range(5):
            buyer_ws.send_json({"type": "typing", "conversationId": conversation["id"]})
        buyer_ws.send_json({"type": "ping"})
        assert next_event(buyer_ws, "pong")  # the buyer's socket has handled all five
        client.post(f"/marketplace/conversations/{conversation['id']}/messages", headers=buyer, json={"body": "hi"})
        assert seller_ws.receive_json()["type"] == "typing"
        assert seller_ws.receive_json()["type"] == "message", "only one typing notice should be relayed"
        buyer_socket.__exit__(None, None, None)
        seller_socket.__exit__(None, None, None)
