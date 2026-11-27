"""Garment isolation (ENGINEERING_PLAN 4.2b). Replaces the MediaPipe "keep every clothes
pixel" cut-out, whose tests lived here: the same intents are covered for SegFormer
(model photo -> only the garment on white; flat lay left alone; no model -> no cut-out),
plus the plan's tests: Top vs Bottom on a sweater/jeans photo, photo choice, preview
expiry, and the user's category winning."""
import json
import time
import uuid
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from database import row
from main import app
from services import garment_cutout, import_previews
from services import product_link_service as links
from services.garment_segmenter import LABEL, segmenter
from services.vision_service import vision_service
from settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "blouse_and_jeans_cc0.jpg"
TOP_COLOUR, JEANS_COLOUR, SKIN = (230, 230, 240), (40, 60, 120), (200, 160, 130)


def model_photo():
    """A synthetic person: face/arms (skin), a top, jeans, on grey."""
    labels = np.full((200, 100), LABEL["Background"], dtype=np.uint8)
    labels[5:25, 40:60] = LABEL["Face"]
    labels[25:95, 15:30] = LABEL["Left-arm"]
    labels[25:95, 30:70] = LABEL["Upper-clothes"]
    labels[95:190, 30:70] = LABEL["Pants"]
    pixels = np.full((200, 100, 3), 90, dtype=np.uint8)
    pixels[labels == LABEL["Face"]] = SKIN
    pixels[labels == LABEL["Left-arm"]] = SKIN
    pixels[labels == LABEL["Upper-clothes"]] = TOP_COLOUR
    pixels[labels == LABEL["Pants"]] = JEANS_COLOUR
    return Image.fromarray(pixels), labels


def colours(image):
    pixels = np.asarray(image).reshape(-1, 3).astype(int)
    near = lambda c: np.all(np.abs(pixels - c) < 12, axis=1).mean()  # noqa: E731
    return {"top": near(TOP_COLOUR), "jeans": near(JEANS_COLOUR), "skin": near(SKIN), "grey": near((90, 90, 90))}


def test_top_keeps_only_the_top_on_white_and_bottom_only_the_jeans():
    photo, labels = model_photo()
    [top] = garment_cutout.candidates(photo, labels, "Top")
    [bottom] = garment_cutout.candidates(photo, labels, "Bottom")
    assert top.label == "Upper-clothes" and bottom.label == "Pants"
    assert tuple(np.asarray(top.image)[0, 0]) == (255, 255, 255)  # white surround
    seen = colours(top.image)
    assert seen["top"] > 0.3 and seen["jeans"] < 0.01 and seen["skin"] < 0.01 and seen["grey"] < 0.01
    seen = colours(bottom.image)
    assert seen["jeans"] > 0.3 and seen["top"] < 0.01
    # A set is offered for "Dress" only because no dress was found; footwear: nothing there.
    assert [c.label for c in garment_cutout.candidates(photo, labels, "Dress")] == ["Set"]
    assert garment_cutout.candidates(photo, labels, "Footwear") == []


def test_flat_lay_without_a_person_is_left_alone(monkeypatch):
    labels = np.full((200, 100), LABEL["Background"], dtype=np.uint8)
    labels[40:140, 30:70] = LABEL["Upper-clothes"]
    monkeypatch.setattr(garment_cutout, "segment", lambda image: labels)
    assert garment_cutout.person_present(Image.new("RGB", (100, 200)), labels) is False
    assert garment_cutout.cutout_garment(Image.new("RGB", (100, 200)), "Top") is None


def test_missing_model_skips_the_cutout(monkeypatch):
    monkeypatch.setattr(segmenter, "available", lambda: False)
    assert garment_cutout.segment(Image.new("RGB", (50, 50))) is None
    assert garment_cutout.cutout_garment(Image.new("RGB", (50, 50)), "Top") is None


def test_stray_specks_do_not_stretch_the_crop():
    photo, labels = model_photo()
    labels[196:198, 90:92] = LABEL["Upper-clothes"]  # a speck far below the top
    [top] = garment_cutout.candidates(photo, labels, "Top")
    assert top.image.height < 100  # cropped to the top (70 px + padding), not down to the speck


@pytest.mark.parametrize("texts,expected", [
    (("Men Slim Fit Dress Shirt",), "Top"),
    (("Floral Shirt Dress",), "Dress"),
    (("Wool Blend Overcoat",), "Outerwear"),
    (("Cotton Kurta with Palazzo",), "Top"),
    (("Black and white striped tee",), "Top"),
    (("Product 123", "Women > Jeans"), "Bottom"),  # breadcrumbs when the title says nothing
    (("Product 123",), None),
])
def test_category_is_inferred_from_the_shop_page(texts, expected):
    assert garment_cutout.infer_category(*texts) == expected


def test_product_page_prefers_a_photo_without_a_person(monkeypatch):
    html = """<html><head><meta property="og:image" content="https://cdn.shop.example/model.jpg">
      <script type="application/ld+json">{"@type":"Product","name":"Ribbed Sweater","category":"Knitwear",
       "image":["https://cdn.shop.example/model.jpg","https://cdn.shop.example/flat.jpg"]}</script></head></html>"""

    def jpeg(colour):
        buffer = BytesIO()
        Image.new("RGB", (20, 20), colour).save(buffer, format="JPEG")
        return buffer.getvalue()

    pages = {"https://shop.example/p/1": (html.encode(), "text/html"),
             "https://cdn.shop.example/model.jpg": (jpeg((255, 0, 0)), "image/jpeg"),
             "https://cdn.shop.example/flat.jpg": (jpeg((0, 0, 255)), "image/jpeg")}
    monkeypatch.setattr(links, "_get", lambda url, max_bytes, deadline: (*pages[url], url))
    is_red = lambda content: Image.open(BytesIO(content)).getpixel((5, 5))[0] > 200  # noqa: E731  red = model shot
    result = links.import_from_link("https://shop.example/p/1", 5_000_000, has_person=is_red)
    assert result.image_url == "https://cdn.shop.example/flat.jpg" and result.person_free is True
    assert result.hints == ("Ribbed Sweater", "Knitwear")
    # Every photo shows a person: the first is used, marked as not person-free.
    result = links.import_from_link("https://shop.example/p/1", 5_000_000, has_person=lambda content: True)
    assert result.image_url == "https://cdn.shop.example/model.jpg" and result.person_free is False


# -- preview -> confirm through the API ---------------------------------------------------

def account(client):
    body = client.post("/auth/signup", json={"full_name": "Cut", "email": f"cut-{uuid.uuid4().hex[:8]}@example.com",
                                             "password": "secure-pass-123"}).json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['token']}"}


def stub_cnn(monkeypatch, category="Top", label="Sweater"):
    value = {"label": label, "confidence": 0.9, "top_3": [{"label": label, "confidence": 0.9}]}
    monkeypatch.setattr(vision_service, "predict", lambda path: {
        "product_type": value, "garment_group": {**value, "label": "Knitwear"},
        "color_group": {**value, "label": "White"}, "category": category, "embedding": [0.01] * 512})


def upload_preview(client, user_id, auth, photo):
    buffer = BytesIO()
    photo.save(buffer, format="JPEG")
    return client.post("/wardrobe/upload/preview", headers=auth, data={"user_id": user_id},
                       files={"file": ("p.jpg", buffer.getvalue(), "image/jpeg")})


def test_preview_then_confirm_a_cutout_and_the_users_category_wins(monkeypatch):
    photo, labels = model_photo()
    monkeypatch.setattr(garment_cutout, "segment", lambda image: labels)
    stub_cnn(monkeypatch, category="Top", label="Sweater")
    with TestClient(app) as client:
        user_id, auth = account(client)
        preview = upload_preview(client, user_id, auth, photo)
        assert preview.status_code == 201, preview.text
        body = preview.json()
        assert body["person_found"] and body["suggested_category"] == "Top"  # from the CNN (no page hints)
        assert set(body["candidates"]) == {"Top", "Outerwear", "Bottom", "Dress"}
        for url in [body["original_url"], body["candidates"]["Bottom"][0]["image_url"]]:
            assert client.get(url).status_code == 200  # served to the owner via signed URLs
        # The user says it's the jeans; the CNN still calls the cut-out a Top.
        item = client.post(f"/wardrobe/imports/{body['preview_id']}/confirm", headers=auth,
                           json={"choice": "cutout", "category": "Bottom"}).json()
        assert item["category"] == "Bottom" and item["needs_review"] is True and item["garment_cutout"] is True
        assert item["subcategory"] == "Sweater"  # the CNN's type is kept
        listed = client.get(f"/wardrobe/{user_id}", headers=auth).json()
        assert [i["category"] for i in listed] == ["Bottom"]  # survives the type-name rule
        # The preview and its other files are gone.
        assert row("SELECT 1 FROM import_previews WHERE preview_id=?", (body["preview_id"],)) is None
        assert not list(settings.upload_dir.glob(f"preview_{body['preview_id']}_*"))
        again = client.post(f"/wardrobe/imports/{body['preview_id']}/confirm", headers=auth,
                            json={"choice": "original", "category": "Top"})
        assert again.status_code == 404


def test_confirming_the_original_photo_with_the_cnns_category_is_not_flagged(monkeypatch):
    monkeypatch.setattr(garment_cutout, "segment", lambda image: None)  # no model installed
    stub_cnn(monkeypatch, category="Top")
    with TestClient(app) as client:
        user_id, auth = account(client)
        body = upload_preview(client, user_id, auth, Image.new("RGB", (60, 80), (200, 200, 200))).json()
        assert body["person_found"] is False and body["candidates"] == {}
        assert client.post(f"/wardrobe/imports/{body['preview_id']}/confirm", headers=auth,
                           json={"choice": "cutout", "category": "Top"}).status_code == 422
        item = client.post(f"/wardrobe/imports/{body['preview_id']}/confirm", headers=auth,
                           json={"choice": "original", "category": "Top"}).json()
        assert item["needs_review"] is False and item["garment_cutout"] is False


def test_previews_are_private_and_expire_after_an_hour(monkeypatch):
    monkeypatch.setattr(garment_cutout, "segment", lambda image: None)
    stub_cnn(monkeypatch)
    with TestClient(app) as client:
        user_id, auth = account(client)
        _, other = account(client)
        body = upload_preview(client, user_id, auth, Image.new("RGB", (60, 80))).json()
        assert client.post(f"/wardrobe/imports/{body['preview_id']}/confirm", headers=other,
                           json={"choice": "original", "category": "Top"}).status_code == 404
        original = settings.upload_dir / f"preview_{body['preview_id']}_original.jpg"
        assert original.is_file()
        assert import_previews.cleanup_expired(now=time.time() + import_previews.TTL_SECONDS - 60) == 0
        assert import_previews.cleanup_expired(now=time.time() + import_previews.TTL_SECONDS + 1) >= 1
        assert not original.exists()
        assert client.get(body["original_url"]).status_code == 404


def test_discarding_a_preview_deletes_its_files(monkeypatch):
    photo, labels = model_photo()
    monkeypatch.setattr(garment_cutout, "segment", lambda image: labels)
    stub_cnn(monkeypatch)
    with TestClient(app) as client:
        user_id, auth = account(client)
        body = upload_preview(client, user_id, auth, photo).json()
        files = json.loads(row("SELECT files_json FROM import_previews WHERE preview_id=?", (body["preview_id"],))["files_json"])
        assert client.delete(f"/wardrobe/imports/{body['preview_id']}", headers=auth).status_code == 204
    assert not (settings.upload_dir / files["original"]).exists()


@pytest.mark.skipif(not (settings.tryon_model_dir / "segformer_b2_clothes" / "model.onnx").is_file(),
                    reason="SegFormer model not downloaded (python -m training.download_tryon_models)")
def test_real_segformer_separates_the_blouse_from_the_jeans():
    pytest.importorskip("onnxruntime")
    object.__setattr__(settings, "garment_segmentation", True)
    try:
        photo = Image.open(FIXTURE).convert("RGB")
        labels = garment_cutout.segment(photo)
        assert labels is not None and garment_cutout.person_present(photo, labels)
        [top] = garment_cutout.candidates(photo, labels, "Top")
        [bottom] = garment_cutout.candidates(photo, labels, "Bottom")
    finally:
        object.__setattr__(settings, "garment_segmentation", False)
    assert (top.label, bottom.label) == ("Upper-clothes", "Pants")
    # The blouse is light, the jeans dark blue: each cut-out holds only its garment.
    def mean_non_white(image):
        pixels = np.asarray(image).reshape(-1, 3).astype(int)
        return pixels[pixels.min(axis=1) < 235].mean(axis=0)
    blouse, jeans = mean_non_white(top.image), mean_non_white(bottom.image)
    assert blouse.mean() > 150 and jeans[2] > jeans[0] + 20 and jeans.mean() < 130
    assert top.image.height < photo.height * 0.6  # the blouse only, not the whole outfit
