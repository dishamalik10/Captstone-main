from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from database import connection, decode_json_fields, ensure_user, row, rows, utc_now
from services.item_embeddings import pack_embedding
from services.media_paths import media_name, media_path
from services.media_access import signed_media_url
from services.season_classifier import classify_seasons, season_label
from services.vision_service import category_for_name


JSON_COLUMNS = {"confidence", "seasons", "style_tags", "occasion_tags"}


def create_item(
    user_id: str,
    image_path: Path,
    prediction: dict[str, Any],
    *,
    source_url: str | None = None,
    source_title: str | None = None,
    category: str | None = None,
    size: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store a new item. ``category`` is the user's choice (4.2b): if the CNN's category
    differs, the user's wins, the CNN's type and colour are kept, and the item is flagged
    for review."""
    ensure_user(user_id)
    category_source = "user" if category and category != prediction["category"] else None
    category = category or prediction["category"]
    item_id = f"cloth_{uuid.uuid4().hex[:12]}"
    created_at = utc_now()
    embedding = prediction.get("embedding")
    confidence = {
        key: value for key, value in prediction.items() if key not in {"category", "embedding"}
    }
    with connection() as db:
        db.execute(
            """
            INSERT INTO clothing_items(
                item_id, user_id, category, subcategory, garment_group,
                color_name, image_path, confidence, created_at, embedding,
                source_url, source_title, category_source, size_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                user_id,
                category,
                prediction["product_type"]["label"],
                prediction["garment_group"]["label"],
                prediction["color_group"]["label"],
                media_name(image_path),
                json.dumps(confidence),
                created_at,
                pack_embedding(embedding) if embedding is not None else None,
                source_url,
                source_title,
                category_source,
                _size_json(size),
            ),
        )
    return get_item(user_id, item_id)


def _size_json(size: dict[str, Any] | None) -> str | None:
    """Stored garment size (4.11), or None when nothing is known."""
    if not size:
        return None
    measurements = {k: v for k, v in (size.get("measurements") or {}).items() if v is not None}
    label = (size.get("label") or "").strip() or None
    if not label and not measurements:
        return None
    return json.dumps({"label": label, "chart": size.get("chart"), "measurements": measurements})


def _public(record: dict[str, Any]) -> dict[str, Any]:
    record.pop("embedding", None)
    # The garment's type name wins over a stale category (e.g. a photo first
    # classified as Sneakers and later renamed "Skirt" is a Bottom).
    # ...unless the user chose the category when adding the item (4.2b).
    if record.get("category_source") != "user":
        record["category"] = category_for_name(record.get("subcategory")) or record["category"]
    record = decode_json_fields(record)
    # Items without a saved season get one inferred from type/fabric (not persisted,
    # so improving the classifier re-tags old uploads; a user-set season always wins).
    record["season_source"] = "user" if record.get("seasons") else "auto"
    if not record.get("seasons"):
        record["seasons"] = classify_seasons(record)
    record["season_label"] = season_label(record["seasons"])
    color_sample = record["confidence"].pop("color_sample", None)
    record["needs_review"] = record.pop("category_source", None) == "user" or any(
        prediction["confidence"] < 0.60
        for prediction in record["confidence"].values()
    )
    record["size"] = json.loads(record.pop("size_json", None) or "null")
    image_path = record.pop("image_path")
    # Photos cut down to just the garment (model/background removed) are saved as *-garment.jpg.
    record["garment_cutout"] = str(image_path).endswith("-garment.jpg")
    record["image_url"] = signed_media_url(record["user_id"], image_path)
    record["color_sample"] = color_sample
    return record


def get_item(user_id: str, item_id: str) -> dict[str, Any]:
    record = row(
        "SELECT * FROM clothing_items WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    )
    if record is None:
        raise KeyError(item_id)
    return _public(record)


def items_by_ids(user_id: str, item_ids: list[str]) -> list[dict[str, Any]]:
    """Only the named items of this user (one query), newest first like ``list_items``."""
    ids = list(dict.fromkeys(str(item_id) for item_id in item_ids))
    if not ids:
        return []
    records = rows(
        f"SELECT * FROM clothing_items WHERE user_id = ? AND item_id IN ({','.join('?' for _ in ids)}) "
        "ORDER BY created_at DESC",
        (user_id, *ids),
    )
    return [_public(record) for record in records]


def list_items(user_id: str, available_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM clothing_items WHERE user_id = ?"
    parameters: tuple[Any, ...] = (user_id,)
    if available_only:
        sql += " AND available = 1"
    sql += " ORDER BY created_at DESC"
    return [_public(record) for record in rows(sql, parameters)]


def update_item(user_id: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "category", "subcategory", "color_name", "pattern", "fabric", "fit",
        "texture", "seasons", "style_tags", "occasion_tags", "available",
    }
    values = {key: value for key, value in changes.items() if key in allowed and value is not None}
    if "size" in changes and changes["size"] is not None:
        # An empty size ({}) clears it.
        values["size_json"] = _size_json(changes["size"])
    if not values:
        return get_item(user_id, item_id)
    implied = category_for_name(values.get("subcategory"))
    if implied:
        values["category"] = implied
    for key in JSON_COLUMNS:
        if key in values:
            values[key] = json.dumps(values[key])
    if "available" in values:
        values["available"] = int(values["available"])
    assignments = ", ".join(f"{key} = ?" for key in values)
    with connection() as db:
        cursor = db.execute(
            f"UPDATE clothing_items SET {assignments} WHERE user_id = ? AND item_id = ?",
            (*values.values(), user_id, item_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(item_id)
    return get_item(user_id, item_id)


def replace_image(
    user_id: str,
    item_id: str,
    image_path: Path,
    prediction: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    """Swap an item's photo and re-apply the CNN prediction for it.
    Returns the updated item and the old image path (for the caller to delete)."""
    record = row(
        "SELECT image_path FROM clothing_items WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    )
    if record is None:
        raise KeyError(item_id)
    embedding = prediction.get("embedding")
    confidence = {key: value for key, value in prediction.items() if key not in {"category", "embedding"}}
    with connection() as db:
        db.execute(
            """UPDATE clothing_items SET image_path=?, category=?, subcategory=?, garment_group=?,
               color_name=?, confidence=?, embedding=? WHERE user_id=? AND item_id=?""",
            (
                media_name(image_path), prediction["category"], prediction["product_type"]["label"],
                prediction["garment_group"]["label"], prediction["color_group"]["label"],
                json.dumps(confidence), pack_embedding(embedding) if embedding is not None else None,
                user_id, item_id,
            ),
        )
    return get_item(user_id, item_id), media_path(record["image_path"])


def delete_item(user_id: str, item_id: str) -> Path:
    record = row(
        "SELECT image_path FROM clothing_items WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    )
    if record is None:
        raise KeyError(item_id)
    with connection() as db:
        db.execute(
            "DELETE FROM clothing_items WHERE user_id = ? AND item_id = ?",
            (user_id, item_id),
        )
    return media_path(record["image_path"])
