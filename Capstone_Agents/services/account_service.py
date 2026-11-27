"""Delete an account and everything it owns (ENGINEERING_PLAN 4.3, issues H6 / M12).

All rows go in one transaction; files are removed after it commits (a failed delete
never leaves rows pointing at missing files). Orders are the one exception: the other
party keeps their order history, so an order is re-pointed at a placeholder "Deleted
user" with the deleted person's address removed, and unfinished orders are cancelled.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from database import connection, row, utc_now
from services.app_service import _verify_password
from services.marketplace_service import IMAGE_ROUTE, image_dir
from services.media_paths import media_path
from settings import settings

LOGGER = logging.getLogger(__name__)
DELETED_USER_ID = "deleted_user"
DELETED_USER_NAME = "Deleted user"


class AccountError(ValueError):
    """A user-facing reason the account could not be deleted."""


def _listing_files(image_urls: str) -> list[Path]:
    files = []
    for url in json.loads(image_urls or "[]"):
        if isinstance(url, str) and url.startswith(IMAGE_ROUTE):
            files.append(image_dir() / Path(url.removeprefix(IMAGE_ROUTE)).name)
    return files


def delete_account(user_id: str, password: str) -> None:
    record = row("SELECT password_hash FROM users WHERE user_id=?", (user_id,))
    if record is None or user_id == DELETED_USER_ID:
        raise AccountError("Account not found.")
    if not record["password_hash"] or not _verify_password(password, record["password_hash"]):
        raise AccountError("That password is not correct.")
    now = utc_now()
    files: list[Path] = []
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        files += [media_path(r["image_path"]) for r in db.execute("SELECT image_path FROM clothing_items WHERE user_id=?", (user_id,))]
        for preview in db.execute("SELECT files_json FROM import_previews WHERE user_id=?", (user_id,)):
            preview_files = json.loads(preview["files_json"])
            files += [settings.upload_dir / name for name in [preview_files["original"]] + [
                c["file"] for found in preview_files["candidates"].values() for c in found]]
        for avatar in db.execute("SELECT avatar_path, parsing_path FROM avatars WHERE user_id=?", (user_id,)):
            files += [media_path(p) for p in (avatar["avatar_path"], avatar["parsing_path"]) if p]
        files += [media_path(r["result_path"]) for r in db.execute(
            "SELECT result_path FROM tryon_renders WHERE user_id=? AND result_path IS NOT NULL", (user_id,))]

        db.execute(
            """INSERT INTO users(user_id, display_name, created_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO NOTHING""",
            (DELETED_USER_ID, DELETED_USER_NAME, now),
        )
        # Unfinished orders are cancelled; a buyer's cancelled order puts the item back on sale.
        for order in db.execute(
            "SELECT order_id, product_id, buyer_id FROM orders WHERE status='pending' AND (buyer_id=? OR seller_id=?)",
            (user_id, user_id),
        ).fetchall():
            db.execute("UPDATE orders SET status='cancelled', updated_at=? WHERE order_id=?", (now, order["order_id"]))
            if order["buyer_id"] == user_id:
                db.execute("UPDATE products SET status='active', updated_at=? WHERE product_id=? AND status='sold'",
                           (now, order["product_id"]))
        # The deleted buyer's shipping address goes; the other party keeps the order record.
        db.execute("UPDATE orders SET buyer_id=?, shipping_address=NULL WHERE buyer_id=?", (DELETED_USER_ID, user_id))
        db.execute("UPDATE orders SET seller_id=? WHERE seller_id=?", (DELETED_USER_ID, user_id))
        # Listings: those in someone's order history stay as a title only (no photos);
        # the rest are deleted (their chats cascade with them).
        for product in db.execute("SELECT product_id, image_urls FROM products WHERE seller_id=?", (user_id,)).fetchall():
            files += _listing_files(product["image_urls"])
            if db.execute("SELECT 1 FROM orders WHERE product_id=? LIMIT 1", (product["product_id"],)).fetchone():
                db.execute(
                    "UPDATE products SET seller_id=?, image_urls='[]', description='', wardrobe_item_id=NULL, "
                    "status='paused', updated_at=? WHERE product_id=?",
                    (DELETED_USER_ID, now, product["product_id"]),
                )
            else:
                db.execute("DELETE FROM products WHERE product_id=?", (product["product_id"],))
        # Tables keyed on the user without a foreign key.
        db.execute("DELETE FROM tryon_usage WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM rate_events WHERE key=?", (user_id,))
        # Reports about this person hold copies of their messages and listings.
        db.execute("DELETE FROM reports WHERE target_owner_id=?", (user_id,))
        # Everything else (wardrobe, avatars, renders, chats, posts, likes, follows,
        # feedback, recommendations, preferences, bandit model, sessions) cascades.
        db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    removed = 0
    for path in files:
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            LOGGER.exception("Could not delete a file of a deleted account")
    LOGGER.info("Deleted an account and %d files", removed)
