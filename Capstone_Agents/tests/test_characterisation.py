"""Characterisation tests for gaps found in the audit (KNOWN_ISSUES.md).

Two kinds of test live here:

- Plain tests pin behaviour that is already correct, so later fixes cannot break it.
- ``xfail(strict=True)`` tests describe the *correct* behaviour for a known bug. They
  fail today. When the fix lands they start passing, strict mode turns that into a
  failure, and the marker must be removed: so a fix cannot land without its test.
"""
from __future__ import annotations

import ipaddress
import socket
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from database import connection, init_database
from main import app
from services import marketplace_service as market
from services import product_link_service as links
from services import tryon_service
from services.marketplace_service import MarketplaceError
from services.product_link_service import ProductLinkError, import_from_link
from settings import settings

PASSWORD = "secure-pass-123"


def account(client: TestClient, name: str, email: str) -> tuple[str, dict[str, str]]:
    response = client.post("/auth/signup", json={"full_name": name, "email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()["user"]["id"], {"Authorization": f"Bearer {response.json()['token']}"}


# -- auth --------------------------------------------------------------------------------

def test_wrong_password_is_rejected_with_a_generic_message():
    with TestClient(app) as client:
        account(client, "Wrong Pass", "char-wrong-pass@example.com")
        response = client.post("/auth/login", json={"email": "char-wrong-pass@example.com", "password": "not-the-password"})
        unknown = client.post("/auth/login", json={"email": "char-nobody@example.com", "password": "not-the-password"})
    assert response.status_code == unknown.status_code == 401
    # Same message for a wrong password and an unknown email: no account enumeration.
    assert response.json() == unknown.json() == {"detail": "Invalid email or password."}


def test_expired_session_is_rejected():
    with TestClient(app) as client:
        _, auth = account(client, "Expired", "char-expired@example.com")
        assert client.get("/auth/me", headers=auth).status_code == 200
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        user_id = client.get("/auth/me", headers=auth).json()["id"]
        with connection() as db:
            db.execute("UPDATE sessions SET expires_at=? WHERE user_id=?", (past, user_id))
        assert client.get("/auth/me", headers=auth).status_code == 401


def test_duplicate_signup_is_a_conflict():
    with TestClient(app) as client:
        account(client, "First", "char-dup@example.com")
        again = client.post("/auth/signup", json={"full_name": "Second", "email": "char-dup@example.com", "password": PASSWORD})
    assert again.status_code == 409


# -- social (M3: missing targets are 404, not an IntegrityError 500) -------------------

def test_liking_a_missing_post_is_not_found():
    with TestClient(app, raise_server_exceptions=False) as client:
        _, auth = account(client, "Liker", "char-liker@example.com")
        response = client.post("/social/posts/post_does_not_exist/like", headers=auth)
    assert response.status_code == 404


def test_following_a_missing_user_is_not_found():
    with TestClient(app, raise_server_exceptions=False) as client:
        _, auth = account(client, "Follower", "char-follower@example.com")
        response = client.post("/social/users/user_does_not_exist/follow", headers=auth)
    assert response.status_code == 404


# -- marketplace (M15: unguarded "mark sold") ---------------------------------------------

def _active_product(seller_id: str) -> str:
    product = market.create_listing(seller_id, {
        "title": "Char test jacket", "price": 900, "category": "outerwear", "condition": "good",
        "description": "", "size": "M", "brand": "", "image_urls": ["https://example.com/jacket.jpg"],
    })
    return product["id"]


def test_second_sequential_order_for_a_sold_item_is_refused():
    with TestClient(app) as client:
        seller_id, _ = account(client, "Char Seller", "char-seller-seq@example.com")
        buyer_a, _ = account(client, "Char Buyer A", "char-buyer-a-seq@example.com")
        buyer_b, _ = account(client, "Char Buyer B", "char-buyer-b-seq@example.com")
    product_id = _active_product(seller_id)
    assert len(market.create_order(buyer_a, [product_id])) == 1
    with pytest.raises(MarketplaceError) as refused:
        market.create_order(buyer_b, [product_id])
    assert refused.value.status == 409


def test_two_buyers_racing_for_one_item_get_one_order(monkeypatch):
    with TestClient(app) as client:
        seller_id, _ = account(client, "Race Seller", "char-race-seller@example.com")
        buyer_a, _ = account(client, "Race Buyer A", "char-race-a@example.com")
        buyer_b, _ = account(client, "Race Buyer B", "char-race-b@example.com")
    product_id = _active_product(seller_id)
    real_connection = market.connection
    state = {"fired": False, "b_result": None}

    class RacingDb:
        """Lets buyer B's whole order run right after buyer A has read the listing."""

        def __init__(self, db: sqlite3.Connection) -> None:
            self._db = db

        def execute(self, sql: str, params=()):
            cursor = self._db.execute(sql, params)
            if "FROM products" in sql and not state["fired"]:
                state["fired"] = True
                listing = cursor.fetchone()  # A has read the listing as active...
                thread = threading.Thread(target=self._buyer_b)  # ...then B orders it
                thread.start()
                thread.join()
                return _Fetched(listing)
            return cursor

        @staticmethod
        def _buyer_b() -> None:
            try:
                state["b_result"] = market.create_order(buyer_b, [product_id])
            except Exception as exc:  # noqa: BLE001 - recorded and asserted on below
                state["b_result"] = exc

        def __getattr__(self, name):
            return getattr(self._db, name)

    class _Fetched:
        def __init__(self, record) -> None:
            self._record = record

        def fetchone(self):
            return self._record

    @contextmanager
    def racing_connection():
        with real_connection() as db:
            yield RacingDb(db)

    monkeypatch.setattr(market, "connection", racing_connection)
    try:
        market.create_order(buyer_a, [product_id])
        a_ok = True
    except MarketplaceError:
        a_ok = False
    assert state["fired"], "the race was not set up"
    assert not isinstance(state["b_result"], sqlite3.Error), f"buyer B hit a database error: {state['b_result']!r}"
    b_ok = isinstance(state["b_result"], list)
    with real_connection() as db:
        orders = db.execute("SELECT COUNT(*) FROM orders WHERE product_id=?", (product_id,)).fetchone()[0]
    assert orders == 1 and a_ok != b_ok


# -- link import (M17: DNS rebinding) ------------------------------------------------------

def test_link_import_never_connects_to_a_private_address(monkeypatch):
    for proxy in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(proxy, raising=False)
    answers = iter([
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],  # passes the check
    ])
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]  # then rebinds

    def rebinding_getaddrinfo(host, port, *args, **kwargs):
        return next(answers, private)

    connected: list[str] = []

    def record_connect(self, address):
        connected.append(address[0])
        raise ConnectionRefusedError("test: no real network")

    monkeypatch.setattr(links.socket, "getaddrinfo", rebinding_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", record_connect)
    with pytest.raises(ProductLinkError):
        import_from_link("http://rebind.example/product", 5_000_000)
    assert connected, "the fetcher should have tried to connect"
    assert all(ipaddress.ip_address(address).is_global for address in connected)


# -- schema migration --------------------------------------------------------------------

def _columns(db_path: Path) -> dict[str, set[str]]:
    db = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {table: {r[1] for r in db.execute(f"PRAGMA table_info({table})")} for table in tables}
    finally:
        db.close()


def _init_at(db_path: Path) -> None:
    previous = settings.database_path
    object.__setattr__(settings, "database_path", db_path)
    try:
        init_database()
        tryon_service.init_tables()
    finally:
        object.__setattr__(settings, "database_path", previous)


def test_database_from_the_first_audit_upgrades_to_the_current_schema(tmp_path):
    old = tmp_path / "old.db"
    db = sqlite3.connect(old)
    db.executescript((Path(__file__).parent / "fixtures" / "schema_c59a86a.sql").read_text())
    db.close()
    _init_at(old)
    fresh = tmp_path / "fresh.db"
    _init_at(fresh)
    assert _columns(old) == _columns(fresh)


def test_a_constraint_violation_the_route_missed_is_a_409_not_a_500(monkeypatch):
    from services import app_service

    def racing_insert(*args, **kwargs):
        raise sqlite3.IntegrityError("UNIQUE constraint failed: users.email")

    monkeypatch.setattr(app_service, "create_session", racing_insert)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/auth/signup", json={"full_name": "Racer", "email": "char-race-signup@example.com", "password": PASSWORD})
    assert response.status_code == 409
    assert "UNIQUE" not in response.text and "users.email" not in response.text
