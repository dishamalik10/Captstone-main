from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from pathlib import PurePosixPath

import asyncio
import json

import anyio
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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
    LoginRequest,
    ProfileUpdate,
    OrderRequest,
    ChatRequest,
    ProductCreate,
    PostCreate,
    TryOnRequest,
)
from database import ensure_user, init_database, rows
from services.preference_service import get_preferences, save_preferences
from services.recommendation_service import recommend, save_feedback
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
from services import outfit_compat_service, stylist_selector, tryon_service
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
from services.garment_cutout import cutout_garment
from services import marketplace_service as market
from services.marketplace_service import MarketplaceError
from services.realtime import chat_partners, conversation_members, hub
from settings import settings
from services.app_service import (
    chat,
    chat_history,
    create_post,
    get_user,
    login,
    logout,
    session_user,
    signup,
    social_feed,
    toggle_follow,
    toggle_like,
    update_user,
)


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    tryon_service.init_tables()
    # Load only the model that serves chat (the fine-tuned stylist when installed),
    # so an 8 GB host does not hold two 1 GB GGUFs at startup.
    chat_model = stylist_selector.chat_llm()
    if chat_model is not local_llm or settings.llm_model_path.is_file():
        try:
            chat_model.load_model()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Local LLM startup load failed")
    try:
        yield
    finally:
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=settings.allowed_origins != ("*",),
    allow_methods=["*"],
    allow_headers=["*"],
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
        (user_id, str(path)),
    ) or tryon_service.owns_media(user_id, path)
    if not owned:
        raise HTTPException(404, "Image not found or the link has expired.")
    return FileResponse(
        path,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=60", "Referrer-Policy": "no-referrer"},
    )


@app.get("/health")
def health() -> dict[str, object]:
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
    }


@app.post("/auth/signup", status_code=201)
def auth_signup(payload: SignupRequest) -> dict:
    try:
        user, token = signup(payload.full_name, payload.email, payload.password)
        return {"user": user, "token": token}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/auth/login")
def auth_login(payload: LoginRequest) -> dict:
    try:
        user, token = login(payload.email, payload.password)
        return {"user": user, "token": token}
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.get("/auth/me")
def auth_me(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return auth[0]


@app.post("/auth/logout", status_code=204, response_class=Response)
def auth_logout(auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    logout(auth[1])
    return Response(status_code=204)


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


# -- Marketplace: listings, orders and buyer <-> seller chat --------------------------------

def _market(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except MarketplaceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@app.get("/marketplace/products")
def marketplace_products(q: str = "", category: str = "") -> list[dict]:
    return market.list_products(q, category)


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
    auth: tuple[dict, str] = Depends(current_auth),
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
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[upload.content_type]
        image_urls.append(market.save_listing_photo(content, suffix))
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
    came_online = hub.connect(user_id, websocket)
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
                members = await anyio.to_thread.run_sync(conversation_members, conversation_id)
                if members and user_id in members:
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
    return {"liked": toggle_like(auth[0]["id"], post_id)}


@app.post("/social/users/{user_id}/follow")
def social_follow(user_id: str, auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    try:
        return {"following": toggle_follow(auth[0]["id"], user_id)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/weather")
def current_weather(city: str) -> dict:
    if not os.getenv("OPENWEATHER_API_KEY"):
        raise HTTPException(503, "OPENWEATHER_API_KEY is not configured.")
    import requests
    from tools.weather_tool import get_weather

    try:
        result = get_weather(city)
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
async def purchase_impact(
    file: UploadFile = File(...),
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    suffix = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[file.content_type]
    path = settings.upload_dir / f"purchase-{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    try:
        prediction = vision_service.predict(path)
        return analyze_purchase_impact(auth[0]["id"], prediction)
    except Exception as exc:
        raise HTTPException(500, f"Purchase analysis failed: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)


@app.post("/chat/messages", status_code=201)
def send_message(
    payload: ChatRequest,
    auth: tuple[dict, str] = Depends(current_auth),
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
    """If the photo shows someone wearing the item, keep only the clothes on white.
    Returns the photo to use and whether it was cut out."""
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as photo:
            garment = cutout_garment(ImageOps.exif_transpose(photo))
    except OSError:
        return path, False
    if garment is None:
        return path, False
    cut_path = path.with_name(f"{path.stem}-garment.jpg")
    garment.save(cut_path, format="JPEG", quality=92)
    path.unlink(missing_ok=True)
    return cut_path, True


def _analyze_new_photo(owner_id: str, path: Path, **source: str | None) -> dict:
    path, cut = _isolate_garment(path)
    try:
        prediction = vision_service.predict(path)
        item = create_item(owner_id, path, prediction, **source)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(500, f"Image analysis failed: {exc}") from exc
    return {**item, "garment_cutout": cut}


@app.post("/wardrobe/upload", response_model=ClothingItemResponse, status_code=201)
async def upload_clothing(
    user_id: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    owner_id = require_owner(user_id, auth)
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    suffix = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[file.content_type]
    path = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    return _analyze_new_photo(owner_id, path)


@app.post("/wardrobe/import-link", response_model=ClothingItemResponse, status_code=201)
def import_clothing_from_link(
    payload: ImportLinkRequest,
    auth: tuple[dict, str] = Depends(current_auth),
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


@app.post("/wardrobe/{user_id}/{item_id}/remove-model", response_model=ClothingItemResponse)
def remove_model_from_photo(
    user_id: str,
    item_id: str,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    """Re-cut an existing item's photo to just the garment and re-run the CNN on it."""
    owner_id = require_owner(user_id, auth)
    record = rows(
        "SELECT image_path FROM clothing_items WHERE user_id=? AND item_id=?", (owner_id, item_id),
    )
    if not record:
        raise HTTPException(404, "Clothing item not found.")
    original = Path(record[0]["image_path"])
    from PIL import Image, ImageOps

    try:
        with Image.open(original) as photo:
            garment = cutout_garment(ImageOps.exif_transpose(photo))
    except OSError as exc:
        raise HTTPException(422, "This item's photo could not be read.") from exc
    if garment is None:
        raise HTTPException(422, "No person was found wearing this item, so there is nothing to remove.")
    cut_path = settings.upload_dir / f"{uuid.uuid4().hex}-garment.jpg"
    garment.save(cut_path, format="JPEG", quality=92)
    try:
        prediction = vision_service.predict(cut_path)
        item, old_path = replace_image(owner_id, item_id, cut_path, prediction)
    except Exception as exc:
        cut_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Image analysis failed: {exc}") from exc
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
        from tools.weather_tool import get_weather

        try:
            weather = get_weather(payload.city)
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
    auth: tuple[dict, str] = Depends(current_auth),
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
    return tryon_service.status()


@app.get("/avatar")
def read_avatar(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return {"avatars": tryon_service.get_avatars(auth[0]["id"]), "status": tryon_service.status()}


@app.post("/avatar", status_code=201)
async def upload_avatar(
    file: UploadFile = File(...),
    view: str = Form("front"),
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    """Create (or replace) the user's avatar from a full-body photo and analyse its proportions."""
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, "Only JPEG, PNG, and WebP images are accepted.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is larger than the configured upload limit.")
    try:
        photo = Image.open(BytesIO(content))
        photo.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, "That file is not a readable image.") from exc
    try:
        return tryon_service.create_avatar(auth[0]["id"], photo, view)
    except BodyPhotoError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.delete("/avatar", status_code=204, response_class=Response)
def remove_avatar(auth: tuple[dict, str] = Depends(current_auth)) -> Response:
    """Delete the user's body photos, avatar and every try-on render (privacy)."""
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
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


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
