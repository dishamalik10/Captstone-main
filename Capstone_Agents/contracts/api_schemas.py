from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Category = Literal["Top", "Bottom", "Dress", "Footwear", "Outerwear", "Accessory"]


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
    style_tags: list[str] = Field(default_factory=list)
    occasion_tags: list[str] = Field(default_factory=list)
    available: bool = True
    created_at: str


class ClothingItemUpdate(BaseModel):
    category: Category | None = None
    subcategory: str | None = None
    color_name: str | None = None
    pattern: str | None = None
    fabric: str | None = None
    fit: str | None = None
    texture: str | None = None
    seasons: list[str] | None = None
    style_tags: list[str] | None = None
    occasion_tags: list[str] | None = None
    available: bool | None = None


class PreferenceUpdate(BaseModel):
    display_name: str | None = None
    preferred_colors: list[str] = Field(default_factory=list)
    avoided_colors: list[str] = Field(default_factory=list)
    preferred_styles: list[str] = Field(default_factory=list)
    disliked_styles: list[str] = Field(default_factory=list)
    fit_preference: str | None = None


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
    user_id: str
    recommendation_id: str | None = None
    item_ids: list[str] = Field(min_length=1)
    action: Literal["skip", "save", "wear", "like", "dislike", "rate"]
    rating: int | None = Field(default=None, ge=1, le=5)


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    fullName: str | None = None
    avatarUrl: str | None = None
    location: str | None = None
    stylePreferences: list[str] | None = None
    bodyShape: str | None = None
    skinTone: str | None = None
    heightCm: int | None = None
    topSize: str | None = None
    bottomSize: str | None = None
    profileComplete: bool | None = None


class OrderRequest(BaseModel):
    product_ids: list[str] = Field(min_length=1)


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default="legacy", min_length=1, max_length=100)


class ProductCreate(BaseModel):
    title: str
    price: float = Field(gt=0)
    image_urls: list[str] = Field(min_length=1)
    category: str
    condition: Literal["new", "like_new", "good", "fair"]
    description: str


class PostCreate(BaseModel):
    outfit_image_url: str
    caption: str = Field(max_length=1000)
    product_ids: list[str] = Field(default_factory=list)
