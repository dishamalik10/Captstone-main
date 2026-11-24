from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from database import connection, decode_json_fields, ensure_user, row, rows, utc_now
from services.item_embeddings import pack_embedding
from services.media_access import signed_media_url
from services.vision_service import category_for_name


JSON_COLUMNS = {"confidence", "seasons", "style_tags", "occasion_tags"}


def create_item(
    user_id: str,
    image_path: Path,
    prediction: dict[str, Any],
) -> dict[str, Any]:
    ensure_user(user_id)
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
                color_name, image_path, confidence, created_at, embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                user_id,
                prediction["category"],
                prediction["product_type"]["label"],
                prediction["garment_group"]["label"],
                prediction["color_group"]["label"],
                str(image_path),
                json.dumps(confidence),
                created_at,
                pack_embedding(embedding) if embedding is not None else None,
            ),
        )
    return get_item(user_id, item_id)


def _public(record: dict[str, Any]) -> dict[str, Any]:
    record.pop("embedding", None)
    # The garment's type name wins over a stale category (e.g. a photo first
    # classified as Sneakers and later renamed "Skirt" is a Bottom).
    record["category"] = category_for_name(record.get("subcategory")) or record["category"]
    record = decode_json_fields(record)
    color_sample = record["confidence"].pop("color_sample", None)
    record["needs_review"] = any(
        prediction["confidence"] < 0.60
        for prediction in record["confidence"].values()
    )
    image_path = record.pop("image_path")
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
    return Path(record["image_path"])
