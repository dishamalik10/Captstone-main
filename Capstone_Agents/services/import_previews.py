"""Preview -> confirm for new wardrobe items (ENGINEERING_PLAN 4.2b).

A preview holds the photo (from a shop link or an upload) and, when someone is wearing
the garment, SegFormer cut-outs for every category. The app shows the suggested
category's cut-out with three choices: "Looks right", "Pick a different piece" (another
category or candidate) and "Use the original photo". Confirming creates the item.
Unconfirmed previews and their files are deleted after one hour.

Files are kept in the upload folder as ``preview_<id>_*.jpg`` so the existing signed
media route can serve them to their owner.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from database import connection, row, rows, utc_now
from services import garment_cutout
from services.media_access import signed_media_url
from settings import settings

TTL_SECONDS = 3600
PREFIX = "preview_"


class PreviewError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _save(image: Image.Image, name: str) -> str:
    image.convert("RGB").save(settings.upload_dir / name, format="JPEG", quality=92)
    return name


def _delete_files(files: dict[str, Any]) -> None:
    names = [files.get("original")] + [c["file"] for found in files.get("candidates", {}).values() for c in found]
    for name in names:
        if name:
            (settings.upload_dir / name).unlink(missing_ok=True)


def cleanup_expired(now: float | None = None) -> int:
    now = time.time() if now is None else now
    expired = rows("SELECT preview_id, files_json FROM import_previews WHERE expires_at < ?", (now,))
    for record in expired:
        _delete_files(json.loads(record["files_json"]))
    with connection() as db:
        db.executemany("DELETE FROM import_previews WHERE preview_id=?", [(r["preview_id"],) for r in expired])
    return len(expired)


def create(
    user_id: str,
    photo: Image.Image,
    *,
    classify: Callable[[Path], str],
    hints: tuple[str, ...] = (),
    person_free: bool | None = None,
    source_url: str | None = None,
    source_title: str | None = None,
    suggested_size: str | None = None,
) -> dict[str, Any]:
    """Segment ``photo`` (unless it is known to have no person in it) and store a preview.
    ``classify`` returns the CNN's category for a photo file (used when the shop page
    gave no category hint)."""
    cleanup_expired()
    preview_id = uuid.uuid4().hex[:16]
    photo = photo.convert("RGB")
    files: dict[str, Any] = {"original": _save(photo, f"{PREFIX}{preview_id}_original.jpg"), "candidates": {}}
    person_found = False
    if person_free is not True:
        labels = garment_cutout.segment(photo)
        person_found = labels is not None and bool(garment_cutout.person_present(photo, labels))
        if person_found:
            for category in garment_cutout.CATEGORIES:
                found = garment_cutout.candidates(photo, labels, category)
                files["candidates"][category] = [
                    {"label": c.label, "file": _save(c.image, f"{PREFIX}{preview_id}_{category.lower()}_{i}.jpg")}
                    for i, c in enumerate(found)
                ]
    suggested = garment_cutout.infer_category(*hints)
    if suggested is None:
        try:
            suggested = classify(settings.upload_dir / files["original"])
        except Exception:  # a suggestion is optional; the user picks the category anyway
            suggested = None
    with connection() as db:
        db.execute(
            """INSERT INTO import_previews(preview_id, user_id, source_url, source_title, suggested_category,
                   person_found, files_json, created_at, expires_at, suggested_size) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (preview_id, user_id, source_url, source_title, suggested, int(person_found), json.dumps(files),
             utc_now(), time.time() + TTL_SECONDS, suggested_size),
        )
    return get(user_id, preview_id)


def _record(user_id: str, preview_id: str) -> dict[str, Any]:
    record = row("SELECT * FROM import_previews WHERE preview_id=? AND user_id=?", (preview_id, user_id))
    if record is None or record["expires_at"] < time.time():
        raise PreviewError("This preview has expired. Add the item again.", 404)
    return record


def get(user_id: str, preview_id: str) -> dict[str, Any]:
    record = _record(user_id, preview_id)
    files = json.loads(record["files_json"])
    return {
        "preview_id": preview_id,
        "suggested_category": record["suggested_category"],
        "person_found": bool(record["person_found"]),
        "original_url": signed_media_url(user_id, files["original"]),
        "candidates": {
            category: [{"index": i, "label": c["label"], "image_url": signed_media_url(user_id, c["file"])}
                       for i, c in enumerate(found)]
            for category, found in files["candidates"].items() if found
        },
        "source_title": record["source_title"],
        "suggested_size": record.get("suggested_size"),
        "expires_at": record["expires_at"],
    }


def take(user_id: str, preview_id: str, choice: str, category: str, index: int = 0) -> tuple[Path, dict[str, Any]]:
    """Move the chosen photo out of the preview into a permanent upload file and delete
    the rest. Returns (photo path, {source_url, source_title})."""
    record = _record(user_id, preview_id)
    files = json.loads(record["files_json"])
    if choice == "cutout":
        found = files["candidates"].get(category) or []
        if not 0 <= index < len(found):
            raise PreviewError("That cut-out isn't available. Pick another piece or use the original photo.", 422)
        chosen, target = found[index]["file"], f"{uuid.uuid4().hex}-garment.jpg"  # *-garment = cut out
    else:
        chosen, target = files["original"], f"{uuid.uuid4().hex}.jpg"
    path = settings.upload_dir / target
    (settings.upload_dir / chosen).rename(path)
    discard(user_id, preview_id)
    return path, {"source_url": record["source_url"], "source_title": record["source_title"]}


def discard(user_id: str, preview_id: str) -> None:
    record = row("SELECT files_json FROM import_previews WHERE preview_id=? AND user_id=?", (preview_id, user_id))
    if record is None:
        return
    _delete_files(json.loads(record["files_json"]))
    with connection() as db:
        db.execute("DELETE FROM import_previews WHERE preview_id=?", (preview_id,))


def owns_media(user_id: str, path: Path) -> bool:
    """Whether ``path`` is a live preview file of ``user_id`` (for the signed media route)."""
    if not path.name.startswith(PREFIX):
        return False
    preview_id = path.name[len(PREFIX):].split("_", 1)[0]
    record = row("SELECT files_json, expires_at FROM import_previews WHERE preview_id=? AND user_id=?",
                 (preview_id, user_id))
    if record is None or record["expires_at"] < time.time():
        return False
    files = json.loads(record["files_json"])
    names = {files["original"]} | {c["file"] for found in files["candidates"].values() for c in found}
    return path.name in names
