from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field


# -- shared field types (4.8: every client-supplied string and list is bounded) -------
Short = Annotated[str, Field(max_length=80)]
Id = Annotated[str, Field(min_length=1, max_length=100)]
Tags = Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=30)]
IdList = Annotated[list[Id], Field(max_length=50)]
_EMAIL = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
# Images AURA itself stored (listing / profile photos). Outside URLs are not accepted:
# they would let one user make every viewer's app fetch a URL of their choosing.
_PUBLIC_PHOTO = re.compile(r"^/marketplace/images/[0-9a-f]{32}\.(?:jpg|png|webp)$")


def _email(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or not _EMAIL.match(value):
        raise ValueError("Enter a valid email address.")
    return value


def _public_photo(value: str) -> str:
    if not _PUBLIC_PHOTO.match(value):
        raise ValueError("Use a photo uploaded to AURA.")
    return value


Email = Annotated[str, AfterValidator(_email)]
PublicPhoto = Annotated[str, AfterValidator(_public_photo)]

Category = Literal["Top", "Bottom", "Dress", "Footwear", "Outerwear", "Accessory"]


Cm = Annotated[float, Field(gt=0, le=300)]


class GarmentMeasurements(BaseModel):
    """Flat garment measurements in cm (4.11): laid flat, edge to edge."""
    chest_flat_cm: Cm | None = None
    waist_flat_cm: Cm | None = None
    hip_flat_cm: Cm | None = None
    length_cm: Cm | None = None   # tops/dresses: high point of the shoulder to the hem
    inseam_cm: Cm | None = None   # bottoms


class GarmentSize(BaseModel):
    """A garment's size (4.11). Send an empty object to clear it."""
    label: str | None = Field(default=None, max_length=20)
    chart: Literal["women", "men", "unisex"] | None = None
    measurements: GarmentMeasurements | None = None


class MeasurementUpdate(BaseModel):
    """Body measurements typed by the user, in cm (4.11). null clears a typed value."""
    chest: float | None = None
    waist: float | None = None
    hip: float | None = None
    shoulder: float | None = None
    inseam: float | None = None
    arm: float | None = None
    torso: float | None = None
    height_cm: float | None = Field(default=None, ge=120, le=230)


class Prediction(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    top_3: list[dict[str, float | str]] = Field(default_factory=list)


class ClothingItemResponse(BaseModel):
    item_id: str
    user_id: str
    category: Category
    subcategory: str
    garment_group: str
    color_name: str
    image_url: str
    confidence: dict[str, Prediction]
    color_sample: dict[str, Any] | None = None
    needs_review: bool
    pattern: str | None = None
    fabric: str | None = None
    fit: str | None = None
    texture: str | None = None
    seasons: list[str] = Field(default_factory=list)
    season_label: Literal["Summer", "Winter", "All-season"] = "All-season"
    season_source: Literal["user", "auto"] = "auto"
    days_in_wardrobe: int | None = None
    source_url: str | None = None
    source_title: str | None = None
    garment_cutout: bool = False  # True when a model/background was removed from this photo
    style_tags: list[str] = Field(default_factory=list)
    occasion_tags: list[str] = Field(default_factory=list)
    available: bool = True
    size: GarmentSize | None = None
    created_at: str


class ClothingItemUpdate(BaseModel):
    category: Category | None = None
    subcategory: Short | None = None
    color_name: Short | None = None
    pattern: Short | None = None
    fabric: Short | None = None
    fit: Short | None = None
    texture: Short | None = None
    seasons: Tags | None = None
    style_tags: Tags | None = None
    occasion_tags: Tags | None = None
    available: bool | None = None
    size: GarmentSize | None = None


class PreferenceUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    preferred_colors: Tags = Field(default_factory=list)
    avoided_colors: Tags = Field(default_factory=list)
    preferred_styles: Tags = Field(default_factory=list)
    disliked_styles: Tags = Field(default_factory=list)
    fit_preference: Short | None = None


class ImportLinkRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=4, max_length=2048)


class ImportCandidate(BaseModel):
    index: int
    label: str
    image_url: str


class ImportPreviewResponse(BaseModel):
    """4.2b: what the app shows before an imported or uploaded item is created."""
    preview_id: str
    suggested_category: Category | None
    person_found: bool
    original_url: str
    candidates: dict[Category, list[ImportCandidate]] = Field(default_factory=dict)
    source_title: str | None = None
    suggested_size: str | None = None
    expires_at: float


class ImportConfirm(BaseModel):
    choice: Literal["cutout", "original"]
    category: Category
    index: int = Field(default=0, ge=0, le=9)
    size: GarmentSize | None = None


class DonationRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=500)


class RecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    occasion: str = Field(min_length=1, max_length=80)
    mood: str = Field(default="Confident", max_length=80)
    city: str | None = Field(default=None, max_length=120)
    temperature_c: float | None = Field(default=None, ge=-60, le=65)
    condition: str | None = Field(default=None, max_length=80)
    limit: int = Field(default=3, ge=1, le=10)
    exclude_recommendation_ids: list[str] = Field(default_factory=list, max_length=50)


class OutfitRecommendation(BaseModel):
    recommendation_id: str
    item_ids: list[str]
    items: list[ClothingItemResponse]
    compatibility_score: int = Field(ge=0, le=100)
    component_scores: dict[str, float]
    explanation: str
    explanation_source: Literal["stylist_llm", "aura_fashion_lm", "local_llm", "rules"] = "rules"
    compatibility_source: Literal["item_level", "category_level", "none"] = "none"
    analysis: dict = Field(default_factory=dict)
    evidence_confidence: Literal["limited", "moderate"] = "limited"
    confidence_note: str = "Style ranking is an uncalibrated heuristic, not a probability."


class RecommendationResponse(BaseModel):
    user_id: str
    occasion: str
    weather: dict[str, float | str | None]
    recommendations: list[OutfitRecommendation]
    agent_trace: dict = Field(default_factory=dict)
    comparison_explanation: str = ""
    comparison_source: Literal["local_llm", "rules"] = "rules"
    evidence_confidence: Literal["limited", "moderate"] = "limited"
    confidence_note: str = ""
    score_disclosure: str = "Rule-based ranking signals are uncalibrated; they are not probabilities or human fashion ratings."


class FeedbackRequest(BaseModel):
    user_id: Id
    recommendation_id: str | None = Field(default=None, max_length=100)
    item_ids: list[Id] = Field(min_length=1, max_length=20)
    action: Literal["skip", "save", "wear", "like", "dislike", "rate"]
    rating: int | None = Field(default=None, ge=1, le=5)


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: Email
    password: str = Field(min_length=8, max_length=128)
    # "web" sessions last 7 days, "app" sessions 30 (4.7).
    client: Literal["app", "web"] = "app"


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    client: Literal["app", "web"] = "app"


class ReportCreate(BaseModel):
    target_type: Literal["listing", "conversation", "post", "user"]
    target_id: Id
    reason: Literal["spam", "scam", "offensive", "harassment", "prohibited_item", "other"]
    details: str = Field(default="", max_length=1000)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class ProfileUpdate(BaseModel):
    fullName: str | None = Field(default=None, min_length=1, max_length=100)
    # Set by POST /users/me/photo; null removes the picture.
    avatarUrl: PublicPhoto | None = None
    location: str | None = Field(default=None, max_length=120)
    stylePreferences: Tags | None = None
    bodyShape: Short | None = None
    skinTone: Short | None = None
    heightCm: int | None = Field(default=None, ge=50, le=260)
    topSize: str | None = Field(default=None, max_length=20)
    bottomSize: str | None = Field(default=None, max_length=20)
    profileComplete: bool | None = None


class ShippingAddress(BaseModel):
    name: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=20)
    line1: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=80)
    pincode: str = Field(default="", max_length=12)


class OrderRequest(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=20)
    shipping_address: ShippingAddress | None = None
    # Payment is arranged between buyer and seller; it is not processed in-app.
    payment_method: Literal["cod", "upi"] = "cod"


class OrderStatusUpdate(BaseModel):
    status: Literal["shipped", "completed", "cancelled"]


class ListingUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    price: float | None = Field(default=None, gt=0, le=1_000_000)
    description: str | None = Field(default=None, max_length=2000)
    size: str | None = Field(default=None, max_length=20)
    brand: str | None = Field(default=None, max_length=60)
    condition: Literal["new", "like_new", "good", "fair"] | None = None
    status: Literal["active", "paused"] | None = None


class ConversationStart(BaseModel):
    product_id: str = Field(min_length=1, max_length=40)
    buyer_id: str | None = Field(default=None, max_length=100)  # seller messaging a buyer


class MarketMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default="legacy", min_length=1, max_length=100)


class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    price: float = Field(gt=0, le=1_000_000)
    image_urls: list[PublicPhoto] = Field(min_length=1, max_length=5)
    category: Short
    condition: Literal["new", "like_new", "good", "fair"]
    description: str = Field(default="", max_length=2000)
    size: str = Field(default="", max_length=20)
    brand: str = Field(default="", max_length=60)


class PostCreate(BaseModel):
    outfit_image_url: PublicPhoto
    caption: str = Field(max_length=1000)
    product_ids: IdList = Field(default_factory=list)


class TryOnRequest(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=8)
    view: Literal["front", "side"] = "front"
    recommendation_id: str | None = Field(default=None, max_length=100)
