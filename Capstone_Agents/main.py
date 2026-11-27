from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from pathlib import PurePosixPath

import asyncio
import json
import logging
import sqlite3
import time

import anyio
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from contracts.api_schemas import (
    ClothingItemResponse,
    ClothingItemUpdate,
    ConversationStart,
    DonationRequest,
    ListingUpdate,
    MarketMessageCreate,
    OrderStatusUpdate,
    ImportLinkRequest,
    FeedbackRequest,
    PreferenceUpdate,
    RecommendationRequest,
    RecommendationResponse,
    SignupRequest,
    DeleteAccountRequest,
    ReportCreate,
    ImportConfirm,
    ImportPreviewResponse,
    LoginRequest,
    MeasurementUpdate,
    ProfileUpdate,
    OrderRequest,
    ChatRequest,
    ProductCreate,
    PostCreate,
    TryOnRequest,
)
from database import ensure_user, init_database, rows
from services.preference_service import get_preferences, save_preferences
from services.recommendation_service import record_explanations, recommend, save_feedback
from services.recommendation_explainer import explain_recommendations
from services.season_classifier import target_season
from services.vision_service import vision_service
from services.style_analysis_service import analyze_style
from services.donation_service import mark_donated, unworn_items, unworn_items_csv
from services.product_link_service import ProductLinkError, import_from_link
from services.purchase_impact_service import analyze_purchase_impact
from services.trend_service import current_fashion_trends
from services.local_llm import LocalModelError, get_model_info, local_llm
from services.compatibility_service import compatibility_model_status
from services import body_measurements, fit_advice, outfit_compat_service, stylist_selector, tryon_service, tryon_worker
from services.body_analysis import BodyPhotoError
from services.aura_fashion_lm import (
    model_info as fashion_lm_model_info,
    unload_model as unload_fashion_model,
)
from services.media_access import (
    verify_media_signature,
)
from services.wardrobe_service import (
    create_item,
    delete_item,
    get_item,
    list_items,
    replace_image,
    update_item,
)
from io import BytesIO

from services import import_previews
from services.garment_cutout import cutout_garment
from services import marketplace_service as market
from services.marketplace_service import MarketplaceError
from services.realtime import chat_partners, conversation_members, hub
from services.image_slots import ImageBusyError, image_slot
from services.media_paths import media_path
from services import moderation_service as moderation
from services import rate_limits
from services.weather_cache import cached_weather
from services.image_sanitize import ImageRejected, reencode
from services.account_service import AccountError, delete_account
from services.resource_report import peak_rss_mb, resident_models
from settings import settings
from logging_config import configure_logging
from request_logging import RequestLoggingMiddleware
from services.app_service import (
    chat,
    chat_history,
    create_post,
    get_user,
    login,
    logout,
    logout_everywhere,
    session_user,
    signup,
    social_feed,
    toggle_follow,
    toggle_like,
    update_user,
)

configure_logging(settings.log_dir)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def current_auth(
    authorization: str | None = Header(default=None),
) -> tuple[dict, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required.")
    token = authorization.removeprefix("Bearer ").strip()
    user = session_user(token)
    if not user:
        raise HTTPException(401, "Session expired or invalid.")
    return user, token


def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    """The signed-in user if a valid token was sent, else None (for public routes)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return session_user(authorization.removeprefix("Bearer ").strip())


def per_user(*buckets: str):
    """A ``current_auth`` dependency that also counts this request against per-user limits."""
    def dependency(auth: tuple[dict, str] = Depends(current_auth)) -> tuple[dict, str]:
        for bucket in buckets:
            rate_limits.hit(bucket, auth[0]["id"])
        return auth

    return dependency


def _ip(request: Request) -> str:
    return rate_limits.client_ip(request.headers, request.client.host if request.client else None)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.getenv("AURA_MEDIA_SIGNING_KEY"):
        # Without a fixed key a random one is made per process, so every restart
        # breaks all image links the app has already received.
        raise RuntimeError(
            "AURA_MEDIA_SIGNING_KEY is not set. Add a long random value to Capstone_Agents/.env, e.g. "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    init_database()
    tryon_service.init_tables()
    import_previews.cleanup_expired()
    if settings.preload_vision and settings.model_path.is_file():
        try:
            vision_service.load()
        except Exception:
            logging.getLogger(__name__).exception("Garment CNN startup load failed")
    # Load only the model that serves chat (the fine-tuned stylist when installed),
    # so an 8 GB host does not hold two 1 GB GGUFs at startup.
    chat_model = stylist_selector.chat_llm()
    if chat_model is not local_llm or settings.llm_model_path.is_file():
        try:
            chat_model.load_model()
        except Exception:
            logging.getLogger(__name__).exception("Local LLM startup load failed")
    if not settings.tryon_enabled and not tryon_service.model.missing_files():
        # The models are downloaded but try-on is off: the default for 8 GB machines.
        logging.getLogger(__name__).warning(
            "Virtual try-on is OFF (AURA_TRYON_ENABLED is not 1). On the 16 GB host, add "
            "AURA_TRYON_ENABLED=1 and AURA_PRELOAD_VISION=1 to Capstone_Agents/.env and restart."
        )
    if tryon_worker.should_spawn():
        tryon_worker.supervisor.start()
    try:
        yield
    finally:
        tryon_worker.supervisor.stop()
        chat_model.unload_model()
        local_llm.unload_model()
        unload_fashion_model()
        tryon_service.model.unload()


app = FastAPI(
    title="AURA Personalized Wardrobe API",
    version="2.0.0",
    description="CNN-powered wardrobe recognition and personalized outfit ranking.",
    lifespan=lifespan,
)
# Added before CORS so it sits inside it: error responses still carry CORS headers.
app.add_middleware(RequestLoggingMiddleware)
@app.exception_handler(rate_limits.RateLimited)
def rate_limited(_request, exc: rate_limits.RateLimited) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(exc)}, headers={"Retry-After": str(exc.retry_after)})


@app.exception_handler(ImageRejected)
def image_rejected(_request, exc: ImageRejected) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(sqlite3.IntegrityError)
def integrity_error(_request, exc: sqlite3.IntegrityError) -> JSONResponse:
    """A database constraint caught a conflict the route did not check for (for example
    two sign-ups with one email at the same moment). Never a 500, never the SQL text."""
    logging.getLogger(__name__).warning("Database constraint rejected a write: %s", exc)
    return JSONResponse(status_code=409, content={"detail": "That conflicts with existing data. Refresh and try again."})


# Browsers only: the Android app sends no Origin. Auth is a bearer header, never a
# cookie, so credentialed CORS is not needed. Production sets AURA_ALLOWED_ORIGINS to
# the web app's origin only (4.7); "*" is for local development.
if settings.allowed_origins == ("*",):
    logging.getLogger(__name__).warning("AURA_ALLOWED_ORIGINS is '*': any website may call this API. Set it to the web app's origin before release.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After", "X-Request-ID"],
)
settings.upload_dir.mkdir(parents=True, exist_ok=True)


def require_owner(user_id: str, auth: tuple[dict, str]) -> str:
    if user_id != auth[0]["id"]:
        raise HTTPException(403, "This resource belongs to another account.")
    return auth[0]["id"]


@app.get("/uploads/{filename}")
def uploaded_image(
    filename: str,
    user_id: str,
    expires: int,
    signature: str,
) -> FileResponse:
    """Serve an owned wardrobe image only through a short-lived signed URL."""
    if PurePosixPath(filename).name != filename or not verify_media_signature(
        user_id, filename, expires, signature
    ):
        raise HTTPException(404, "Image not found or the link has expired.")
    path = settings.upload_dir / filename
    if not path.is_file():
        raise HTTPException(404, "Image not found or the link has expired.")
    owned = rows(
        "SELECT 1 FROM clothing_items WHERE user_id=? AND image_path=? LIMIT 1",
        (user_id, path.name),
    ) or tryon_service.owns_media(user_id, path) or import_previews.owns_media(user_id, path)
    if not owned:
        raise HTTPException(404, "Image not found or the link has expired.")
    return FileResponse(
        path,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=60", "Referrer-Policy": "no-referrer"},
    )


def _is_local_operator(request: Request) -> bool:
    """A request made on the server machine itself (e.g. ``curl localhost:8000/health``).
    Everything arriving through the Cloudflare tunnel carries CF-Connecting-IP."""
    peer = request.client.host if request.client else ""
    return peer in {"127.0.0.1", "::1"} and "cf-connecting-ip" not in request.headers


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    """Public: only "ok". On the server machine itself: models, memory and worker state."""
    if not _is_local_operator(request):
        return {"status": "ok"}
    llm_status = get_model_info()
    llm_status.pop("path", None)
    return {
        "status": "ok",
        "model_present": settings.model_path.is_file(),
        "metadata_present": settings.metadata_path.is_file(),
        "model_loaded": vision_service._model is not None,
        "llm": llm_status,
        "fashion_lm": fashion_lm_model_info(),
        "outfit_compatibility": outfit_compat_service.status()["available"],
        "stylist_llm": stylist_selector.model_source(),
        "chat_llm": stylist_selector.chat_model_source(),
        # Memory go/no-go evidence (ENGINEERING_PLAN step 3). Peak RSS is the high-water
        # mark since each process started.
        "resources": {
            "api_peak_rss_mb": peak_rss_mb(),
            "api_resident_models": resident_models(),
            "tryon_worker": tryon_service.worker_resources(),
        },
    }


@app.post("/auth/signup", status_code=201)
def auth_signup(payload: SignupRequest, request: Request) -> dict:
    rate_limits.hit("signup", _ip(request))
    try:
        user, token = signup(payload.full_name, payload.email, payload.password, payload.client)
        return {"user": user, "token": token}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/auth/login")
def auth_login(payload: LoginRequest) -> dict:
    account = payload.email.strip().lower()
    # Checked before the password, so a locked account can't be probed further.
    rate_limits.check("login_failed", account)
    try:
        user, token = login(payload.email, payload.password, payload.client)
        return {"user": user, "token": token}
    except ValueError as exc:
        rate_limits.record("login_failed", account)
        raise HTTPException(401, str(exc)) from exc


@app.get("/auth/me")
def auth_me(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return auth[0]


@app.post("/auth/logout", status_code=204, response_class=Response)
def auth_logout(auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    logout(auth[1])
    return Response(status_code=204)


@app.post("/auth/logout-all", status_code=204, response_class=Response)
def auth_logout_all(auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    """Sign out on every device (for a lost phone or a shared computer)."""
    logout_everywhere(auth[0]["id"])
    return Response(status_code=204)


@app.post("/auth/delete-account", status_code=204, response_class=Response)
def auth_delete_account(payload: DeleteAccountRequest, auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    """Permanently delete the account and everything it owns (password required)."""
    try:
        delete_account(auth[0]["id"], payload.password)
    except AccountError as exc:
        raise HTTPException(403, str(exc)) from exc
    return Response(status_code=204)


@app.post("/users/me/photo")
def upload_profile_photo(
    file: UploadFile = File(...),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    """Set the profile picture. It is public (shown on posts and listings), so it is
    stored like a listing photo: re-encoded, with no metadata."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    return update_user(auth[0]["id"], {"avatarUrl": market.save_listing_photo(content)})


@app.patch("/users/me")
def patch_profile(
    payload: ProfileUpdate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    return update_user(auth[0]["id"], payload.model_dump(exclude_unset=True))


@app.get("/users/{user_id}")
def public_profile(user_id: str) -> dict:
    try:
        profile = get_user(user_id)
        return {
            key: profile[key]
            for key in ("id", "fullName", "avatarUrl", "itemsCount", "outfitsSaved", "following", "followers")
            if key in profile
        }
    except KeyError as exc:
        raise HTTPException(404, "User not found.") from exc


# -- Report and block (4.4) -----------------------------------------------------------------

def _moderation(call, *args):
    try:
        return call(*args)
    except moderation.ModerationError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@app.post("/reports", status_code=201)
def create_report(payload: ReportCreate, auth: tuple[dict, str] = Depends(per_user("report"))) -> dict:
    """Report a listing, a marketplace conversation, a post or a user for manual review."""
    return _moderation(moderation.report, auth[0]["id"], payload.target_type, payload.target_id,
                       payload.reason, payload.details)


@app.get("/users/me/blocks")
def my_blocks(auth: tuple[dict, str] = Depends(current_auth)) -> list[dict]:
    return moderation.list_blocked(auth[0]["id"])


@app.post("/users/{user_id}/block", status_code=204, response_class=Response)
def block_user(user_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    _moderation(moderation.block, auth[0]["id"], user_id)
    return Response(status_code=204)


@app.delete("/users/{user_id}/block", status_code=204, response_class=Response)
def unblock_user(user_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    moderation.unblock(auth[0]["id"], user_id)
    return Response(status_code=204)


# -- Marketplace: listings, orders and buyer <-> seller chat --------------------------------

def _market(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except MarketplaceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@app.get("/marketplace/products")
def marketplace_products(
    q: str = Query("", max_length=100),
    category: str = Query("", max_length=40),
    viewer: dict | None = Depends(optional_user),
) -> list[dict]:
    """Public browse; a signed-in viewer doesn't see listings from users they blocked."""
    return market.list_products(q, category, viewer["id"] if viewer else None)


@app.post("/marketplace/products", status_code=201)
def marketplace_create_product(
    payload: ProductCreate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    """Create a listing from image URLs (JSON). The app uses /marketplace/listings."""
    return _market(market.create_listing, auth[0]["id"], payload.model_dump())


@app.post("/marketplace/listings", status_code=201)
async def marketplace_create_listing(
    title: str = Form(..., min_length=1, max_length=120),
    price: float = Form(..., gt=0, le=1_000_000),
    category: str = Form(...),
    condition: str = Form(...),
    description: str = Form("", max_length=2000),
    size: str = Form("", max_length=20),
    brand: str = Form("", max_length=60),
    wardrobe_item_id: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    """Sell an item: upload up to 5 photos, and/or reuse a wardrobe item's photo."""
    seller_id = auth[0]["id"]
    if len(files) > market.MAX_PHOTOS:
        raise HTTPException(422, f"A listing can have at most {market.MAX_PHOTOS} photos.")
    image_urls: list[str] = []
    if wardrobe_item_id:
        url, _item = _market(market.copy_wardrobe_photo, seller_id, wardrobe_item_id)
        image_urls.append(url)
    for upload in files:
        if upload.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(415, "Only JPEG, PNG, and WebP photos are accepted.")
        content = await upload.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(413, "A photo is larger than the upload limit.")
        image_urls.append(market.save_listing_photo(content))
    return _market(market.create_listing, seller_id, {
        "title": title, "price": price, "category": category, "condition": condition,
        "description": description, "size": size, "brand": brand,
        "image_urls": image_urls[: market.MAX_PHOTOS], "wardrobe_item_id": wardrobe_item_id,
    })


@app.get("/marketplace/images/{filename}")
def marketplace_image(filename: str) -> FileResponse:
    """Listing photos are public, like any shop's product photos."""
    path = market.image_dir() / filename
    if PurePosixPath(filename).name != filename or not path.is_file():
        raise HTTPException(404, "Image not found.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/marketplace/products/{product_id}")
def marketplace_product(product_id: str) -> dict:
    return _market(market.get_product, product_id)


@app.get("/marketplace/products/{product_id}/fit")
def marketplace_product_fit(product_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    """Size advice for this listing, computed for (and shown only to) the viewer (4.11)."""
    product = _market(market.get_product, product_id)
    return fit_advice.for_listing(auth[0]["id"], product)


@app.patch("/marketplace/listings/{product_id}")
def marketplace_update_listing(
    product_id: str,
    payload: ListingUpdate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    return _market(market.update_listing, auth[0]["id"], product_id, payload.model_dump(exclude_none=True))


@app.delete("/marketplace/listings/{product_id}", status_code=204)
def marketplace_delete_listing(product_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    _market(market.delete_listing, auth[0]["id"], product_id)
    return Response(status_code=204)


@app.post("/marketplace/orders", status_code=201)
def marketplace_order(
    payload: OrderRequest,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    address = payload.shipping_address.model_dump() if payload.shipping_address else None
    order_ids = _market(market.create_order, auth[0]["id"], payload.product_ids, address, payload.payment_method)
    for order in rows(
        "SELECT o.order_id, o.seller_id, p.title FROM orders o JOIN products p ON p.product_id=o.product_id "
        "WHERE o.order_id IN (%s)" % ",".join("?" for _ in order_ids), tuple(order_ids),
    ):
        hub.push([order["seller_id"]], {
            "type": "order", "event": "placed", "orderId": order["order_id"], "productTitle": order["title"],
        })
    return {"order_ids": order_ids}


@app.get("/marketplace/orders/mine")
def marketplace_my_orders(auth: tuple[dict, str] = Depends(current_auth)) -> list[dict]:
    return market.buyer_orders(auth[0]["id"])


@app.post("/marketplace/orders/{order_id}/status")
def marketplace_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    user_id = auth[0]["id"]
    order = _market(market.update_order_status, user_id, order_id, payload.status)
    other = order["buyer"]["id"] if user_id == order["seller"]["id"] else order["seller"]["id"]
    hub.push([other], {"type": "order", "event": order["status"], "orderId": order_id, "productTitle": order["productTitle"]})
    return order


@app.get("/marketplace/seller")
def marketplace_seller(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return market.seller_dashboard(auth[0]["id"])


@app.get("/marketplace/conversations")
def marketplace_conversations(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    user_id = auth[0]["id"]
    conversations = market.list_conversations(user_id)
    for conversation in conversations:
        conversation["otherUser"]["online"] = hub.is_online(conversation["otherUser"]["id"])
    return {"conversations": conversations, "unread": market.unread_count(user_id)}


@app.post("/marketplace/conversations", status_code=201)
def marketplace_start_conversation(
    payload: ConversationStart,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    return _market(market.start_conversation, auth[0]["id"], payload.product_id, payload.buyer_id)


@app.get("/marketplace/conversations/{conversation_id}")
def marketplace_conversation(conversation_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    user_id = auth[0]["id"]
    conversation = _market(market.get_conversation, user_id, conversation_id)
    conversation["otherUser"]["online"] = hub.is_online(conversation["otherUser"]["id"])
    messages = _market(market.conversation_messages, user_id, conversation_id)
    # Opening the thread marked the other person's messages read: show them "Seen".
    hub.push([conversation["otherUser"]["id"]], {"type": "read", "conversationId": conversation_id})
    return {"conversation": conversation, "messages": messages}


@app.post("/marketplace/conversations/{conversation_id}/messages", status_code=201)
def marketplace_send_message(
    conversation_id: str,
    payload: MarketMessageCreate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    user_id = auth[0]["id"]
    message = _market(market.send_message, user_id, conversation_id, payload.body)
    members = conversation_members(conversation_id) or ()
    others = [member for member in members if member != user_id]
    hub.push(others, {"type": "message", "conversationId": conversation_id, "message": {**message, "mine": False}})
    hub.push([user_id], {"type": "message", "conversationId": conversation_id, "message": message})  # other tabs
    return message


MAX_SOCKETS_PER_USER = 3
TYPING_INTERVAL_SECONDS = 2.0


@app.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    """Real-time channel. The first frame must be {"type": "auth", "token": "<session token>"}
    (sent as a message, not in the URL, so the token never lands in access logs)."""
    await websocket.accept()
    try:
        first = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=10))
        token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        token = None
    user = await anyio.to_thread.run_sync(session_user, token) if isinstance(token, str) and token else None
    if not user:
        try:
            await websocket.send_json({"type": "error", "detail": "Authentication required."})
            await websocket.close(code=4401)
        except Exception:
            pass
        return

    user_id = user["id"]
    if hub.socket_count(user_id) >= MAX_SOCKETS_PER_USER:
        try:
            await websocket.send_json({"type": "error", "detail": "Too many open connections. Close AURA on another device or tab."})
            await websocket.close(code=4429)
        except Exception:
            pass
        return
    came_online = hub.connect(user_id, websocket)
    last_typing: dict[str, float] = {}
    partners = await anyio.to_thread.run_sync(chat_partners, user_id)
    try:
        await websocket.send_json({"type": "ready", "online": sorted(p for p in partners if hub.is_online(p))})
        if came_online:
            await hub.send(partners, {"type": "presence", "userId": user_id, "online": True})
        while True:
            try:
                event = json.loads(await websocket.receive_text())
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif event.get("type") == "typing":
                conversation_id = str(event.get("conversationId") or "")[:40]
                now = time.monotonic()
                if now - last_typing.get(conversation_id, -TYPING_INTERVAL_SECONDS) < TYPING_INTERVAL_SECONDS:
                    continue  # throttled: one "typing" notice per conversation every few seconds
                last_typing[conversation_id] = now
                members = await anyio.to_thread.run_sync(conversation_members, conversation_id)
                others = [member for member in members or [] if member != user_id]
                if members and user_id in members and not any(
                    [await anyio.to_thread.run_sync(moderation.blocked_between, user_id, other) for other in others]
                ):
                    await hub.send(
                        [member for member in members if member != user_id],
                        {"type": "typing", "conversationId": conversation_id, "userId": user_id},
                    )
    except WebSocketDisconnect:
        pass
    finally:
        if hub.disconnect(user_id, websocket):
            # Shielded: the "went offline" notice must go out even if this task was cancelled.
            with anyio.CancelScope(shield=True):
                partners = await anyio.to_thread.run_sync(chat_partners, user_id)
                await hub.send(partners, {"type": "presence", "userId": user_id, "online": False})


@app.get("/social/feed")
def read_social_feed(auth: tuple[dict, str] = Depends(current_auth)) -> list[dict]:
    return social_feed(auth[0]["id"])


@app.post("/social/posts", status_code=201)
def social_create_post(
    payload: PostCreate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    return create_post(auth[0]["id"], payload.model_dump())


@app.post("/social/posts/{post_id}/like")
def social_like(post_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    try:
        return {"liked": toggle_like(auth[0]["id"], post_id)}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/social/users/{user_id}/follow")
def social_follow(user_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    try:
        return {"following": toggle_follow(auth[0]["id"], user_id)}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/weather")
def current_weather(
    city: str = Query(min_length=1, max_length=120),
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    """Signed-in users only, cached per city: anyone else could spend the API key's quota."""
    if not os.getenv("OPENWEATHER_API_KEY"):
        raise HTTPException(503, "OPENWEATHER_API_KEY is not configured.")
    import requests

    try:
        result = cached_weather(city)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        if status == 404:
            raise HTTPException(404, f"Could not find weather for '{city}'.") from exc
        raise HTTPException(502, "Weather service is unavailable.") from exc
    except requests.RequestException as exc:
        raise HTTPException(502, "Weather service is unavailable.") from exc
    return {
        "temperature": result.temperature,
        "condition": result.condition,
        "location": result.city,
        "icon": "partly-sunny",
        "season": target_season(result.temperature),
    }


@app.get("/chat/messages")
def messages(
    session_id: str = "legacy",
    auth: tuple[dict, str] = Depends(current_auth),
) -> list[dict]:
    return chat_history(auth[0]["id"], session_id)


@app.get("/wardrobe/style-analysis")
def style_analysis(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return analyze_style(auth[0]["id"])


@app.post("/wardrobe/purchase-impact")
def purchase_impact(
    file: UploadFile = File(...),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    content, _content_type, suffix = reencode(content)  # pixels only: no EXIF/metadata kept
    path = settings.upload_dir / f"purchase-{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    try:
        with image_slot():
            prediction = vision_service.predict(path)
        return analyze_purchase_impact(auth[0]["id"], prediction)
    except ImageBusyError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Purchase analysis failed")
        raise HTTPException(500, "Purchase analysis failed. Try a different photo.") from exc
    finally:
        path.unlink(missing_ok=True)


@app.post("/chat/messages", status_code=201)
def send_message(
    payload: ChatRequest,
    auth: tuple[dict, str] = Depends(per_user("chat")),
) -> dict:
    try:
        return chat(auth[0]["id"], payload.content, payload.session_id)
    except LocalModelError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc


@app.put("/users/{user_id}/preferences")
def put_preferences(
    user_id: str,
    payload: PreferenceUpdate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    owner_id = require_owner(user_id, auth)
    return save_preferences(owner_id, payload.model_dump())


@app.get("/users/{user_id}/preferences")
def read_preferences(
    user_id: str,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    owner_id = require_owner(user_id, auth)
    return get_preferences(owner_id)


def _isolate_garment(path: Path) -> tuple[Path, bool]:
    """If the photo shows someone wearing the item, keep only that garment on white
    (the garment the CNN sees in the whole photo). Returns the photo to use and whether
    it was cut out. The app's preview flow lets the user choose instead (4.2b)."""
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as photo:
            photo = ImageOps.exif_transpose(photo)
            photo.load()
    except OSError:
        return path, False
    from services import garment_cutout

    labels = garment_cutout.segment(photo)
    garment = None
    if labels is not None and garment_cutout.person_present(photo, labels):
        try:
            category = vision_service.predict(path)["category"]
        except Exception:
            category = None
        found = garment_cutout.candidates(photo, labels, category) if category else []
        garment = found[0].image if found else cutout_garment(photo)
    elif labels is None:
        garment = cutout_garment(photo)  # tests replace this; without SegFormer it returns None
    if garment is None:
        return path, False
    cut_path = path.with_name(f"{path.stem}-garment.jpg")
    garment.save(cut_path, format="JPEG", quality=92)
    path.unlink(missing_ok=True)
    return cut_path, True


def _analyze_new_photo(owner_id: str, path: Path, **source: str | None) -> dict:
    try:
        with image_slot():
            path, cut = _isolate_garment(path)
            prediction = vision_service.predict(path)
        item = create_item(owner_id, path, prediction, **source)
    except ImageBusyError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        path.unlink(missing_ok=True)
        logging.getLogger(__name__).exception("Image analysis failed")
        raise HTTPException(500, "Image analysis failed. Try a different photo.") from exc
    return {**item, "garment_cutout": cut}


@app.post("/wardrobe/upload", response_model=ClothingItemResponse, status_code=201)
def upload_clothing(
    user_id: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    owner_id = require_owner(user_id, auth)
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    content, _content_type, suffix = reencode(content)  # pixels only: no EXIF/metadata kept
    path = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    return _analyze_new_photo(owner_id, path)


@app.post("/wardrobe/import-link", response_model=ClothingItemResponse, status_code=201)
def import_clothing_from_link(
    payload: ImportLinkRequest,
    auth: tuple[dict, str] = Depends(per_user("link_import", "upload")),
) -> dict:
    """Add a wardrobe item from a shopping link (product page or direct image URL)."""
    owner_id = require_owner(payload.user_id, auth)
    try:
        imported = import_from_link(payload.url, settings.max_upload_bytes)
    except ProductLinkError as exc:
        raise HTTPException(422, str(exc)) from exc
    path = settings.upload_dir / f"{uuid.uuid4().hex}{imported.suffix}"
    path.write_bytes(imported.content)
    return _analyze_new_photo(owner_id, path, source_url=imported.source_url, source_title=imported.title)


# -- 4.2b: preview -> confirm ---------------------------------------------------------------

def _photo_has_person(content: bytes) -> bool | None:
    from PIL import Image

    from services.garment_cutout import person_present

    with Image.open(BytesIO(content)) as photo:
        photo.load()
        return person_present(photo)


def _cnn_category(path: Path) -> str:
    return vision_service.predict(path)["category"]


def _preview(owner_id: str, content: bytes, **kwargs) -> dict:
    from PIL import Image

    try:
        with image_slot(), Image.open(BytesIO(content)) as photo:
            photo.load()
            return import_previews.create(owner_id, photo, classify=_cnn_category, **kwargs)
    except ImageBusyError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/wardrobe/import-link/preview", response_model=ImportPreviewResponse, status_code=201)
def preview_link_import(
    payload: ImportLinkRequest,
    auth: tuple[dict, str] = Depends(per_user("link_import", "upload")),
) -> dict:
    """Fetch a shop link's product photo (preferring one with no model in it) and show
    the garment cut-outs to choose from. Nothing is added until it is confirmed."""
    owner_id = require_owner(payload.user_id, auth)
    try:
        imported = import_from_link(payload.url, settings.max_upload_bytes, has_person=_photo_has_person)
    except ProductLinkError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _preview(owner_id, imported.content, hints=imported.hints, person_free=imported.person_free,
                    source_url=imported.source_url, source_title=imported.title, suggested_size=imported.size)


@app.post("/wardrobe/upload/preview", response_model=ImportPreviewResponse, status_code=201)
def preview_upload(
    user_id: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    """The upload equivalent of /wardrobe/import-link/preview."""
    owner_id = require_owner(user_id, auth)
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    content, _content_type, _suffix = reencode(content)
    return _preview(owner_id, content)


@app.post("/wardrobe/imports/{preview_id}/confirm", response_model=ClothingItemResponse, status_code=201)
def confirm_import(
    preview_id: str,
    payload: ImportConfirm,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    """Create the item from the chosen cut-out (or the original photo) in the user's
    chosen category. If the CNN disagrees, the user's category wins and the item is
    flagged for review."""
    owner_id = auth[0]["id"]
    try:
        path, source = import_previews.take(owner_id, preview_id, payload.choice, payload.category, payload.index)
    except import_previews.PreviewError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    try:
        with image_slot():
            prediction = vision_service.predict(path)
        item = create_item(owner_id, path, prediction, category=payload.category,
                           size=payload.size.model_dump() if payload.size else None, **source)
    except ImageBusyError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        path.unlink(missing_ok=True)
        logging.getLogger(__name__).exception("Image analysis failed")
        raise HTTPException(500, "Image analysis failed. Try a different photo.") from exc
    return {**item, "garment_cutout": payload.choice == "cutout"}


@app.delete("/wardrobe/imports/{preview_id}", status_code=204, response_class=Response)
def discard_import(preview_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    import_previews.discard(auth[0]["id"], preview_id)
    return Response(status_code=204)


@app.post("/wardrobe/{user_id}/{item_id}/remove-model", response_model=ClothingItemResponse)
def remove_model_from_photo(
    user_id: str,
    item_id: str,
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    """Re-cut an existing item's photo to just the garment and re-run the CNN on it."""
    owner_id = require_owner(user_id, auth)
    record = rows(
        "SELECT image_path FROM clothing_items WHERE user_id=? AND item_id=?", (owner_id, item_id),
    )
    if not record:
        raise HTTPException(404, "Clothing item not found.")
    original = media_path(record[0]["image_path"])
    from PIL import Image, ImageOps

    category = rows("SELECT category FROM clothing_items WHERE item_id=?", (item_id,))[0]["category"]
    try:
        with image_slot(), Image.open(original) as photo:
            # The item's category is already known, so only that garment is kept.
            garment = cutout_garment(ImageOps.exif_transpose(photo), category)
    except ImageBusyError as exc:
        raise HTTPException(503, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(422, "This item's photo could not be read.") from exc
    if garment is None:
        raise HTTPException(422, "No person was found wearing this item, so there is nothing to remove.")
    cut_path = settings.upload_dir / f"{uuid.uuid4().hex}-garment.jpg"
    garment.save(cut_path, format="JPEG", quality=92)
    try:
        with image_slot():
            prediction = vision_service.predict(cut_path)
        item, old_path = replace_image(owner_id, item_id, cut_path, prediction)
    except ImageBusyError as exc:
        cut_path.unlink(missing_ok=True)
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        cut_path.unlink(missing_ok=True)
        logging.getLogger(__name__).exception("Image analysis failed")
        raise HTTPException(500, "Image analysis failed. Try a different photo.") from exc
    old_path.unlink(missing_ok=True)
    return {**item, "garment_cutout": True}


@app.get("/wardrobe/{user_id}", response_model=list[ClothingItemResponse])
def wardrobe(
    user_id: str,
    available_only: bool = False,
    auth: tuple[dict, str] = Depends(current_auth),
) -> list[dict]:
    owner_id = require_owner(user_id, auth)
    return list_items(owner_id, available_only)


@app.get("/wardrobe/{user_id}/{item_id}", response_model=ClothingItemResponse)
def wardrobe_item(
    user_id: str,
    item_id: str,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    owner_id = require_owner(user_id, auth)
    try:
        return get_item(owner_id, item_id)
    except KeyError as exc:
        raise HTTPException(404, "Clothing item not found.") from exc


@app.get("/wardrobe/{user_id}/{item_id}/fit")
def wardrobe_item_fit(user_id: str, item_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    """Size advice for one of the user's own items (4.11): zone ratings and a verdict."""
    owner_id = require_owner(user_id, auth)
    try:
        item = get_item(owner_id, item_id)
    except KeyError as exc:
        raise HTTPException(404, "Clothing item not found.") from exc
    return fit_advice.for_user(owner_id, item["category"], item.get("size"), cut=item.get("fit"))


@app.patch("/wardrobe/{user_id}/{item_id}", response_model=ClothingItemResponse)
def patch_wardrobe_item(
    user_id: str,
    item_id: str,
    payload: ClothingItemUpdate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    owner_id = require_owner(user_id, auth)
    try:
        return update_item(owner_id, item_id, payload.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(404, "Clothing item not found.") from exc


@app.delete("/wardrobe/{user_id}/{item_id}", status_code=204, response_class=Response)
def remove_wardrobe_item(
    user_id: str,
    item_id: str,
    auth: tuple[dict, str] = Depends(current_auth),
) -> Response:
    owner_id = require_owner(user_id, auth)
    try:
        path = delete_item(owner_id, item_id)
        path.unlink(missing_ok=True)
        return Response(status_code=204)
    except KeyError as exc:
        raise HTTPException(404, "Clothing item not found.") from exc


def _weather(payload: RecommendationRequest) -> tuple[float, str, str | None]:
    if payload.temperature_c is not None:
        return payload.temperature_c, payload.condition or "Unknown", payload.city
    if payload.city and os.getenv("OPENWEATHER_API_KEY"):
        try:
            weather = cached_weather(payload.city)
        except Exception:  # unknown city or API outage: rank without live weather
            return 25.0, payload.condition or "Unknown", payload.city
        return weather.temperature, weather.condition, weather.city
    return 25.0, payload.condition or "Unknown", payload.city


@app.get("/trends/current")
def live_fashion_trends(
    region: str = "India",
    refresh: bool = False,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    return current_fashion_trends(region, force=refresh)


@app.get("/models/compatibility/status")
def compatibility_status() -> dict:
    """Expose model readiness without leaking weights or local data."""
    return compatibility_model_status()


@app.get("/models/outfit-compatibility/status")
def outfit_compatibility_status() -> dict:
    """Readiness and held-out metrics of the Polyvore item-level compatibility model."""
    return outfit_compat_service.status()


@app.get("/models/personalisation/status")
def personalisation_status(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    """What the signed-in user's contextual bandit has learned from their feedback."""
    from services import bandit_ranker

    return {"enabled": settings.bandit_enabled, **bandit_ranker.describe(auth[0]["id"])}


@app.get("/models/stylist/status")
def stylist_status() -> dict:
    """Whether the fine-tuned stylist may reorder top outfits, and which model serves chat."""
    return {"source": stylist_selector.model_source(), "chat": stylist_selector.chat_model_source()}


@app.get("/models/fashion-language/status")
def fashion_language_status() -> dict:
    """Report readiness of the local scratch-trained AURA fashion model."""
    return fashion_lm_model_info()


@app.post("/recommend", response_model=RecommendationResponse)
def outfit_recommendations(
    payload: RecommendationRequest,
    auth: tuple[dict, str] = Depends(per_user("recommend")),
) -> dict:
    owner_id = require_owner(payload.user_id, auth)
    temperature, condition, city = _weather(payload)
    recommendations, agent_trace = recommend(
        owner_id,
        payload.occasion,
        temperature,
        condition,
        payload.limit,
        payload.exclude_recommendation_ids,
        use_stylist=True,
    )
    if not recommendations:
        raise HTTPException(
            422,
            "No new outfit combinations remain for these alternatives. Change the occasion or add available wardrobe items."
            if payload.exclude_recommendation_ids
            else "Not enough wardrobe items. Upload a dress, or at least a top and bottom.",
        )
    available_wardrobe = list_items(owner_id, available_only=True)
    explanation_result = explain_recommendations(
        recommendations, occasion=payload.occasion, temperature=temperature,
        condition=condition, wardrobe=available_wardrobe,
        preferences=get_preferences(owner_id),
        # At most one LLM call per request: skip the comparison LLM when the stylist ran.
        allow_llm=not any(
            step.get("agent") == "stylist_llm_agent" and step.get("status") == "completed"
            for step in agent_trace.get("agents", [])
        ),
    )
    recommendations = explanation_result["recommendations"]
    record_explanations(owner_id, recommendations)
    agent_trace.setdefault("agents", []).append({
        "agent": "explanation_agent",
        "status": "completed",
        "source": explanation_result["comparison_source"],
        "fashion_lm_available": explanation_result.get("fashion_lm_available", False),
        "outfit_explanation_sources": sorted({
            recommendation.get("explanation_source", "rules")
            for recommendation in recommendations
        }),
        "may_change_rank_or_items": False,
    })
    return {
        "user_id": owner_id,
        "occasion": payload.occasion,
        "weather": {
            "city": city,
            "temperature_c": temperature,
            "condition": condition,
            "season": target_season(temperature),
        },
        "recommendations": recommendations,
        "agent_trace": agent_trace,
        "comparison_explanation": explanation_result["comparison_explanation"],
        "comparison_source": explanation_result["comparison_source"],
        "evidence_confidence": explanation_result["evidence_confidence"],
        "confidence_note": explanation_result["confidence_note"],
    }


@app.post("/feedback", status_code=201)
def feedback(
    payload: FeedbackRequest,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict[str, str]:
    owner_id = require_owner(payload.user_id, auth)
    if payload.action == "rate" and payload.rating is None:
        raise HTTPException(422, "A rating from 1 to 5 is required for action=rate.")
    owned = {
        item["item_id"]
        for item in rows(
            "SELECT item_id FROM clothing_items WHERE user_id=? AND item_id IN (%s)"
            % ",".join("?" for _ in payload.item_ids),
            (owner_id, *payload.item_ids),
        )
    }
    if owned != set(payload.item_ids):
        raise HTTPException(422, "Feedback can reference only your own wardrobe items.")
    try:
        save_feedback({**payload.model_dump(), "user_id": owner_id})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"status": "saved"}


# -- Donations: never-worn clothes ----------------------------------------------------------

@app.get("/donations/candidates", response_model=list[ClothingItemResponse])
def donation_candidates(
    min_days: int = 0,
    auth: tuple[dict, str] = Depends(current_auth),
) -> list[dict]:
    """Items never marked as worn, owned for at least ``min_days`` days (oldest first)."""
    return unworn_items(auth[0]["id"], max(0, min_days))


@app.get("/donations/candidates.csv")
def donation_candidates_csv(
    min_days: int = 0,
    auth: tuple[dict, str] = Depends(current_auth),
) -> Response:
    return Response(
        content=unworn_items_csv(auth[0]["id"], max(0, min_days)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aura-unworn-clothes.csv"'},
    )


@app.post("/donations")
def donate_items(
    payload: DonationRequest,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    donated = mark_donated(auth[0]["id"], payload.item_ids)
    if not donated:
        raise HTTPException(404, "None of these items are in your active wardrobe.")
    return {"donated": donated}


@app.get("/activity/wear-logs")
def wear_logs(auth: tuple[dict, str] = Depends(current_auth)) -> list[dict]:
    from database import rows

    records = rows(
        """SELECT feedback_id,item_ids,created_at FROM feedback
           WHERE user_id=? AND action='wear' ORDER BY created_at DESC""",
        (auth[0]["id"],),
    )
    return [
        {
            "id": str(item["feedback_id"]),
            "outfitName": f"Outfit with {len(__import__('json').loads(item['item_ids']))} items",
            "date": item["created_at"],
        }
        for item in records
    ]


# -- My Virtual Look: avatar + virtual try-on ----------------------------------------------

@app.get("/tryon/status")
def tryon_status() -> dict:
    """Public summary only; the full status is in the authenticated GET /avatar."""
    full = tryon_service.status()
    return {key: full[key] for key in ("enabled", "tryon_ready", "worker_running", "queue_length")}


@app.get("/avatar")
def read_avatar(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return {
        "avatars": tryon_service.get_avatars(auth[0]["id"]),
        "status": tryon_service.status(),
        "consent_given": tryon_service.has_consent(auth[0]["id"]),
    }


@app.post("/avatar", status_code=201)
def upload_avatar(
    file: UploadFile = File(...),
    view: str = Form("front"),
    consent: bool = Form(False),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    """Create (or replace) the user's avatar from a full-body photo and analyse its proportions.

    The first body photo needs ``consent=true`` (the app's consent screen); it is recorded
    and not asked again until the user deletes their body data. Without it: 428."""
    try:
        tryon_service.require_consent(auth[0]["id"], consent)
    except tryon_service.ConsentRequired as exc:
        raise HTTPException(428, str(exc)) from exc
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    content, _content_type, _suffix = reencode(content)  # size guard + rotation applied, metadata dropped
    try:
        photo = Image.open(BytesIO(content))
        photo.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, "That file is not a readable image.") from exc
    try:
        with image_slot():
            return tryon_service.create_avatar(auth[0]["id"], photo, view)
    except ImageBusyError as exc:
        raise HTTPException(503, str(exc)) from exc
    except BodyPhotoError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


# -- 4.11 body measurements -----------------------------------------------------------------

def _measurements_view(user_id: str) -> dict:
    profile = get_user(user_id)
    return body_measurements.public(user_id, profile.get("heightCm"))


@app.get("/body/measurements")
def read_measurements(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    """The user's own measurements: typed values, estimates (as ranges until validated) and height."""
    return _measurements_view(auth[0]["id"])


@app.put("/body/measurements")
def update_measurements(payload: MeasurementUpdate, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    """Type or correct measurements (cm). Typed values always win; null clears one."""
    user_id = auth[0]["id"]
    values = payload.model_dump(exclude_unset=True)
    height = values.pop("height_cm", None)
    try:
        body_measurements.set_manual(user_id, values)
    except body_measurements.MeasurementError as exc:
        raise HTTPException(422, str(exc)) from exc
    if height is not None:
        update_user(user_id, {"heightCm": round(height)})
    return _measurements_view(user_id)


@app.post("/body/measurements/estimate")
def estimate_measurements(
    file: UploadFile = File(...),
    height_cm: float | None = Form(None),
    auth: tuple[dict, str] = Depends(per_user("upload")),
) -> dict:
    """Estimate measurements from the front avatar and a side photo, scaled by height.
    The side photo is measured in memory and never stored (VQ13)."""
    from PIL import Image, UnidentifiedImageError

    user_id = auth[0]["id"]
    if not tryon_service.has_consent(user_id):
        raise HTTPException(428, tryon_service.CONSENT_MESSAGE)
    front = tryon_service.get_avatars(user_id).get("front")
    if front is None:
        raise HTTPException(409, "Add your front full-body photo first; it is measured together with the side photo.")
    if height_cm is None:
        height_cm = get_user(user_id).get("heightCm")
    if not height_cm:
        raise HTTPException(422, "Enter your height first: it is the scale for every measurement.")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    content, _content_type, _suffix = reencode(content)
    try:
        side = Image.open(BytesIO(content))
        side.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, "That file is not a readable image.") from exc
    try:
        with image_slot():
            avatar = tryon_service.front_avatar_image(user_id)
            result = body_measurements.estimate_from_photos(user_id, avatar, side, float(height_cm))
    except ImageBusyError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (BodyPhotoError, body_measurements.MeasurementError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        del content
    update_user(user_id, {"heightCm": round(float(height_cm))})
    return {**result, **_measurements_view(user_id)}


@app.delete("/avatar", status_code=204, response_class=Response)
def remove_avatar(auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    """Delete the user's body data: photos, avatars, every try-on render and the consent record."""
    tryon_service.delete_avatars(auth[0]["id"])
    return Response(status_code=204)


@app.post("/tryon", status_code=202)
def start_tryon(payload: TryOnRequest, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    try:
        return tryon_service.request_render(
            auth[0]["id"], payload.item_ids, payload.view, payload.recommendation_id,
        )
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except tryon_service.TryOnLimitError as exc:
        raise HTTPException(429, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.delete("/tryon/{render_id}", status_code=204, response_class=Response)
def delete_tryon(render_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    """Delete one look (or cancel a queued render)."""
    try:
        tryon_service.delete_render(auth[0]["id"], render_id)
    except KeyError as exc:
        raise HTTPException(404, "Look not found.") from exc
    return Response(status_code=204)


@app.get("/tryon/saved")
def saved_tryons(auth: tuple[dict, str] = Depends(current_auth)) -> list[dict]:
    return tryon_service.saved_looks(auth[0]["id"])


@app.get("/tryon/{render_id}")
def read_tryon(render_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    try:
        return tryon_service.get_render(auth[0]["id"], render_id)
    except KeyError as exc:
        raise HTTPException(404, "Look not found.") from exc


@app.post("/tryon/{render_id}/save")
def save_tryon(render_id: str, saved: bool = True, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    try:
        return tryon_service.set_saved(auth[0]["id"], render_id, saved)
    except KeyError as exc:
        raise HTTPException(404, "Only a finished look can be saved.") from exc


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AURA Personalized Wardrobe API",
        "version": "2.0.0",
        "docs": "/docs",
    }
