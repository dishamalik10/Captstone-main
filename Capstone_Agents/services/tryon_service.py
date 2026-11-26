"""My Virtual Look: personal avatar + virtual try-on of recommended outfits.

Flow: full-body photo -> body analysis (services.body_analysis) -> avatar (the user's
own photo on a plain backdrop) -> AI Stylist outfit -> CatVTON renders each garment
onto the avatar in layers (bottom, top, outer layer; a dress as one full-body
garment) -> the user previews the look.

Renders run one at a time on a background thread (the diffusion model needs most of
an 8 GB machine) and are cached per avatar + outfit, so revisiting a look is instant
and the same avatar is reused for every outfit. Every render is a generated visual
preview: it is not a physical garment-fit or size simulation.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from database import connection, row, rows, utc_now
from ml.catvton import CatVTON
from services import body_analysis
from services.media_access import signed_media_url
from settings import settings

LOGGER = logging.getLogger(__name__)
VIEWS = ("front", "side")
LAYER_ORDER = {"Bottom": 0, "Dress": 0, "Top": 1, "Outerwear": 2}
NOT_RENDERED = {"Footwear", "Accessory"}
IDLE_UNLOAD_SECONDS = 600
PREVIEW_DISCLAIMER = (
    "AI-generated visual preview on your photo. It shows colour, pattern and overall look; "
    "it is not a physical fit or size simulation, so real drape and fit can differ."
)

model = CatVTON(settings.tryon_model_dir, settings.tryon_device, settings.tryon_attention)


def init_tables() -> None:
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS avatars (
                avatar_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                view TEXT NOT NULL,
                avatar_path TEXT NOT NULL,
                parsing_path TEXT NOT NULL,
                landmarks_json TEXT NOT NULL,
                analysis_json TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_avatars_user ON avatars(user_id, view, active);

            CREATE TABLE IF NOT EXISTS tryon_renders (
                render_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                avatar_id TEXT NOT NULL REFERENCES avatars(avatar_id) ON DELETE CASCADE,
                cache_key TEXT NOT NULL,
                item_ids TEXT NOT NULL,
                recommendation_id TEXT,
                status TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT '',
                progress REAL NOT NULL DEFAULT 0,
                result_path TEXT,
                skipped_json TEXT NOT NULL DEFAULT '[]',
                error TEXT,
                saved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_tryon_cache ON tryon_renders(user_id, cache_key);
            """
        )
        # Renders interrupted by a restart can never finish.
        db.execute(
            "UPDATE tryon_renders SET status='failed', error='Interrupted by a server restart; try again.' "
            "WHERE status IN ('queued','running')"
        )


# -- status ---------------------------------------------------------------------------

def status() -> dict[str, Any]:
    missing = model.missing_files()
    return {
        "enabled": settings.tryon_enabled,
        "body_analysis_ready": body_analysis.models_ready(),
        "tryon_ready": settings.tryon_enabled and not missing,
        "missing_files": missing + body_analysis._models.missing(),
        "loaded": model.loaded,
        "engine": f"CatVTON (Stable Diffusion 1.5 inpainting, {settings.tryon_attention} attention)",
        "render_size": f"{settings.tryon_width}x{settings.tryon_height}",
        "steps": settings.tryon_steps,
        "queue_length": _jobs.qsize(),
        "disclaimer": PREVIEW_DISCLAIMER,
    }


# -- avatars --------------------------------------------------------------------------

def _save_png(image: Image.Image, prefix: str) -> Path:
    path = settings.upload_dir / f"{prefix}_{uuid.uuid4().hex}.png"
    image.save(path, optimize=True)
    return path


def _public_avatar(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "avatar_id": record["avatar_id"],
        "view": record["view"],
        "image_url": signed_media_url(record["user_id"], record["avatar_path"]),
        "analysis": json.loads(record["analysis_json"] or "{}"),
        "created_at": record["created_at"],
    }


def create_avatar(user_id: str, photo: Image.Image, view: str = "front") -> dict[str, Any]:
    """Validate a full-body photo, analyse it and make it the user's active avatar for ``view``."""
    if view not in VIEWS:
        raise body_analysis.BodyPhotoError("View must be 'front' or 'side'.")
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    photo.thumbnail((1600, 1600), Image.LANCZOS)  # enough detail; bounds memory
    parsed = body_analysis.parse_photo(photo)
    warnings = body_analysis.validate(parsed) if view == "front" else []
    avatar, parsing, landmarks = body_analysis.build_avatar(parsed)
    analysis: dict[str, Any] = {}
    if view == "front":
        analysis = body_analysis.analyze_proportions(parsing, landmarks, avatar, warnings)
    avatar_path = _save_png(avatar, "avatar")
    parsing_path = _save_png(Image.fromarray(parsing), "parsing")
    avatar_id = f"avatar_{uuid.uuid4().hex[:12]}"
    with connection() as db:
        old = db.execute(
            "SELECT avatar_id, avatar_path, parsing_path FROM avatars WHERE user_id=? AND view=?",
            (user_id, view),
        ).fetchall()
        db.execute(
            """INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at)
               VALUES (?,?,?,?,?,?,?,1,?)""",
            (avatar_id, user_id, view, str(avatar_path), str(parsing_path),
             json.dumps(landmarks.round(2).tolist()), json.dumps(analysis), utc_now()),
        )
    # A new photo replaces the old avatar for this view, with its renders and files.
    for record in old:
        _delete_avatar_files(user_id, record["avatar_id"], record["avatar_path"], record["parsing_path"])
    return _public_avatar(row("SELECT * FROM avatars WHERE avatar_id=?", (avatar_id,)))


def _delete_avatar_files(user_id: str, avatar_id: str, avatar_path: str, parsing_path: str) -> None:
    for render in rows("SELECT result_path FROM tryon_renders WHERE avatar_id=?", (avatar_id,)):
        if render["result_path"]:
            Path(render["result_path"]).unlink(missing_ok=True)
    with connection() as db:
        db.execute("DELETE FROM tryon_renders WHERE avatar_id=?", (avatar_id,))
        db.execute("DELETE FROM avatars WHERE avatar_id=? AND user_id=?", (avatar_id, user_id))
    Path(avatar_path).unlink(missing_ok=True)
    Path(parsing_path).unlink(missing_ok=True)


def get_avatars(user_id: str) -> dict[str, Any]:
    records = rows("SELECT * FROM avatars WHERE user_id=? AND active=1", (user_id,))
    return {record["view"]: _public_avatar(record) for record in records}


def delete_avatars(user_id: str) -> int:
    records = rows("SELECT * FROM avatars WHERE user_id=?", (user_id,))
    for record in records:
        _delete_avatar_files(user_id, record["avatar_id"], record["avatar_path"], record["parsing_path"])
    return len(records)


# -- renders --------------------------------------------------------------------------

def _public_render(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "render_id": record["render_id"],
        "status": record["status"],
        "stage": record["stage"],
        "progress": round(float(record["progress"]), 3),
        "item_ids": json.loads(record["item_ids"]),
        "recommendation_id": record["recommendation_id"],
        "image_url": signed_media_url(record["user_id"], record["result_path"]) if record["result_path"] else None,
        "not_rendered": json.loads(record["skipped_json"] or "[]"),
        "error": record["error"],
        "saved": bool(record["saved"]),
        "view": (row("SELECT view FROM avatars WHERE avatar_id=?", (record["avatar_id"],)) or {}).get("view"),
        "disclaimer": PREVIEW_DISCLAIMER,
        "created_at": record["created_at"],
    }


def get_render(user_id: str, render_id: str) -> dict[str, Any]:
    record = row("SELECT * FROM tryon_renders WHERE render_id=? AND user_id=?", (render_id, user_id))
    if record is None:
        raise KeyError(render_id)
    return _public_render(record)


def request_render(
    user_id: str, item_ids: list[str], view: str = "front", recommendation_id: str | None = None,
) -> dict[str, Any]:
    """Queue (or reuse) a render of these wardrobe items on the user's avatar."""
    if not settings.tryon_enabled:
        raise RuntimeError("Virtual try-on is turned off on this server (AURA_TRYON_ENABLED=0).")
    missing = model.missing_files()
    if missing:
        raise RuntimeError("The try-on model is not installed yet. Run `python -m training.download_tryon_models`.")
    avatar = row("SELECT * FROM avatars WHERE user_id=? AND view=? AND active=1", (user_id, view))
    if avatar is None:
        raise LookupError(f"Upload a {view} full-body photo first to create your avatar.")
    items = rows(
        "SELECT item_id, category, subcategory, color_name, image_path FROM clothing_items "
        f"WHERE user_id=? AND item_id IN ({','.join('?' for _ in item_ids)})",
        (user_id, *item_ids),
    )
    if len(items) != len(set(item_ids)):
        raise ValueError("A try-on can only use items from your own wardrobe.")
    cache_key = f"{avatar['avatar_id']}|{','.join(sorted(item_ids))}|{settings.tryon_width}x{settings.tryon_height}|{settings.tryon_steps}"
    cached = row(
        "SELECT * FROM tryon_renders WHERE user_id=? AND cache_key=? AND status IN ('queued','running','done') "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id, cache_key),
    )
    if cached:
        if recommendation_id and not cached["recommendation_id"]:
            with connection() as db:
                db.execute("UPDATE tryon_renders SET recommendation_id=? WHERE render_id=?", (recommendation_id, cached["render_id"]))
            cached["recommendation_id"] = recommendation_id
        return _public_render(cached)
    render_id = f"look_{uuid.uuid4().hex[:12]}"
    now = utc_now()
    with connection() as db:
        db.execute(
            """INSERT INTO tryon_renders(render_id,user_id,avatar_id,cache_key,item_ids,recommendation_id,
               status,stage,progress,created_at,updated_at) VALUES (?,?,?,?,?,?,'queued','Waiting to start',0,?,?)""",
            (render_id, user_id, avatar["avatar_id"], cache_key, json.dumps(item_ids), recommendation_id, now, now),
        )
    _ensure_worker()
    _jobs.put(render_id)
    return get_render(user_id, render_id)


def set_saved(user_id: str, render_id: str, saved: bool = True) -> dict[str, Any]:
    with connection() as db:
        cursor = db.execute(
            "UPDATE tryon_renders SET saved=? WHERE render_id=? AND user_id=? AND status='done'",
            (int(saved), render_id, user_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(render_id)
    return get_render(user_id, render_id)


def saved_looks(user_id: str) -> list[dict[str, Any]]:
    records = rows(
        "SELECT * FROM tryon_renders WHERE user_id=? AND saved=1 AND status='done' ORDER BY updated_at DESC",
        (user_id,),
    )
    return [_public_render(record) for record in records]


def plan_layers(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Order garments for rendering; return (layers, names of pieces not rendered)."""
    skipped = [f"{item['color_name']} {item['subcategory']}" for item in items if item["category"] in NOT_RENDERED]
    layers = sorted((item for item in items if item["category"] in LAYER_ORDER), key=lambda item: LAYER_ORDER[item["category"]])
    if any(item["category"] == "Dress" for item in layers):
        # A dress already covers top and bottom; any separates alongside it are not layered.
        dress_skip = [item for item in layers if item["category"] in {"Top", "Bottom"}]
        skipped += [f"{item['color_name']} {item['subcategory']}" for item in dress_skip]
        layers = [item for item in layers if item not in dress_skip]
    return layers, skipped


# -- worker ---------------------------------------------------------------------------

_jobs: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
_last_used = 0.0


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work_loop, name="tryon-worker", daemon=True)
            _worker.start()


def _update(render_id: str, **fields: Any) -> None:
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in fields)
    with connection() as db:
        db.execute(f"UPDATE tryon_renders SET {assignments} WHERE render_id=?", (*fields.values(), render_id))


def _work_loop() -> None:
    global _last_used
    while True:
        try:
            render_id = _jobs.get(timeout=60)
        except queue.Empty:
            if model.loaded and time.time() - _last_used > IDLE_UNLOAD_SECONDS:
                LOGGER.info("Unloading idle try-on model")
                model.unload()
            continue
        try:
            _run(render_id)
        except Exception as exc:  # noqa: BLE001 - surface every failure to the user
            LOGGER.exception("Try-on render %s failed", render_id)
            _update(render_id, status="failed", stage="Failed", error=_friendly_error(exc))
        finally:
            _last_used = time.time()


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "out of memory" in text.lower() or "MPS backend out of memory" in text:
        return "The computer ran out of memory while rendering. Close other apps and try again."
    return f"Render failed: {text[:300]}"


def _run(render_id: str) -> None:
    record = row("SELECT * FROM tryon_renders WHERE render_id=?", (render_id,))
    if record is None or record["status"] != "queued":
        return
    avatar = row("SELECT * FROM avatars WHERE avatar_id=?", (record["avatar_id"],))
    if avatar is None:
        _update(render_id, status="failed", error="The avatar was replaced or deleted.")
        return
    item_ids = json.loads(record["item_ids"])
    items = rows(
        f"SELECT item_id, category, subcategory, color_name, image_path FROM clothing_items "
        f"WHERE user_id=? AND item_id IN ({','.join('?' for _ in item_ids)})",
        (record["user_id"], *item_ids),
    )
    layers, skipped = plan_layers(items)
    if not layers:
        _update(render_id, status="failed", error="This outfit has no garments that can be rendered (only shoes or accessories).")
        return
    _update(render_id, status="running", stage="Loading the try-on model", progress=0.02, skipped_json=json.dumps(skipped))
    model.load()
    person = Image.open(avatar["avatar_path"]).convert("RGB")
    original = person.copy()
    parsing = np.asarray(Image.open(avatar["parsing_path"]))
    landmarks = np.asarray(json.loads(avatar["landmarks_json"]), dtype=np.float32)
    total = len(layers)
    for index, item in enumerate(layers):
        name = f"{item['color_name']} {item['subcategory']}".strip()
        _update(render_id, stage=f"Preparing {name}", progress=(index + 0.02) / total)
        garment = body_analysis.garment_cutter.cut(Image.open(item["image_path"]))
        region = body_analysis.GARMENT_REGION[item["category"]]
        mask = body_analysis.tryon_mask(parsing, landmarks, region)

        def report(fraction: float, index=index, name=name) -> None:
            _update(render_id, stage=f"Dressing your avatar: {name} ({index + 1}/{total})",
                    progress=min(0.99, (index + 0.05 + 0.95 * fraction) / total))

        person = render_region(person, garment, mask, progress=report)
        if region in {"lower", "overall"}:
            # Shorter bottoms leave slivers of the photo's old trousers beside the hands and
            # over the ankles (areas the mask protects); fill them from their surroundings.
            leftover = body_analysis.leftover_bottom(
                original, parsing, landmarks, np.asarray(mask) > 0,
                rendered=person, new_colour=body_analysis.garment_colour_lab(garment),
            )
            person = body_analysis.remove_leftover(person, leftover, landmarks)
    result_path = _save_png(person, "look")
    _update(render_id, status="done", stage="Ready", progress=1.0, result_path=str(result_path))


def crop_box(mask: Image.Image, aspect: float, context: float = 0.12) -> tuple[int, int, int, int]:
    """A box of the given width/height aspect around the mask, with some surrounding context.

    Rendering a crop instead of the whole full-body avatar gives the try-on model several
    times more pixels on the garment (it was trained on people filling the frame).
    """
    width, height = mask.size
    left, top, right, bottom = mask.getbbox() or (0, 0, width, height)
    box_h = (bottom - top) * (1 + 2 * context)
    box_w = (right - left) * (1 + 2 * context)
    if box_w / box_h > aspect:
        box_h = box_w / aspect
    else:
        box_w = box_h * aspect
    box_h, box_w = min(box_h, height), min(box_w, width)
    if box_w / box_h > aspect:  # clipped by the image height: shrink width to keep the aspect
        box_w = box_h * aspect
    else:
        box_h = box_w / aspect
    cx, cy = (left + right) / 2, (top + bottom) / 2
    x0 = int(round(min(max(0, cx - box_w / 2), width - box_w)))
    y0 = int(round(min(max(0, cy - box_h / 2), height - box_h)))
    return x0, y0, int(round(x0 + box_w)), int(round(y0 + box_h))


def render_region(person: Image.Image, garment: Image.Image, mask: Image.Image, progress=None) -> Image.Image:
    """Try the garment on inside ``mask``: render a 3:4 crop around it, then paste it back."""
    from PIL import ImageFilter

    size = (settings.tryon_width, settings.tryon_height)
    box = crop_box(mask, size[0] / size[1])
    crop_person, crop_mask = person.crop(box), mask.crop(box)
    rendered = model(
        crop_person.resize(size, Image.LANCZOS),
        garment,
        crop_mask.resize(size, Image.NEAREST),
        size=size,
        steps=settings.tryon_steps,
        guidance=settings.tryon_guidance,
        seed=42,  # fixed seed: the same avatar + outfit always renders the same way
        progress=progress,
    )
    upscaled = rendered.resize(crop_person.size, Image.LANCZOS)
    soft = crop_mask.filter(ImageFilter.GaussianBlur(max(1, crop_person.width // 160)))
    result = person.copy()
    result.paste(Image.composite(upscaled, crop_person, soft), box[:2])
    return result


def owns_media(user_id: str, path: Path) -> bool:
    """Whether ``path`` is this user's avatar or try-on render (for signed media serving)."""
    text = str(path)
    return bool(
        rows("SELECT 1 FROM avatars WHERE user_id=? AND avatar_path=? LIMIT 1", (user_id, text))
        or rows("SELECT 1 FROM tryon_renders WHERE user_id=? AND result_path=? LIMIT 1", (user_id, text))
    )
