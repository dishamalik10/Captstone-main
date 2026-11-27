"""My Virtual Look: personal avatar + virtual try-on of recommended outfits.

Flow: full-body photo -> body analysis (services.body_analysis) -> avatar (the user's
own photo on a plain backdrop) -> AI Stylist outfit -> CatVTON renders each garment
onto the avatar in layers (bottom, top, outer layer; a dress as one full-body
garment) -> the user previews the look.

Render jobs are rows in ``tryon_renders``. The API only queues them (with per-user,
per-day and global limits); a separate worker process (``services.tryon_worker``,
started by the API) claims and renders them one at a time, because the diffusion
model needs most of an 8 GB machine and must not share a process with the API. Looks
are cached per avatar + outfit, so revisiting one is instant. Every render is a
generated visual preview: it is not a physical garment-fit or size simulation.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from database import connection, row, rows, utc_now
from ml.catvton import CatVTON
from services import body_analysis, body_measurements, tryon_fit
from services.media_access import signed_media_url
from services.media_paths import media_name, media_path, migrate_to_names
from services.resource_report import peak_rss_mb
from settings import settings

LOGGER = logging.getLogger(__name__)
VIEWS = ("front", "side")
LAYER_ORDER = {"Bottom": 0, "Dress": 0, "Top": 1, "Outerwear": 2}
NOT_RENDERED = {"Footwear", "Accessory"}
IDLE_UNLOAD_SECONDS = 600
HEARTBEAT_FRESH_SECONDS = 90


class TryOnLimitError(RuntimeError):
    """A fair-use limit was reached (served as HTTP 429)."""
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
            CREATE INDEX IF NOT EXISTS ix_tryon_status ON tryon_renders(status, created_at);

            -- One row per render started, kept even if the look is later deleted, so
            -- deleting looks or the avatar cannot reset the daily limit.
            CREATE TABLE IF NOT EXISTS tryon_usage (
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_tryon_usage ON tryon_usage(user_id, created_at);

            -- Written by the worker process; read by the API for /tryon/status.
            CREATE TABLE IF NOT EXISTS tryon_worker (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                pid INTEGER,
                model_loaded INTEGER NOT NULL DEFAULT 0,
                heartbeat_at TEXT
            );
            """
        )
        # Files are stored by name inside the upload folder (portable data).
        migrate_to_names(db, "avatars", ("avatar_path", "parsing_path"))
        # Data minimisation (4.3): stored parsing maps and landmarks are no longer kept.
        for record in db.execute("SELECT avatar_id, parsing_path FROM avatars WHERE parsing_path != ''").fetchall():
            media_path(record["parsing_path"]).unlink(missing_ok=True)
            db.execute("UPDATE avatars SET parsing_path='', landmarks_json='[]' WHERE avatar_id=?", (record["avatar_id"],))
        migrate_to_names(db, "tryon_renders", ("result_path",))
        worker_columns = {column["name"] for column in db.execute("PRAGMA table_info(tryon_worker)")}
        if "peak_rss_mb" not in worker_columns:
            db.execute("ALTER TABLE tryon_worker ADD COLUMN peak_rss_mb INTEGER")
        # A render that was mid-way when the server stopped cannot resume. Queued jobs
        # stay queued: the worker picks them up when it starts.
        db.execute(
            "UPDATE tryon_renders SET status='failed', stage='Failed', "
            "error='Interrupted by a server restart; try again.' WHERE status='running'"
        )


# -- status ---------------------------------------------------------------------------

def _worker_state() -> dict[str, Any]:
    record = row("SELECT pid, model_loaded, heartbeat_at, peak_rss_mb FROM tryon_worker WHERE id=1")
    if not record or not record["heartbeat_at"]:
        return {"running": False, "model_loaded": False, "peak_rss_mb": None}
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["heartbeat_at"])).total_seconds()
    running = age < HEARTBEAT_FRESH_SECONDS
    return {
        "running": running,
        "model_loaded": running and bool(record["model_loaded"]),
        "peak_rss_mb": record["peak_rss_mb"] if running else None,
    }


def worker_resources() -> dict[str, Any]:
    """The worker's state for /health: whether it runs, holds the model, and its peak RSS."""
    return _worker_state()


def status() -> dict[str, Any]:
    missing = model.missing_files()
    worker = _worker_state()
    return {
        "enabled": settings.tryon_enabled,
        "body_analysis_ready": body_analysis.models_ready(),
        "tryon_ready": settings.tryon_enabled and not missing,
        "missing_files": missing + body_analysis._models.missing(),
        "loaded": worker["model_loaded"],
        "worker_running": worker["running"],
        "engine": f"CatVTON (Stable Diffusion 1.5 inpainting, {settings.tryon_attention} attention)",
        "render_size": f"{settings.tryon_width}x{settings.tryon_height}",
        "steps": settings.tryon_steps,
        "queue_length": _queue_length(),
        "limits": {
            "active_per_user": settings.tryon_max_active_per_user,
            "per_day": settings.tryon_daily_limit,
            "queue": settings.tryon_queue_limit,
        },
        "disclaimer": PREVIEW_DISCLAIMER,
    }


def _queue_length() -> int:
    record = row("SELECT COUNT(*) AS n FROM tryon_renders WHERE status IN ('queued','running')")
    return int(record["n"]) if record else 0


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
    # Only the avatar image and its summary are kept. The body parsing map and pose
    # landmarks are rebuilt from the avatar when a render runs (data minimisation, 4.3).
    avatar_path = _save_png(avatar, "avatar")
    avatar_id = f"avatar_{uuid.uuid4().hex[:12]}"
    with connection() as db:
        old = db.execute(
            "SELECT avatar_id, avatar_path, parsing_path FROM avatars WHERE user_id=? AND view=?",
            (user_id, view),
        ).fetchall()
        db.execute(
            """INSERT INTO avatars(avatar_id,user_id,view,avatar_path,parsing_path,landmarks_json,analysis_json,active,created_at)
               VALUES (?,?,?,?,?,?,?,1,?)""",
            (avatar_id, user_id, view, media_name(avatar_path), "", "[]", json.dumps(analysis), utc_now()),
        )
    # A new photo replaces the old avatar for this view, with its renders and files.
    for record in old:
        _delete_avatar_files(user_id, record["avatar_id"], record["avatar_path"], record["parsing_path"])
    return _public_avatar(row("SELECT * FROM avatars WHERE avatar_id=?", (avatar_id,)))


def _delete_avatar_files(user_id: str, avatar_id: str, avatar_path: str, parsing_path: str) -> None:
    for render in rows("SELECT result_path FROM tryon_renders WHERE avatar_id=?", (avatar_id,)):
        if render["result_path"]:
            media_path(render["result_path"]).unlink(missing_ok=True)
    with connection() as db:
        db.execute("DELETE FROM tryon_renders WHERE avatar_id=?", (avatar_id,))
        db.execute("DELETE FROM avatars WHERE avatar_id=? AND user_id=?", (avatar_id, user_id))
    media_path(avatar_path).unlink(missing_ok=True)
    if parsing_path:
        media_path(parsing_path).unlink(missing_ok=True)


def front_avatar_image(user_id: str) -> Image.Image:
    """The user's active front avatar image (for measuring, 4.11)."""
    record = row("SELECT avatar_path FROM avatars WHERE user_id=? AND view='front' AND active=1", (user_id,))
    if record is None:
        raise LookupError("No front avatar.")
    with Image.open(media_path(record["avatar_path"])) as image:
        return image.convert("RGB")


def get_avatars(user_id: str) -> dict[str, Any]:
    records = rows("SELECT * FROM avatars WHERE user_id=? AND active=1", (user_id,))
    return {record["view"]: _public_avatar(record) for record in records}


def delete_avatars(user_id: str) -> int:
    """Delete all body data: photos, avatars, renders, measurements, height and the consent record."""
    records = rows("SELECT * FROM avatars WHERE user_id=?", (user_id,))
    for record in records:
        _delete_avatar_files(user_id, record["avatar_id"], record["avatar_path"], record["parsing_path"])
    # Measurements and height are body data too (4.11, VQ10).
    body_measurements.delete(user_id)
    user = row("SELECT profile_json FROM users WHERE user_id=?", (user_id,)) or {}
    profile = json.loads(user.get("profile_json") or "{}")
    profile.pop("heightCm", None)
    with connection() as db:
        db.execute("UPDATE users SET body_consent_at=NULL, profile_json=? WHERE user_id=?",
                   (json.dumps(profile), user_id))
    return len(records)


class ConsentRequired(PermissionError):
    """The user has not confirmed the body-photo consent statement yet."""


CONSENT_MESSAGE = (
    "Before AURA stores a body photo, confirm that the photo is of you, that you are 18 or "
    "over, and that you agree to AURA storing it until you delete it."
)


def require_consent(user_id: str, consent_given: bool) -> None:
    """Record consent the first time it is given; refuse a body photo without it."""
    record = row("SELECT body_consent_at FROM users WHERE user_id=?", (user_id,))
    if record and record["body_consent_at"]:
        return
    if not consent_given:
        raise ConsentRequired(CONSENT_MESSAGE)
    with connection() as db:
        db.execute("UPDATE users SET body_consent_at=? WHERE user_id=? AND body_consent_at IS NULL", (utc_now(), user_id))


def has_consent(user_id: str) -> bool:
    record = row("SELECT body_consent_at FROM users WHERE user_id=?", (user_id,))
    return bool(record and record["body_consent_at"])


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
    items = _render_items(user_id, item_ids)
    if len(items) != len(set(item_ids)):
        raise ValueError("A try-on can only use items from your own wardrobe.")
    cache_key = f"{avatar['avatar_id']}|{','.join(sorted(item_ids))}|{settings.tryon_width}x{settings.tryon_height}|{settings.tryon_steps}"
    fit_key = tryon_fit.signature(items, *_body_for_fit(user_id)[:2])
    if fit_key:
        # Sizes change the mask (4.11): a new size or new measurements mean a new render.
        cache_key += f"|fit:{fit_key}"
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
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with connection() as db:
        # Check the limits and queue the job in one write transaction, so two requests
        # arriving together cannot both slip under a limit.
        db.execute("BEGIN IMMEDIATE")
        active = db.execute(
            "SELECT COUNT(*) FROM tryon_renders WHERE user_id=? AND status IN ('queued','running')", (user_id,),
        ).fetchone()[0]
        if active >= settings.tryon_max_active_per_user:
            raise TryOnLimitError("You already have a look rendering. Wait for it to finish, then try the next one.")
        today = db.execute(
            "SELECT COUNT(*) FROM tryon_usage WHERE user_id=? AND created_at > ?", (user_id, day_ago),
        ).fetchone()[0]
        if today >= settings.tryon_daily_limit:
            raise TryOnLimitError(
                f"You have used today's {settings.tryon_daily_limit} new try-on renders. "
                "Looks you already rendered still open instantly; new ones are available again tomorrow."
            )
        waiting = db.execute("SELECT COUNT(*) FROM tryon_renders WHERE status IN ('queued','running')").fetchone()[0]
        if waiting >= settings.tryon_queue_limit:
            raise TryOnLimitError("The try-on queue is full right now. Please try again in a few minutes.")
        db.execute(
            """INSERT INTO tryon_renders(render_id,user_id,avatar_id,cache_key,item_ids,recommendation_id,
               status,stage,progress,created_at,updated_at) VALUES (?,?,?,?,?,?,'queued','Waiting to start',0,?,?)""",
            (render_id, user_id, avatar["avatar_id"], cache_key, json.dumps(item_ids), recommendation_id, now, now),
        )
        db.execute("INSERT INTO tryon_usage(user_id, created_at) VALUES (?, ?)", (user_id, now))
    return get_render(user_id, render_id)


def delete_render(user_id: str, render_id: str) -> None:
    """Delete one of the user's looks (a queued job is cancelled; a running one is
    abandoned and its result discarded when the worker finishes)."""
    record = row("SELECT result_path FROM tryon_renders WHERE render_id=? AND user_id=?", (render_id, user_id))
    if record is None:
        raise KeyError(render_id)
    with connection() as db:
        db.execute("DELETE FROM tryon_renders WHERE render_id=? AND user_id=?", (render_id, user_id))
    if record["result_path"]:
        media_path(record["result_path"]).unlink(missing_ok=True)


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


def _render_items(user_id: str, item_ids: list[str]) -> list[dict[str, Any]]:
    items = rows(
        "SELECT item_id, category, subcategory, color_name, image_path, fit, size_json FROM clothing_items "
        f"WHERE user_id=? AND item_id IN ({','.join('?' for _ in item_ids)})",
        (user_id, *item_ids),
    )
    for item in items:
        item["size"] = json.loads(item.pop("size_json") or "null")
    return items


def _body_for_fit(user_id: str) -> tuple[float | None, dict[str, dict[str, Any]], str | None]:
    """(height cm, merged measurements, fit preference) used to shape the try-on mask."""
    user = row("SELECT profile_json FROM users WHERE user_id=?", (user_id,)) or {}
    height = json.loads(user.get("profile_json") or "{}").get("heightCm")
    preference = row("SELECT fit_preference FROM preferences WHERE user_id=?", (user_id,)) or {}
    return (float(height) if height else None), body_measurements.merged(user_id), preference.get("fit_preference")


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


# -- worker (runs in the try-on worker process) -----------------------------------------

def _update(render_id: str, **fields: Any) -> None:
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in fields)
    with connection() as db:
        db.execute(f"UPDATE tryon_renders SET {assignments} WHERE render_id=?", (*fields.values(), render_id))


def _exists(render_id: str) -> bool:
    return row("SELECT 1 AS ok FROM tryon_renders WHERE render_id=?", (render_id,)) is not None


def claim_next() -> str | None:
    """Atomically move the oldest queued job to 'running' and return its id."""
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        record = db.execute(
            "SELECT render_id FROM tryon_renders WHERE status='queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if record is None:
            return None
        db.execute(
            "UPDATE tryon_renders SET status='running', stage='Starting', updated_at=? WHERE render_id=?",
            (utc_now(), record["render_id"]),
        )
        return record["render_id"]


def process_next() -> bool:
    """Render the oldest queued job, if any. Returns whether a job was processed."""
    render_id = claim_next()
    if render_id is None:
        return False
    try:
        _run(render_id)
    except Exception as exc:  # noqa: BLE001 - surface every failure to the user
        LOGGER.exception("Try-on render %s failed", render_id)
        _update(render_id, status="failed", stage="Failed", error=_friendly_error(exc))
    return True


def recover_interrupted() -> None:
    """Called when a worker starts: a 'running' job belongs to a worker that died."""
    with connection() as db:
        db.execute(
            "UPDATE tryon_renders SET status='failed', stage='Failed', "
            "error='The renderer stopped unexpectedly; try again.' WHERE status='running'"
        )


def heartbeat() -> None:
    with connection() as db:
        db.execute(
            """INSERT INTO tryon_worker(id, pid, model_loaded, heartbeat_at, peak_rss_mb) VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET pid=excluded.pid, model_loaded=excluded.model_loaded,
               heartbeat_at=excluded.heartbeat_at, peak_rss_mb=excluded.peak_rss_mb""",
            (os.getpid(), int(model.loaded), utc_now(), peak_rss_mb()),
        )


def cleanup_expired(now: datetime | None = None) -> int:
    """Delete unsaved looks (and failed renders) older than the retention period,
    and usage rows older than two days. Returns the number of looks deleted."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=settings.tryon_retention_days)).isoformat()
    expired = rows(
        "SELECT render_id, result_path FROM tryon_renders "
        "WHERE saved=0 AND status IN ('done','failed') AND created_at < ?",
        (cutoff,),
    )
    with connection() as db:
        for record in expired:
            db.execute("DELETE FROM tryon_renders WHERE render_id=?", (record["render_id"],))
        db.execute("DELETE FROM tryon_usage WHERE created_at < ?", ((now - timedelta(days=2)).isoformat(),))
    for record in expired:
        if record["result_path"]:
            media_path(record["result_path"]).unlink(missing_ok=True)
    return len(expired)


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "out of memory" in text.lower() or "MPS backend out of memory" in text:
        return "The computer ran out of memory while rendering. Close other apps and try again."
    return "Render failed. Please try again; if it keeps failing, try a different photo or outfit."


def _run(render_id: str) -> None:
    record = row("SELECT * FROM tryon_renders WHERE render_id=?", (render_id,))
    if record is None or record["status"] != "running":
        return
    avatar = row("SELECT * FROM avatars WHERE avatar_id=?", (record["avatar_id"],))
    if avatar is None:
        _update(render_id, status="failed", error="The avatar was replaced or deleted.")
        return
    item_ids = json.loads(record["item_ids"])
    items = _render_items(record["user_id"], item_ids)
    height_cm, body, preference = _body_for_fit(record["user_id"])
    layers, skipped = plan_layers(items)
    if not layers:
        _update(render_id, status="failed", error="This outfit has no garments that can be rendered (only shoes or accessories).")
        return
    _update(render_id, status="running", stage="Preparing your clothes", progress=0.01, skipped_json=json.dumps(skipped))
    garments = cut_garments([media_path(item["image_path"]) for item in layers])
    _update(render_id, stage="Loading the try-on model", progress=0.02)
    model.load()
    person = Image.open(media_path(avatar["avatar_path"])).convert("RGB")
    original = person.copy()
    parsing, landmarks = avatar_body_map(person)
    total = len(layers)
    for index, item in enumerate(layers):
        if not _exists(render_id):
            LOGGER.info("Try-on render %s was deleted; stopping", render_id)
            return
        name = f"{item['color_name']} {item['subcategory']}".strip()
        _update(render_id, stage=f"Preparing {name}", progress=(index + 0.02) / total)
        garment = garments[index]
        region = body_analysis.GARMENT_REGION[item["category"]]
        fit = tryon_fit.mask_fit(item, parsing, landmarks, height_cm, body, preference)
        mask = body_analysis.tryon_mask(parsing, landmarks, region, fit)

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
    _finish_render(render_id, person)


def _cut_to_png(path: str) -> bytes:
    """Child-process entry point for ``cut_garments``: one garment, cut out, as PNG bytes."""
    buffer = BytesIO()
    body_analysis.garment_cutter.cut(Image.open(path)).save(buffer, format="PNG")
    return buffer.getvalue()


def cut_garments(paths: list[Path]) -> list[Image.Image]:
    """Cut out every garment of a render before the diffusion model runs.

    ISNet needs ~2 GB of CPU memory at 1024x1024 and onnxruntime keeps it after use, so
    in the worker it would sit beside the ~5 GB diffusion peak (measured in ENGINEERING_PLAN
    step 3). In a short-lived child process that memory goes back to the system on exit.
    """
    if not (settings.tryon_isolate_cutout and body_analysis.garment_cutter.available()):
        return [body_analysis.garment_cutter.cut(Image.open(path)) for path in paths]
    import multiprocessing

    with multiprocessing.get_context("spawn").Pool(1) as pool:
        encoded = pool.map(_cut_to_png, [str(path) for path in paths])
    return [Image.open(BytesIO(data)).convert("RGB") for data in encoded]


def avatar_body_map(avatar: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Parsing map and pose landmarks for an avatar, rebuilt from the avatar image
    (the person on a plain backdrop) instead of being stored."""
    parsed = body_analysis.parse_photo(avatar)
    return body_analysis.keep_person_only(parsed.parsing), parsed.landmarks


def _finish_render(render_id: str, image: Image.Image) -> bool:
    """Store the finished look, unless it was deleted (or its avatar replaced) while
    rendering, in which case the image is discarded. Returns whether it was stored."""
    result_path = _save_png(image, "look")
    with connection() as db:
        updated = db.execute(
            "UPDATE tryon_renders SET status='done', stage='Ready', progress=1.0, result_path=?, updated_at=? "
            "WHERE render_id=? AND status='running'",
            (media_name(result_path), utc_now(), render_id),
        ).rowcount
    if not updated:
        result_path.unlink(missing_ok=True)
    return bool(updated)


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
    text = media_name(path)
    return bool(
        rows("SELECT 1 FROM avatars WHERE user_id=? AND avatar_path=? LIMIT 1", (user_id, text))
        or rows("SELECT 1 FROM tryon_renders WHERE user_id=? AND result_path=? LIMIT 1", (user_id, text))
    )
