"""Marketplace holds: 72 h reservation, open-order limit, guarded status changes (M15, Q16)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from database import connection, ensure_user, init_database, row
from services import marketplace_service as market
from services.marketplace_service import MarketplaceError


def _user(prefix):
    user_id = f"{prefix}_{uuid.uuid4().hex[:8]}"
    ensure_user(user_id)
    return user_id


def _listing(seller_id, title="Hold test kurta"):
    return market.create_listing(seller_id, {
        "title": title, "price": 500, "category": "tops", "condition": "good",
        "description": "", "size": "M", "brand": "", "image_urls": ["https://example.com/k.jpg"],
    })["id"]


@pytest.fixture(autouse=True)
def _db():
    """Listings made here are removed afterwards: other tests assert exact browse results."""
    init_database()
    before = {r["product_id"] for r in market.rows("SELECT product_id FROM products")}
    yield
    with connection() as db:
        created = [r["product_id"] for r in db.execute("SELECT product_id FROM products").fetchall()
                   if r["product_id"] not in before]
        for product_id in created:
            db.execute("DELETE FROM orders WHERE product_id=?", (product_id,))
            db.execute("DELETE FROM products WHERE product_id=?", (product_id,))


def test_order_carries_a_72_hour_hold():
    seller, buyer = _user("seller"), _user("buyer")
    order_id = market.create_order(buyer, [_listing(seller)])[0]
    order = row("SELECT created_at, reserved_until FROM orders WHERE order_id=?", (order_id,))
    held = datetime.fromisoformat(order["reserved_until"]) - datetime.fromisoformat(order["created_at"])
    assert held == timedelta(hours=72)
    assert market.buyer_orders(buyer)[0]["reservedUntil"] == order["reserved_until"]


def test_unshipped_order_is_cancelled_after_the_hold_and_the_item_relisted():
    seller, buyer = _user("seller"), _user("buyer")
    product_id = _listing(seller)
    order_id = market.create_order(buyer, [product_id])[0]
    assert market.get_product(product_id)["status"] == "sold"
    market.expire_unshipped_orders()
    assert row("SELECT status FROM orders WHERE order_id=?", (order_id,))["status"] == "pending"  # inside the hold
    later = datetime.now(timezone.utc) + timedelta(hours=73)
    assert market.expire_unshipped_orders(now=later) >= 1
    assert row("SELECT status FROM orders WHERE order_id=?", (order_id,))["status"] == "cancelled"
    assert market.get_product(product_id)["status"] == "active"
    # Another buyer can now order it.
    assert market.create_order(_user("buyer2"), [product_id])


def test_shipped_orders_are_never_expired():
    seller, buyer = _user("seller"), _user("buyer")
    product_id = _listing(seller)
    order_id = market.create_order(buyer, [product_id])[0]
    market.update_order_status(seller, order_id, "shipped")
    market.expire_unshipped_orders(now=datetime.now(timezone.utc) + timedelta(days=30))
    assert row("SELECT status FROM orders WHERE order_id=?", (order_id,))["status"] == "shipped"


def test_a_buyer_can_hold_at_most_three_unshipped_orders():
    seller, buyer = _user("seller"), _user("buyer")
    for index in range(market.MAX_OPEN_ORDERS_PER_BUYER):
        market.create_order(buyer, [_listing(seller, f"Item {index}")])
    fourth = _listing(seller, "Item 4")
    with pytest.raises(MarketplaceError, match="at most 3 unshipped") as refused:
        market.create_order(buyer, [fourth])
    assert refused.value.status == 409
    assert market.get_product(fourth)["status"] == "active"  # the refused order reserved nothing


def test_a_basket_that_would_exceed_the_limit_reserves_nothing():
    seller, buyer = _user("seller"), _user("buyer")
    market.create_order(buyer, [_listing(seller, "Already held")])
    basket = [_listing(seller, f"Basket {index}") for index in range(3)]
    with pytest.raises(MarketplaceError):
        market.create_order(buyer, basket)
    assert all(market.get_product(p)["status"] == "active" for p in basket)


def test_status_change_is_refused_if_the_order_changed_underneath():
    seller, buyer = _user("seller"), _user("buyer")
    product_id = _listing(seller)
    order_id = market.create_order(buyer, [product_id])[0]
    stale = dict(row("SELECT * FROM orders WHERE order_id=?", (order_id,)))
    # The buyer cancels while the seller's screen still shows "pending".
    market.update_order_status(buyer, order_id, "cancelled")
    original_row = market.row

    def stale_read(sql, params=()):
        return stale if "FROM orders WHERE order_id=?" in sql and params == (order_id,) else original_row(sql, params)

    market.row = stale_read
    try:
        with pytest.raises(MarketplaceError) as refused:
            market.update_order_status(seller, order_id, "shipped")
    finally:
        market.row = original_row
    assert refused.value.status == 409
    assert row("SELECT status FROM orders WHERE order_id=?", (order_id,))["status"] == "cancelled"


def test_legacy_pending_orders_get_a_hold_on_startup():
    seller, buyer = _user("seller"), _user("buyer")
    order_id = market.create_order(buyer, [_listing(seller)])[0]
    created = "2026-01-01T10:00:00+00:00"
    with connection() as db:
        db.execute("UPDATE orders SET created_at=?, reserved_until=NULL WHERE order_id=?", (created, order_id))
    init_database()
    assert row("SELECT reserved_until FROM orders WHERE order_id=?", (order_id,))["reserved_until"] == "2026-01-04T10:00:00+00:00"
