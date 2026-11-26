"""Peer-to-peer marketplace: users list clothes for sale, chat with buyers, and
move orders through pending -> shipped -> completed (or cancelled).

Payment is not processed in-app: the buyer picks cash on delivery or UPI to the
seller, and the order records that choice.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from database import connection, ensure_user, row, rows, utc_now
from settings import settings

LISTING_STATUSES = {"active", "paused", "sold"}
CONDITIONS = {"new", "like_new", "good", "fair"}
CATEGORIES = {"tops", "bottoms", "dresses", "shoes", "outerwear", "accessories"}
WARDROBE_TO_LISTING = {
    "Top": "tops", "Bottom": "bottoms", "Dress": "dresses", "Footwear": "shoes",
    "Outerwear": "outerwear", "Accessory": "accessories",
}
MAX_PHOTOS = 5
IMAGE_ROUTE = "/marketplace/images/"


class MarketplaceError(ValueError):
    """User-facing reason a marketplace action was refused."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def image_dir() -> Path:
    path = settings.upload_dir / "marketplace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_listing_photo(content: bytes, suffix: str) -> str:
    name = f"{uuid.uuid4().hex}{suffix}"
    (image_dir() / name).write_bytes(content)
    return f"{IMAGE_ROUTE}{name}"


def copy_wardrobe_photo(user_id: str, item_id: str) -> tuple[str, dict[str, Any]]:
    """Copy a wardrobe item's photo into public listing storage; returns (url, item)."""
    item = row(
        "SELECT * FROM clothing_items WHERE user_id=? AND item_id=?", (user_id, item_id),
    )
    if item is None:
        raise MarketplaceError("That wardrobe item was not found.", 404)
    source = Path(item["image_path"])
    if not source.is_file():
        raise MarketplaceError("That wardrobe item's photo is missing.", 404)
    name = f"{uuid.uuid4().hex}{source.suffix or '.jpg'}"
    shutil.copyfile(source, image_dir() / name)
    return f"{IMAGE_ROUTE}{name}", item


# -- Listings ------------------------------------------------------------------------------

PRODUCT_SELECT = """SELECT p.*, u.display_name seller_name, u.avatar_url seller_avatar,
       u.created_at seller_since
  FROM products p JOIN users u ON u.user_id = p.seller_id"""


def _seller_summary(seller_id: str) -> dict[str, Any]:
    sold = row(
        "SELECT COUNT(*) n FROM orders WHERE seller_id=? AND status IN ('shipped','completed')",
        (seller_id,),
    )["n"]
    return {"sales": sold}


def _product(record: dict[str, Any]) -> dict[str, Any]:
    summary = _seller_summary(record["seller_id"])
    return {
        "id": record["product_id"], "title": record["title"], "price": record["price"],
        "imageUrls": json.loads(record["image_urls"]), "category": record["category"],
        "condition": record["condition"], "description": record["description"],
        "size": record.get("size") or "", "brand": record.get("brand") or "",
        "status": record["status"], "createdAt": record["created_at"],
        "wardrobeItemId": record.get("wardrobe_item_id"),
        "seller": {
            "id": record["seller_id"], "name": record.get("seller_name") or "Seller",
            "avatarUrl": record.get("seller_avatar") or "",
            "sales": summary["sales"], "memberSince": record.get("seller_since") or "",
        },
        "isNew": record["condition"] == "new",
    }


def list_products(query: str = "", category: str = "") -> list[dict[str, Any]]:
    sql = PRODUCT_SELECT + " WHERE p.status='active'"
    params: list[Any] = []
    if category and category in CATEGORIES:
        sql += " AND p.category=?"
        params.append(category)
    if query.strip():
        sql += " AND (p.title LIKE ? OR p.brand LIKE ? OR p.description LIKE ?)"
        like = f"%{query.strip()}%"
        params += [like, like, like]
    sql += " ORDER BY p.created_at DESC"
    return [_product(record) for record in rows(sql, tuple(params))]


def get_product(product_id: str) -> dict[str, Any]:
    record = row(PRODUCT_SELECT + " WHERE p.product_id=?", (product_id,))
    if record is None:
        raise MarketplaceError("Listing not found.", 404)
    return _product(record)


def _validate_listing(data: dict[str, Any]) -> None:
    if not str(data.get("title") or "").strip():
        raise MarketplaceError("Add a title for the listing.")
    if float(data.get("price") or 0) <= 0:
        raise MarketplaceError("Set a price above zero.")
    if data.get("category") not in CATEGORIES:
        raise MarketplaceError("Choose a category.")
    if data.get("condition") not in CONDITIONS:
        raise MarketplaceError("Choose the item's condition.")
    if not data.get("image_urls"):
        raise MarketplaceError("Add at least one photo.")
    if len(data["image_urls"]) > MAX_PHOTOS:
        raise MarketplaceError(f"A listing can have at most {MAX_PHOTOS} photos.")


def create_listing(seller_id: str, data: dict[str, Any]) -> dict[str, Any]:
    _validate_listing(data)
    product_id = f"prd_{uuid.uuid4().hex[:16]}"
    now = utc_now()
    with connection() as db:
        db.execute(
            """INSERT INTO products(product_id, seller_id, title, price, image_urls, category,
                   condition, description, status, created_at, size, brand, wardrobe_item_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?, 'active', ?,?,?,?,?)""",
            (
                product_id, seller_id, data["title"].strip(), round(float(data["price"]), 2),
                json.dumps(data["image_urls"]), data["category"], data["condition"],
                (data.get("description") or "").strip(), now,
                (data.get("size") or "").strip(), (data.get("brand") or "").strip(),
                data.get("wardrobe_item_id"), now,
            ),
        )
    return get_product(product_id)


def _own_listing(seller_id: str, product_id: str) -> dict[str, Any]:
    record = row("SELECT * FROM products WHERE product_id=?", (product_id,))
    if record is None or record["seller_id"] != seller_id:
        raise MarketplaceError("Listing not found.", 404)
    return record


def update_listing(seller_id: str, product_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    record = _own_listing(seller_id, product_id)
    values: dict[str, Any] = {}
    for key in ("title", "description", "size", "brand"):
        if changes.get(key) is not None:
            values[key] = str(changes[key]).strip()
    if values.get("title") == "":
        raise MarketplaceError("The title cannot be empty.")
    if changes.get("price") is not None:
        if float(changes["price"]) <= 0:
            raise MarketplaceError("Set a price above zero.")
        values["price"] = round(float(changes["price"]), 2)
    if changes.get("condition") is not None:
        if changes["condition"] not in CONDITIONS:
            raise MarketplaceError("Choose a valid condition.")
        values["condition"] = changes["condition"]
    if changes.get("status") is not None:
        status = changes["status"]
        if status not in {"active", "paused"}:
            raise MarketplaceError("A listing can only be set to active or paused.")
        if record["status"] == "sold":
            raise MarketplaceError("This item is sold; cancel the order first to relist it.", 409)
        values["status"] = status
    if values:
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in values)
        with connection() as db:
            db.execute(f"UPDATE products SET {assignments} WHERE product_id=?", (*values.values(), product_id))
    return get_product(product_id)


def delete_listing(seller_id: str, product_id: str) -> None:
    _own_listing(seller_id, product_id)
    if rows("SELECT 1 FROM orders WHERE product_id=? LIMIT 1", (product_id,)):
        raise MarketplaceError("This listing has orders, so it can be paused but not deleted.", 409)
    record = row("SELECT image_urls FROM products WHERE product_id=?", (product_id,))
    with connection() as db:
        db.execute("DELETE FROM conversation_messages WHERE conversation_id IN "
                   "(SELECT conversation_id FROM conversations WHERE product_id=?)", (product_id,))
        db.execute("DELETE FROM conversations WHERE product_id=?", (product_id,))
        db.execute("DELETE FROM products WHERE product_id=?", (product_id,))
    for url in json.loads(record["image_urls"]):
        if url.startswith(IMAGE_ROUTE):
            (image_dir() / Path(url).name).unlink(missing_ok=True)


# -- Orders --------------------------------------------------------------------------------

ORDER_SELECT = """SELECT o.*, p.title, p.image_urls, b.display_name buyer_name, s.display_name seller_name
  FROM orders o
  JOIN products p ON p.product_id = o.product_id
  JOIN users b ON b.user_id = o.buyer_id
  JOIN users s ON s.user_id = o.seller_id"""


def _order(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["order_id"], "productId": record["product_id"], "productTitle": record["title"],
        "imageUrl": (json.loads(record["image_urls"]) or [""])[0], "amount": record["amount"],
        "status": record["status"], "date": record["created_at"],
        "updatedAt": record.get("updated_at") or record["created_at"],
        "buyer": {"id": record["buyer_id"], "name": record.get("buyer_name") or "Buyer"},
        "seller": {"id": record["seller_id"], "name": record.get("seller_name") or "Seller"},
        "shippingAddress": json.loads(record.get("shipping_address") or "{}"),
        "paymentMethod": record.get("payment_method") or "cod",
    }


def create_order(buyer_id: str, product_ids: list[str], shipping_address: dict[str, str] | None = None,
                 payment_method: str = "cod") -> list[str]:
    ensure_user(buyer_id)
    order_ids: list[str] = []
    now = utc_now()
    with connection() as db:
        for product_id in dict.fromkeys(product_ids):
            product = db.execute(
                "SELECT * FROM products WHERE product_id=? AND status='active'", (product_id,),
            ).fetchone()
            if not product:
                raise MarketplaceError("An item in your bag is no longer available.", 409)
            if product["seller_id"] == buyer_id:
                raise MarketplaceError("You cannot buy your own listing.", 409)
            order_id = f"ord_{uuid.uuid4().hex[:16]}"
            db.execute(
                """INSERT INTO orders(order_id, buyer_id, seller_id, product_id, amount, status, created_at,
                       shipping_address, payment_method, updated_at)
                   VALUES (?,?,?,?,?, 'pending', ?,?,?,?)""",
                (order_id, buyer_id, product["seller_id"], product_id, product["price"], now,
                 json.dumps(shipping_address or {}), payment_method, now),
            )
            # Reserve the one-off item so nobody else can buy it.
            db.execute("UPDATE products SET status='sold', updated_at=? WHERE product_id=?", (now, product_id))
            order_ids.append(order_id)
    return order_ids


def buyer_orders(buyer_id: str) -> list[dict[str, Any]]:
    return [_order(r) for r in rows(ORDER_SELECT + " WHERE o.buyer_id=? ORDER BY o.created_at DESC", (buyer_id,))]


# Who may move an order to which status, from which status.
TRANSITIONS = {
    ("seller", "pending", "shipped"), ("seller", "pending", "cancelled"),
    ("buyer", "pending", "cancelled"), ("buyer", "shipped", "completed"),
}


def update_order_status(user_id: str, order_id: str, status: str) -> dict[str, Any]:
    record = row("SELECT * FROM orders WHERE order_id=?", (order_id,))
    if record is None or user_id not in {record["buyer_id"], record["seller_id"]}:
        raise MarketplaceError("Order not found.", 404)
    role = "seller" if user_id == record["seller_id"] else "buyer"
    if (role, record["status"], status) not in TRANSITIONS:
        raise MarketplaceError(f"A {role} cannot change a {record['status']} order to {status}.", 409)
    now = utc_now()
    with connection() as db:
        db.execute("UPDATE orders SET status=?, updated_at=? WHERE order_id=?", (status, now, order_id))
        if status == "cancelled":
            # The item goes back on sale.
            db.execute("UPDATE products SET status='active', updated_at=? WHERE product_id=?",
                       (now, record["product_id"]))
        elif status == "shipped":
            # A piece listed from the seller's wardrobe has left it: stop suggesting it in outfits.
            db.execute(
                """UPDATE clothing_items SET available=0 WHERE user_id=? AND item_id=
                   (SELECT wardrobe_item_id FROM products WHERE product_id=?)""",
                (record["seller_id"], record["product_id"]),
            )
    return _order(row(ORDER_SELECT + " WHERE o.order_id=?", (order_id,)))


def seller_dashboard(seller_id: str) -> dict[str, Any]:
    listings = [_product(r) for r in rows(PRODUCT_SELECT + " WHERE p.seller_id=? ORDER BY p.created_at DESC", (seller_id,))]
    orders = [_order(r) for r in rows(ORDER_SELECT + " WHERE o.seller_id=? ORDER BY o.created_at DESC", (seller_id,))]
    earned = [order for order in orders if order["status"] in {"shipped", "completed"}]
    return {
        "stats": {
            "totalSales": len(earned),
            "revenue": round(sum(float(order["amount"]) for order in earned), 2),
            "activeListings": sum(1 for listing in listings if listing["status"] == "active"),
            "pendingOrders": sum(1 for order in orders if order["status"] == "pending"),
            "unreadMessages": unread_count(seller_id),
        },
        "listings": listings,
        "orders": orders,
    }


# -- Buyer <-> seller chat -----------------------------------------------------------------

def start_conversation(user_id: str, product_id: str, buyer_id: str | None = None) -> dict[str, Any]:
    """Open (or reuse) the thread about a listing. Buyers start it themselves; a seller
    may open it with a ``buyer_id`` who has ordered the item."""
    product = row("SELECT product_id, seller_id FROM products WHERE product_id=?", (product_id,))
    if product is None:
        raise MarketplaceError("Listing not found.", 404)
    if product["seller_id"] == user_id:
        if not buyer_id or not rows(
            "SELECT 1 FROM orders WHERE product_id=? AND buyer_id=? LIMIT 1", (product_id, buyer_id),
        ):
            raise MarketplaceError("This is your own listing.", 409)
    else:
        buyer_id = user_id
    existing = row(
        "SELECT conversation_id FROM conversations WHERE product_id=? AND buyer_id=?", (product_id, buyer_id),
    )
    if existing:
        return get_conversation(user_id, existing["conversation_id"])
    conversation_id = f"cnv_{uuid.uuid4().hex[:16]}"
    with connection() as db:
        db.execute(
            """INSERT INTO conversations(conversation_id, product_id, buyer_id, seller_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (conversation_id, product_id, buyer_id, product["seller_id"], utc_now(), utc_now()),
        )
    return get_conversation(user_id, conversation_id)


CONVERSATION_SELECT = """SELECT c.*, p.title, p.price, p.image_urls, p.status product_status,
       b.display_name buyer_name, b.avatar_url buyer_avatar,
       s.display_name seller_name, s.avatar_url seller_avatar
  FROM conversations c
  JOIN products p ON p.product_id = c.product_id
  JOIN users b ON b.user_id = c.buyer_id
  JOIN users s ON s.user_id = c.seller_id"""


def _conversation(user_id: str, record: dict[str, Any]) -> dict[str, Any]:
    is_seller = user_id == record["seller_id"]
    last = row(
        "SELECT body, sender_id, created_at FROM conversation_messages WHERE conversation_id=? "
        "ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (record["conversation_id"],),
    )
    unread = row(
        "SELECT COUNT(*) n FROM conversation_messages WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",
        (record["conversation_id"], user_id),
    )["n"]
    other = "buyer" if is_seller else "seller"
    return {
        "id": record["conversation_id"],
        "role": "seller" if is_seller else "buyer",
        "product": {
            "id": record["product_id"], "title": record["title"], "price": record["price"],
            "imageUrl": (json.loads(record["image_urls"]) or [""])[0], "status": record["product_status"],
        },
        "otherUser": {
            "id": record[f"{other}_id"], "name": record.get(f"{other}_name") or other.title(),
            "avatarUrl": record.get(f"{other}_avatar") or "",
        },
        "lastMessage": last["body"] if last else "",
        "lastMessageAt": last["created_at"] if last else record["created_at"],
        "lastMessageMine": bool(last and last["sender_id"] == user_id),
        "unread": unread,
    }


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any]:
    record = row(CONVERSATION_SELECT + " WHERE c.conversation_id=?", (conversation_id,))
    if record is None or user_id not in {record["buyer_id"], record["seller_id"]}:
        raise MarketplaceError("Conversation not found.", 404)
    return _conversation(user_id, record)


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    records = rows(
        CONVERSATION_SELECT + " WHERE c.buyer_id=? OR c.seller_id=? ORDER BY c.updated_at DESC",
        (user_id, user_id),
    )
    return [_conversation(user_id, record) for record in records]


def conversation_messages(user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    get_conversation(user_id, conversation_id)  # access check
    with connection() as db:
        db.execute(
            "UPDATE conversation_messages SET read_at=? WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL",
            (utc_now(), conversation_id, user_id),
        )
    return [
        {"id": r["message_id"], "body": r["body"], "createdAt": r["created_at"],
         "mine": r["sender_id"] == user_id, "read": r["read_at"] is not None}
        for r in rows(
            "SELECT * FROM conversation_messages WHERE conversation_id=? ORDER BY created_at, rowid",
            (conversation_id,),
        )
    ]


def send_message(user_id: str, conversation_id: str, body: str) -> dict[str, Any]:
    get_conversation(user_id, conversation_id)  # access check
    text = body.strip()
    if not text:
        raise MarketplaceError("Message cannot be empty.")
    message_id = f"msg_{uuid.uuid4().hex[:16]}"
    now = utc_now()
    with connection() as db:
        db.execute(
            "INSERT INTO conversation_messages(message_id, conversation_id, sender_id, body, created_at) VALUES (?,?,?,?,?)",
            (message_id, conversation_id, user_id, text[:2000], now),
        )
        db.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (now, conversation_id))
    return {"id": message_id, "body": text[:2000], "createdAt": now, "mine": True, "read": False}


def unread_count(user_id: str) -> int:
    return row(
        """SELECT COUNT(*) n FROM conversation_messages m
             JOIN conversations c ON c.conversation_id = m.conversation_id
            WHERE (c.buyer_id=? OR c.seller_id=?) AND m.sender_id<>? AND m.read_at IS NULL""",
        (user_id, user_id, user_id),
    )["n"]
