"""Stored 512-d visual embeddings for wardrobe items.

New uploads store the embedding produced by the garment CNN. Items uploaded
before this feature are back-filled lazily from their saved image the first
time the compatibility model needs them.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from database import connection, rows
from ml.outfit_compat import EMBEDDING_DIM
from services.media_paths import media_path

LOGGER = logging.getLogger(__name__)


def pack_embedding(embedding: Any) -> bytes:
    vector = np.asarray(embedding, dtype=np.float16).reshape(-1)
    if vector.shape[0] != EMBEDDING_DIM:
        raise ValueError(f"Expected a {EMBEDDING_DIM}-d embedding, got {vector.shape[0]}")
    return vector.tobytes()


def unpack_embedding(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    vector = np.frombuffer(blob, dtype=np.float16).astype(np.float32)
    return vector if vector.shape[0] == EMBEDDING_DIM else None


def embeddings_for_items(user_id: str, items: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    ids = [str(item["item_id"]) for item in items]
    if not ids:
        return {}
    records = rows(
        "SELECT item_id, embedding, image_path FROM clothing_items WHERE user_id=? AND item_id IN (%s)"
        % ",".join("?" for _ in ids),
        (user_id, *ids),
    )
    found: dict[str, np.ndarray] = {}
    missing: list[dict[str, Any]] = []
    for record in records:
        vector = unpack_embedding(record.get("embedding"))
        if vector is not None:
            found[record["item_id"]] = vector
        else:
            missing.append(record)
    if missing:
        found.update(_backfill(user_id, missing))
    return found


def _backfill(user_id: str, records: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    from services.vision_service import vision_service

    computed: dict[str, np.ndarray] = {}
    for record in records:
        path = media_path(record["image_path"])
        if not path.is_file():
            continue
        try:
            vector = np.asarray(vision_service.embed(path), dtype=np.float32)
            with connection() as db:
                db.execute(
                    "UPDATE clothing_items SET embedding=? WHERE user_id=? AND item_id=?",
                    (pack_embedding(vector), user_id, record["item_id"]),
                )
            computed[record["item_id"]] = vector
        except Exception:  # pragma: no cover - depends on local model/image files
            LOGGER.exception("Could not back-fill embedding for %s", record["item_id"])
    return computed
