"""Report and block (ENGINEERING_PLAN 4.4).

- Anyone signed in can report a listing, a marketplace conversation, a social post or a
  user. A report stores a snapshot of what was reported, so the evidence survives the
  content being edited or deleted. Reports are reviewed by hand (scripts/review_reports.py).
- Blocking is one-way for content (you stop seeing the blocked user's listings, posts
  and conversations) and two-way for messaging (neither of you can message the other).
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from database import connection, row, rows, utc_now

TARGET_TYPES = ("listing", "conversation", "post", "user")
REASONS = ("spam", "scam", "offensive", "harassment", "prohibited_item", "other")


class ModerationError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _target(reporter_id: str, target_type: str, target_id: str) -> tuple[str, dict[str, Any]]:
    """(owner user id, snapshot) of the reported thing, or 404."""
    if target_type == "listing":
        record = row("SELECT seller_id, title, description, image_urls, price FROM products WHERE product_id=?", (target_id,))
        if record:
            return record["seller_id"], {k: record[k] for k in ("title", "description", "image_urls", "price")}
    elif target_type == "post":
        record = row("SELECT user_id, caption, outfit_image_url FROM social_posts WHERE post_id=?", (target_id,))
        if record:
            return record["user_id"], {"caption": record["caption"], "image": record["outfit_image_url"]}
    elif target_type == "conversation":
        record = row("SELECT buyer_id, seller_id, product_id FROM conversations WHERE conversation_id=?", (target_id,))
        # Only a member can report a conversation, and the report is about the other member.
        if record and reporter_id in (record["buyer_id"], record["seller_id"]):
            other = record["seller_id"] if reporter_id == record["buyer_id"] else record["buyer_id"]
            messages = rows(
                "SELECT sender_id, body, created_at FROM conversation_messages WHERE conversation_id=? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 30",
                (target_id,),
            )
            return other, {"product_id": record["product_id"], "recent_messages": list(reversed(messages))}
    elif target_type == "user":
        record = row("SELECT user_id, display_name FROM users WHERE user_id=?", (target_id,))
        if record:
            return record["user_id"], {"display_name": record["display_name"]}
    raise ModerationError("That content was not found.", 404)


def report(reporter_id: str, target_type: str, target_id: str, reason: str, details: str = "") -> dict[str, Any]:
    if target_type not in TARGET_TYPES or reason not in REASONS:
        raise ModerationError("Choose what you're reporting and why.", 422)
    owner_id, snapshot = _target(reporter_id, target_type, target_id)
    if owner_id == reporter_id:
        raise ModerationError("You can't report your own content.", 409)
    report_id = f"rpt_{uuid.uuid4().hex[:16]}"
    with connection() as db:
        # One report per person per item; reporting again just keeps the first report.
        db.execute(
            """INSERT INTO reports(report_id, reporter_id, target_type, target_id, target_owner_id, reason,
                   details, snapshot_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(reporter_id, target_type, target_id) DO NOTHING""",
            (report_id, reporter_id, target_type, target_id, owner_id, reason, details.strip()[:1000],
             json.dumps(snapshot, default=str), utc_now()),
        )
    return {"reported": True}


def block(blocker_id: str, blocked_id: str) -> None:
    if blocker_id == blocked_id:
        raise ModerationError("You can't block yourself.", 409)
    if not row("SELECT 1 FROM users WHERE user_id=?", (blocked_id,)):
        raise ModerationError("User not found.", 404)
    with connection() as db:
        db.execute(
            "INSERT INTO blocks(blocker_id, blocked_id, created_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
            (blocker_id, blocked_id, utc_now()),
        )


def unblock(blocker_id: str, blocked_id: str) -> None:
    with connection() as db:
        db.execute("DELETE FROM blocks WHERE blocker_id=? AND blocked_id=?", (blocker_id, blocked_id))


def list_blocked(user_id: str) -> list[dict[str, Any]]:
    return [
        {"id": r["blocked_id"], "name": r["display_name"] or "AURA user", "blockedAt": r["created_at"]}
        for r in rows(
            "SELECT b.blocked_id, b.created_at, u.display_name FROM blocks b JOIN users u ON u.user_id=b.blocked_id "
            "WHERE b.blocker_id=? ORDER BY b.created_at DESC",
            (user_id,),
        )
    ]


def hidden_from(viewer_id: str | None) -> set[str]:
    """Users whose content ``viewer_id`` has chosen not to see."""
    if not viewer_id:
        return set()
    return {r["blocked_id"] for r in rows("SELECT blocked_id FROM blocks WHERE blocker_id=?", (viewer_id,))}


def blocked_between(a: str, b: str) -> bool:
    """True if either user has blocked the other (messaging is off both ways)."""
    return row(
        "SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?) LIMIT 1",
        (a, b, b, a),
    ) is not None
