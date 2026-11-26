"""Find wardrobe items the user has never worn, export them as a donation list,
and mark items as donated (which removes them from the active wardrobe).

"Worn" means the item was part of an outfit the user marked as worn
(a ``feedback`` row with ``action='wear'``).
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from database import connection, rows, utc_now
from services.wardrobe_service import list_items


def _worn_item_ids(user_id: str) -> set[str]:
    records = rows(
        "SELECT item_ids FROM feedback WHERE user_id=? AND action='wear'", (user_id,),
    )
    return {item_id for record in records for item_id in json.loads(record["item_ids"])}


def _days_since(timestamp: str, now: datetime) -> int:
    try:
        created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0, (now - created).days)


def unworn_items(user_id: str, min_days: int = 0) -> list[dict[str, Any]]:
    """Active (not donated) items never worn, owned for at least ``min_days`` days,
    oldest first so the longest-unworn pieces lead the list."""
    worn = _worn_item_ids(user_id)
    now = datetime.now(timezone.utc)
    result = []
    for item in list_items(user_id, available_only=True):
        if item["item_id"] in worn:
            continue
        days = _days_since(item["created_at"], now)
        if days < min_days:
            continue
        result.append({**item, "days_in_wardrobe": days})
    result.sort(key=lambda item: item["days_in_wardrobe"], reverse=True)
    return result


CSV_COLUMNS = ("Item", "Category", "Colour", "Pattern", "Season", "Added on", "Days owned, never worn")


def unworn_items_csv(user_id: str, min_days: int = 0) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for item in unworn_items(user_id, min_days):
        writer.writerow((
            item.get("subcategory") or item["category"],
            item["category"],
            item.get("color_name") or "",
            item.get("pattern") or "",
            item.get("season_label") or "",
            str(item["created_at"])[:10],
            item["days_in_wardrobe"],
        ))
    return buffer.getvalue()


def mark_donated(user_id: str, item_ids: list[str]) -> list[str]:
    """Mark the user's own active items as donated; returns the ids actually updated."""
    if not item_ids:
        return []
    placeholders = ",".join("?" for _ in item_ids)
    owned = {
        record["item_id"] for record in rows(
            f"SELECT item_id FROM clothing_items WHERE user_id=? AND available=1 AND item_id IN ({placeholders})",
            (user_id, *item_ids),
        )
    }
    if not owned:
        return []
    donated_at = utc_now()
    with connection() as db:
        db.executemany(
            "UPDATE clothing_items SET available=0, donated_at=? WHERE user_id=? AND item_id=?",
            [(donated_at, user_id, item_id) for item_id in owned],
        )
    return sorted(owned)
