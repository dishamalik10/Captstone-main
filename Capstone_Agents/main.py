from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from pathlib import PurePosixPath

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from contracts.api_schemas import (
    ClothingItemResponse,
    ClothingItemUpdate,
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
)
from database import ensure_user, init_database, rows
from services.preference_service import get_preferences, save_preferences
from services.recommendation_service import recommend, save_feedback
from services.recommendation_explainer import explain_recommendations
from services.vision_service import vision_service
from services.style_analysis_service import analyze_style
from services.purchase_impact_service import analyze_purchase_impact
from services.trend_service import current_fashion_trends
from services.local_llm import LocalModelError, get_model_info, local_llm
from services.compatibility_service import compatibility_model_status
from services import outfit_compat_service, stylist_selector
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
    update_item,
)
from settings import settings
from services.app_service import (
    chat,
    chat_history,
    create_order,
    create_post,
    create_product,
    get_user,
    list_products,
    login,
    logout,
    session_user,
    signup,
    seller_dashboard,
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
    )
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


@app.get("/marketplace/products")
def marketplace_products() -> list[dict]:
    return list_products()


@app.post("/marketplace/products", status_code=201)
def marketplace_create_product(
    payload: ProductCreate,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    return create_product(auth[0]["id"], payload.model_dump())


@app.get("/marketplace/products/{product_id}")
def marketplace_product(product_id: str) -> dict:
    products = [product for product in list_products() if product["id"] == product_id]
    if not products:
        raise HTTPException(404, "Product not found.")
    return products[0]


@app.post("/marketplace/orders", status_code=201)
def marketplace_order(
    payload: OrderRequest,
    auth: tuple[dict, str] = Depends(current_auth),
) -> dict:
    try:
        return {"order_ids": create_order(auth[0]["id"], payload.product_ids)}
    except KeyError as exc:
        raise HTTPException(409, "A product is unavailable.") from exc


@app.get("/marketplace/seller")
def marketplace_seller(auth: tuple[dict, str] = Depends(current_auth)) -> dict:
    return seller_dashboard(auth[0]["id"])


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
    from tools.weather_tool import get_weather

    result = get_weather(city)
    return {
        "temperature": result.temperature,
        "condition": result.condition,
        "location": result.city,
        "icon": "partly-sunny",
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
    try:
        prediction = vision_service.predict(path)
        return create_item(owner_id, path, prediction)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(500, f"Image analysis failed: {exc}") from exc


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

        weather = get_weather(payload.city)
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


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AURA Personalized Wardrobe API",
        "version": "2.0.0",
        "docs": "/docs",
    }
