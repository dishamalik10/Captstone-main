"""ENGINEERING_PLAN 4.8: bounded inputs, AURA-only image URLs, re-encoded uploads,
minimal public status, authenticated cached weather, vague sign-up conflicts."""
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from database import row
from main import app
from services import marketplace_service as market
from services import weather_cache
from services.image_sanitize import ImageRejected, reencode
from services.vision_service import vision_service
from settings import settings
from tools import weather_tool
from tools.weather_tool import WeatherContext

pytestmark = pytest.mark.usefixtures("remove_new_listings")

PASSWORD = "secure-pass-123"


def account(client):
    body = client.post("/auth/signup", json={"full_name": "Hygiene", "email": f"hy-{uuid.uuid4().hex[:8]}@example.com", "password": PASSWORD}).json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['token']}"}


def jpeg_with_gps(size=(80, 60)) -> bytes:
    image = Image.new("RGB", size, (200, 40, 40))
    exif = Image.Exif()
    exif[0x0110] = "Secret Phone"            # camera model
    exif[0x0112] = 6                         # rotate 90° on display
    exif.get_ifd(0x8825)[2] = (18.0, 31.0, 12.0)  # GPS latitude
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_reencode_drops_metadata_and_applies_rotation():
    clean, content_type, suffix = reencode(jpeg_with_gps())
    assert (content_type, suffix) == ("image/jpeg", ".jpg")
    with Image.open(BytesIO(clean)) as image:
        assert not image.getexif() and "exif" not in image.info
        assert image.size == (60, 80)  # the orientation was applied, then dropped


def test_reencode_refuses_non_images_and_huge_images(monkeypatch):
    with pytest.raises(ImageRejected):
        reencode(b"<svg onload=alert(1)>")
    monkeypatch.setattr("services.image_sanitize.MAX_PIXELS", 100)
    with pytest.raises(ImageRejected):
        reencode(jpeg_with_gps())


def test_public_listing_photos_are_stored_without_exif():
    with TestClient(app) as client:
        _, auth = account(client)
        listing = client.post("/marketplace/listings", headers=auth,
                              data={"title": "Coat", "price": "500", "category": "outerwear", "condition": "good"},
                              files=[("files", ("c.jpg", jpeg_with_gps(), "image/jpeg"))]).json()
        stored = market.image_dir() / listing["imageUrls"][0].rsplit("/", 1)[1]
    with Image.open(stored) as image:
        assert not image.getexif()


def test_wardrobe_uploads_are_stored_without_exif(monkeypatch):
    value = {"label": "Shirt", "confidence": 0.9, "top_3": [{"label": "Shirt", "confidence": 0.9}]}
    monkeypatch.setattr(vision_service, "predict", lambda _: {
        "product_type": value, "garment_group": value, "color_group": {**value, "label": "Red"},
        "category": "Top", "embedding": [0.01] * 512})
    with TestClient(app) as client:
        user_id, auth = account(client)
        item = client.post("/wardrobe/upload", headers=auth, data={"user_id": user_id},
                           files={"file": ("a.jpg", jpeg_with_gps(), "image/jpeg")}).json()
    stored = settings.upload_dir / row("SELECT image_path FROM clothing_items WHERE item_id=?", (item["item_id"],))["image_path"]
    with Image.open(stored) as image:
        assert not image.getexif()


@pytest.mark.parametrize("field,value", [
    ("avatarUrl", "https://tracker.example/pixel.png"),
    ("avatarUrl", "file:///var/mobile/photo.jpg"),
    ("fullName", "x" * 101),
    ("heightCm", 9000),
    ("stylePreferences", ["minimal"] * 31),
])
def test_profile_fields_are_validated(field, value):
    with TestClient(app) as client:
        _, auth = account(client)
        assert client.patch("/users/me", headers=auth, json={field: value}).status_code == 422


def test_profile_photo_upload_sets_an_aura_photo():
    with TestClient(app) as client:
        _, auth = account(client)
        user = client.post("/users/me/photo", headers=auth, files={"file": ("me.jpg", jpeg_with_gps(), "image/jpeg")}).json()
        assert user["avatarUrl"].startswith("/marketplace/images/")
        assert client.get(user["avatarUrl"]).status_code == 200
        # The stored URL may be sent back unchanged when the rest of the profile is saved.
        assert client.patch("/users/me", headers=auth, json={"avatarUrl": user["avatarUrl"]}).status_code == 200


def test_json_listings_and_posts_only_take_aura_photos():
    with TestClient(app) as client:
        _, auth = account(client)
        listing = client.post("/marketplace/products", headers=auth, json={
            "title": "T", "price": 10, "category": "tops", "condition": "good", "image_urls": ["https://evil.example/a.jpg"]})
        post = client.post("/social/posts", headers=auth, json={"outfit_image_url": "http://169.254.169.254/", "caption": "hi"})
    assert listing.status_code == 422 and post.status_code == 422


def test_invalid_emails_are_refused_and_conflicts_are_vague():
    with TestClient(app) as client:
        assert client.post("/auth/signup", json={"full_name": "Bad", "email": "not-an-email", "password": PASSWORD}).status_code == 422
        email = f"hy-dup-{uuid.uuid4().hex[:6]}@example.com"
        client.post("/auth/signup", json={"full_name": "First", "email": email, "password": PASSWORD})
        again = client.post("/auth/signup", json={"full_name": "Second", "email": email, "password": PASSWORD})
    assert again.status_code == 409 and "already exists" not in again.json()["detail"]


def test_public_status_endpoints_are_minimal():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert set(client.get("/tryon/status").json()) == {"enabled", "tryon_ready", "worker_running", "queue_length"}
        # Requests through the tunnel come from 127.0.0.1 but carry CF-Connecting-IP.
    with TestClient(app, client=("127.0.0.1", 50000)) as local:
        assert local.get("/health", headers={"CF-Connecting-IP": "203.0.113.5"}).json() == {"status": "ok"}
        assert "resources" in local.get("/health").json()


def test_weather_is_cached_per_city(monkeypatch):
    weather_cache.clear()
    calls = []
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    monkeypatch.setattr(weather_tool, "get_weather", lambda city: calls.append(city) or WeatherContext(
        city="Pune", temperature=30.0, condition="Clear", season="Summer"))
    with TestClient(app) as client:
        _, auth = account(client)
        for city in ("Pune", "pune ", "PUNE"):
            assert client.get("/weather", params={"city": city}, headers=auth).status_code == 200
    assert calls == ["Pune"]
