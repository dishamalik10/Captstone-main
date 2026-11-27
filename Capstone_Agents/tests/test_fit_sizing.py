"""ENGINEERING_PLAN 4.11: body measurements, garment sizes, size advice and fit-aware try-on masks."""
import json
import math
import uuid
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from database import ensure_user, init_database, row
from main import app
from services import body_analysis as ba
from services import body_measurements as bm
from services import fit_advice, size_chart, tryon_fit, tryon_service
from services.product_link_service import find_product_size
from settings import settings
from tests.test_virtual_tryon import needs_cv2

pytestmark = pytest.mark.usefixtures("remove_new_listings")
PASSWORD = "secure-pass-123"
HEIGHT = 170.0
PERSON_PX = 800  # rows 100..899 in the synthetic photos
CM = HEIGHT / PERSON_PX


# -- synthetic photos with known widths and depths --------------------------------------

def _landmarks(points: dict[int, tuple[float, float]]) -> np.ndarray:
    lm = np.zeros((33, 3), np.float32)
    lm[:, 2] = 0.99
    for hand, wrist in zip(ba.HAND_POINTS, [ba.L_WRIST, ba.R_WRIST] * 3):
        points[hand] = points[wrist]
    for foot, ankle in zip(ba.FOOT_POINTS, [ba.L_ANKLE, ba.R_ANKLE] * 2):
        points[foot] = points[ankle]
    for index, (x, y) in points.items():
        lm[index, :2] = (x, y)
    return lm


def front_photo():
    """Chest 160 px wide, waist 130, hip 170; legs apart below row 560; feet at row 899."""
    p = np.zeros((1000, 1000), np.uint8)
    p[100:200, 460:540] = ba.FACE_SKIN
    p[200:250, 475:525] = ba.BODY_SKIN
    p[250:300, 400:600] = ba.CLOTHES
    p[300:340, 420:580] = ba.CLOTHES
    p[340:480, 435:565] = ba.CLOTHES
    p[480:560, 415:585] = ba.CLOTHES
    p[560:900, 415:485] = ba.CLOTHES
    p[560:900, 515:585] = ba.CLOTHES
    lm = _landmarks({
        ba.NOSE: (500, 150), ba.L_SHOULDER: (440, 250), ba.R_SHOULDER: (560, 250),
        ba.L_ELBOW: (330, 420), ba.R_ELBOW: (670, 420), ba.L_WRIST: (300, 560), ba.R_WRIST: (700, 560),
        ba.L_HIP: (460, 500), ba.R_HIP: (540, 500), ba.L_KNEE: (450, 700), ba.R_KNEE: (550, 700),
        ba.L_ANKLE: (450, 880), ba.R_ANKLE: (550, 880),
    })
    return p, lm


def side_photo():
    """Chest 100 px deep, waist 90, hip 110."""
    p = np.zeros((1000, 1000), np.uint8)
    p[100:200, 470:530] = ba.FACE_SKIN
    p[200:250, 480:520] = ba.BODY_SKIN
    p[250:340, 450:550] = ba.CLOTHES
    p[340:480, 455:545] = ba.CLOTHES
    p[480:900, 445:555] = ba.CLOTHES
    _, lm = front_photo()
    lm[[ba.L_SHOULDER, ba.R_SHOULDER, ba.L_HIP, ba.R_HIP], 0] = 500
    return p, lm


# -- measurements -------------------------------------------------------------------------

def test_ellipse_circumference():
    assert bm.ellipse_circumference(10, 10) == pytest.approx(math.pi * 10)
    assert bm.ellipse_circumference(4, 2) == pytest.approx(9.6884, abs=1e-3)  # a=2, b=1


@needs_cv2
def test_estimate_from_known_widths_and_depths():
    values = bm.estimate(bm.outline(*front_photo()), bm.outline(*side_photo(), side=True), HEIGHT)
    assert values["chest"] == pytest.approx(bm.ellipse_circumference(160 * CM, 100 * CM), abs=0.1)
    assert values["waist"] == pytest.approx(bm.ellipse_circumference(130 * CM, 90 * CM), abs=0.1)
    assert values["hip"] == pytest.approx(bm.ellipse_circumference(170 * CM, 110 * CM), abs=0.1)
    assert values["shoulder"] == pytest.approx(200 * CM, abs=0.1)
    assert values["torso"] == pytest.approx(250 * CM, abs=0.1)
    assert values["inseam"] == pytest.approx((899 - 560) * CM, abs=0.5)


@needs_cv2
def test_estimate_scales_each_photo_by_its_own_height():
    """The same body photographed from further away (half size) measures the same."""
    front, lm = front_photo()
    small = np.asarray(Image.fromarray(front).resize((500, 500), Image.NEAREST))
    lm_small = lm.copy()
    lm_small[:, :2] /= 2
    full = bm.estimate(bm.outline(front, lm), bm.outline(*side_photo(), side=True), HEIGHT)
    half = bm.estimate(bm.outline(small, lm_small), bm.outline(*side_photo(), side=True), HEIGHT)
    assert half["chest"] == pytest.approx(full["chest"], rel=0.03)
    assert half["waist"] == pytest.approx(full["waist"], rel=0.03)


def _user() -> str:
    init_database()
    user_id = f"fit_{uuid.uuid4().hex[:8]}"
    ensure_user(user_id)
    return user_id


@needs_cv2
def test_low_confidence_photos_give_no_estimate(monkeypatch):
    user_id = _user()
    monkeypatch.setattr(bm, "front_photo", lambda avatar: (*front_photo(), []))
    monkeypatch.setattr(bm, "side_photo", lambda photo: (*side_photo(), []))
    assert bm.estimate_from_photos(user_id, Image.new("RGB", (8, 8)), Image.new("RGB", (8, 8)), HEIGHT)["status"] == "estimated"
    assert "chest" in bm.merged(user_id)
    monkeypatch.setattr(bm, "side_photo", lambda photo: (*side_photo(), ["Loose or layered clothing hides your outline."]))
    result = bm.estimate_from_photos(user_id, Image.new("RGB", (8, 8)), Image.new("RGB", (8, 8)), HEIGHT)
    assert result["status"] == "not_estimated" and result["problems"]
    assert bm.merged(user_id) == {}  # stale estimates are not shown


def test_typed_values_win_and_can_be_cleared():
    user_id = _user()
    bm._save(user_id, estimate={"chest": 96.0, "waist": 80.0})
    bm.set_manual(user_id, {"chest": 92})
    view = bm.merged(user_id)
    assert view["chest"] == {"value": 92.0, "source": "you"}
    assert view["waist"]["source"] == "estimated"
    bm.set_manual(user_id, {"chest": None})
    assert bm.merged(user_id)["chest"]["source"] == "estimated"
    with pytest.raises(bm.MeasurementError):
        bm.set_manual(user_id, {"waist": 400})


def test_estimates_are_ranges_until_the_accuracy_check_passes(monkeypatch, tmp_path):
    user_id = _user()
    bm._save(user_id, estimate={"chest": 100.0, "hip": 100.0})
    monkeypatch.setattr(bm, "ACCURACY_RESULTS", tmp_path / "missing.json")
    view = bm.merged(user_id)
    assert view["chest"]["range_only"] and (view["chest"]["low"], view["chest"]["high"]) == (95, 105)
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"zones": {"chest": {"pass": True}, "hip": {"pass": False}}}))
    monkeypatch.setattr(bm, "ACCURACY_RESULTS", results)
    view = bm.merged(user_id)
    assert not view["chest"]["range_only"] and view["hip"]["range_only"]


# -- size chart and advice ---------------------------------------------------------------

def test_size_chart_maps_labels_to_body_ranges():
    m = size_chart.parse("m", "Top", "men")
    assert m.body["chest"] == (94.0, 100.0)
    assert size_chart.parse("M", "Top").system == "letter (unisex)"
    assert size_chart.parse("UK 12", "Dress").body["waist"] == (70.5, 75.5)
    assert size_chart.parse("US 8", "Dress").body == size_chart.parse("UK 12", "Dress").body
    jeans = size_chart.parse("32/30", "Bottom")
    assert jeans.body["waist"] == (79.3, 83.3) and jeans.inseam_cm == pytest.approx(76.2)
    assert size_chart.parse("W32 L30", "Bottom").inseam_cm == pytest.approx(76.2)
    assert size_chart.parse("40", "Top").body["chest"] == (99.6, 103.6)  # chest in inches
    assert size_chart.parse("32", "Bottom").body["waist"] == (79.3, 83.3)  # waist in inches
    assert size_chart.parse("EU 50", "Outerwear", "men").body["chest"] == (98, 102)
    for unknown in ("Free size", "one size", "", None, "XXXXL"):
        assert size_chart.parse(unknown, "Top") is None


@pytest.mark.parametrize("delta, rating", [
    (-8.1, "tight"), (-8, "snug"), (-3.1, "snug"), (-3, "regular"), (4, "regular"),
    (4.1, "relaxed"), (12, "relaxed"), (12.1, "loose"),
])
def test_rating_boundaries(delta, rating):
    assert fit_advice.rate(delta) == rating


def _body(**values):
    return {zone: {"value": value, "source": "you"} for zone, value in values.items()}


def test_advice_from_the_size_chart():
    body = _body(chest=97, waist=85)
    right = fit_advice.advise("Top", {"label": "M", "chart": "men"}, body)
    assert right["verdict"] == "Should fit well" and {z["rating"] for z in right["zones"]} == {"regular"}
    assert right["estimated"] and "generic size chart" in right["garment_basis"]
    small = fit_advice.advise("Top", {"label": "XS", "chart": "men"}, body)
    assert small["verdict"] == "Likely too small"
    oversized = fit_advice.advise("Top", {"label": "M", "chart": "men"}, body, cut="Oversized")
    assert oversized["verdict"] == "Likely too big"
    # A preference for a relaxed fit makes a regular M read snugger.
    relaxed = fit_advice.advise("Top", {"label": "M", "chart": "men"}, body, fit_preference="Relaxed")
    assert {z["rating"] for z in relaxed["zones"]} == {"snug"}


def test_advice_from_garment_measurements_and_lengths():
    body = _body(waist=80, hip=98, inseam=78)
    size = {"label": None, "measurements": {"waist_flat_cm": 41, "hip_flat_cm": 52, "inseam_cm": 70}}
    advice = fit_advice.advise("Bottom", size, body)
    zones = {z["zone"]: z for z in advice["zones"]}
    assert zones["waist"]["garment_cm"] == 82 and zones["waist"]["rating"] == "regular"
    assert zones["hip"]["rating"] == "regular"  # 104 - 98 = 6 = the regular ease
    assert advice["lengths"] == [{"zone": "inseam", "rating": "short", "difference_cm": -8.0}]
    assert advice["garment_basis"] == "garment measurements" and not advice["estimated"]
    crop = fit_advice.advise("Top", {"measurements": {"chest_flat_cm": 50, "length_cm": 40}}, _body(chest=90, torso=50))
    assert crop["lengths"][0]["rating"] == "cropped"


def test_advice_falls_back_to_usual_sizes_and_skips_shoes():
    advice = fit_advice.advise("Top", {"label": "L"}, {}, usual_sizes={"top": "L", "bottom": "32"})
    assert advice["verdict"] == "Should fit well" and advice["estimated"]
    assert any("usual size" in note for note in advice["notes"])
    assert not fit_advice.advise("Top", {"label": "L"}, {})["available"]
    assert not fit_advice.advise("Footwear", {"label": "9"}, _body(chest=90))["available"]
    assert not fit_advice.advise("Top", {"label": "Free size"}, _body(chest=90))["available"]


# -- try-on masks ------------------------------------------------------------------------

def _lowest_row(mask) -> int:
    return int(np.nonzero(np.asarray(mask).any(axis=1))[0].max())


def _width(mask, y) -> int:
    return int((np.asarray(mask)[y] > 0).sum())


@needs_cv2
def test_mask_hem_follows_garment_length():
    p, lm = front_photo()
    default = ba.tryon_mask(p, lm, "upper")
    crop = ba.tryon_mask(p, lm, "upper", ba.MaskFit(hem_y=380))
    kurta = ba.tryon_mask(p, lm, "upper", ba.MaskFit(hem_y=700))
    # The crop top's mask still covers the photo's own top below the hem (it must be repainted),
    # but no bare skin; a kurta's reaches the knees.
    assert _lowest_row(kurta) > _lowest_row(default) + 100
    assert np.asarray(crop)[560:].sum() == 0
    shorts = ba.tryon_mask(p, lm, "lower", ba.MaskFit(hem_y=620))
    trousers = ba.tryon_mask(p, lm, "lower")
    # Bare legs below the shorts' hem are not repainted ... but these legs are clothes
    # (old trousers), which must be repainted, so the masks agree there.
    assert _lowest_row(shorts) == _lowest_row(trousers)


@needs_cv2
def test_mask_hem_on_bare_legs():
    p, lm = front_photo()
    p[600:900][p[600:900] == ba.CLOTHES] = ba.BODY_SKIN  # bare legs below row 600
    shorts = ba.tryon_mask(p, lm, "lower", ba.MaskFit(hem_y=620))
    trousers = ba.tryon_mask(p, lm, "lower")
    assert _lowest_row(shorts) < _lowest_row(trousers) - 150


@needs_cv2
def test_mask_widens_with_ease():
    p, lm = front_photo()
    regular = ba.tryon_mask(p, lm, "upper")
    roomy = ba.tryon_mask(p, lm, "upper", ba.MaskFit(widen_px=20))
    assert _width(roomy, 400) == _width(regular, 400) + 40
    assert _width(roomy, 150) == _width(regular, 150)  # never up into the head


@needs_cv2
def test_mask_fit_from_item_size():
    p, lm = front_photo()
    plain = {"item_id": "a", "category": "Top", "subcategory": "Shirt", "fit": None, "size": None}
    assert tryon_fit.mask_fit(plain, p, lm, HEIGHT, {}) is None
    crop = tryon_fit.mask_fit({**plain, "subcategory": "Crop top"}, p, lm, None, {})
    assert crop.hem_y == pytest.approx(250 + 250 * 0.62)
    measured = tryon_fit.mask_fit({**plain, "size": {"measurements": {"length_cm": 74}}}, p, lm, HEIGHT, {})
    assert measured.hem_y == pytest.approx(250 + (74 - 4) / CM)
    roomy_item = {**plain, "size": {"label": "XL", "chart": "men"}}
    assert tryon_fit.mask_fit(roomy_item, p, lm, HEIGHT, _body(chest=97)) is None  # widening is off by default
    object.__setattr__(settings, "tryon_fit_widen", True)
    try:
        assert tryon_fit.mask_fit(roomy_item, p, lm, HEIGHT, _body(chest=97)).widen_px > 0
    finally:
        object.__setattr__(settings, "tryon_fit_widen", False)
    assert tryon_fit.signature([plain], HEIGHT, {}) is None
    assert tryon_fit.signature([{**plain, "size": {"label": "M"}}], HEIGHT, {})


# -- API -----------------------------------------------------------------------------------

def signup(client):
    body = client.post("/auth/signup", json={"full_name": "Fit Tester", "email": f"fit-{uuid.uuid4().hex[:8]}@example.com",
                                             "password": PASSWORD}).json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['token']}"}


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_measurement_routes_and_body_data_deletion():
    tryon_service.init_tables()
    client = TestClient(app)
    user_id, headers = signup(client)
    other_id, other_headers = signup(client)
    assert client.get("/body/measurements", headers=headers).json()["measurements"] == {}
    saved = client.put("/body/measurements", headers=headers, json={"chest": 94, "waist": 80, "height_cm": 172}).json()
    assert saved["measurements"]["chest"] == {"value": 94.0, "source": "you"} and saved["height_cm"] == 172
    assert client.put("/body/measurements", headers=headers, json={"waist": 5}).status_code == 422
    assert client.get("/body/measurements", headers=other_headers).json()["measurements"] == {}
    # Estimating needs consent and a front photo first.
    files = {"file": ("side.jpg", jpeg(), "image/jpeg")}
    assert client.post("/body/measurements/estimate", headers=headers, files=files).status_code == 428
    tryon_service.require_consent(user_id, True)
    assert client.post("/body/measurements/estimate", headers=headers, files=files).status_code == 409
    # "Delete my body data" removes measurements and height.
    assert client.delete("/avatar", headers=headers).status_code == 204
    after = client.get("/body/measurements", headers=headers).json()
    assert after["measurements"] == {} and after["height_cm"] is None
    assert row("SELECT 1 FROM body_measurements WHERE user_id=?", (user_id,)) is None


@needs_cv2
def test_estimate_route_never_stores_the_side_photo(monkeypatch):
    tryon_service.init_tables()
    client = TestClient(app)
    user_id, headers = signup(client)
    tryon_service.require_consent(user_id, True)
    monkeypatch.setattr(tryon_service, "get_avatars", lambda uid: {"front": {"view": "front"}})
    monkeypatch.setattr(tryon_service, "front_avatar_image", lambda uid: Image.new("RGB", (8, 8)))
    monkeypatch.setattr(bm, "front_photo", lambda avatar: (*front_photo(), []))
    monkeypatch.setattr(bm, "side_photo", lambda photo: (*side_photo(), []))
    before = set(settings.upload_dir.iterdir())
    response = client.post("/body/measurements/estimate", headers=headers, data={"height_cm": "170"},
                           files={"file": ("side.jpg", jpeg(), "image/jpeg")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "estimated" and body["measurements"]["chest"]["source"] == "estimated"
    assert body["height_cm"] == 170
    assert set(settings.upload_dir.iterdir()) == before


def test_item_size_and_fit_routes(monkeypatch):
    from services.vision_service import vision_service

    value = {"label": "Shirt", "confidence": 0.9, "top_3": [{"label": "Shirt", "confidence": 0.9}]}
    monkeypatch.setattr(vision_service, "predict", lambda path: {
        "product_type": value, "garment_group": value, "color_group": {**value, "label": "Blue"},
        "category": "Top", "embedding": [0.01] * 512})
    monkeypatch.setattr("main.cutout_garment", lambda image, category=None: None, raising=False)
    client = TestClient(app)
    user_id, headers = signup(client)
    item = client.post("/wardrobe/upload", headers=headers, data={"user_id": user_id},
                       files={"file": ("shirt.jpg", jpeg(), "image/jpeg")}).json()
    assert item["size"] is None
    assert not client.get(f"/wardrobe/{user_id}/{item['item_id']}/fit", headers=headers).json()["available"]
    updated = client.patch(f"/wardrobe/{user_id}/{item['item_id']}", headers=headers,
                           json={"size": {"label": "M", "chart": "men"}}).json()
    assert updated["size"]["label"] == "M"
    client.put("/body/measurements", headers=headers, json={"chest": 97, "waist": 85})
    fit = client.get(f"/wardrobe/{user_id}/{item['item_id']}/fit", headers=headers).json()
    assert fit["available"] and fit["verdict"] == "Should fit well"
    cleared = client.patch(f"/wardrobe/{user_id}/{item['item_id']}", headers=headers, json={"size": {}}).json()
    assert cleared["size"] is None
    other_id, other_headers = signup(client)
    assert client.get(f"/wardrobe/{user_id}/{item['item_id']}/fit", headers=other_headers).status_code == 403


def test_listing_fit_is_for_the_viewer():
    client = TestClient(app)
    seller_id, seller_headers = signup(client)
    viewer_id, viewer_headers = signup(client)
    photo = "/marketplace/images/" + "0" * 32 + ".jpg"  # format check only
    product = client.post("/marketplace/products", headers=seller_headers, json={
        "title": "Linen shirt", "price": 500, "image_urls": [photo], "category": "tops",
        "condition": "good", "size": "L"}).json()
    client.put("/body/measurements", headers=viewer_headers, json={"chest": 96, "waist": 84})
    fit = client.get(f"/marketplace/products/{product['id']}/fit", headers=viewer_headers).json()
    assert fit["available"] and fit["zones"][0]["body_cm"] == 96
    assert not client.get(f"/marketplace/products/{product['id']}/fit", headers=seller_headers).json()["available"]
    assert client.get(f"/marketplace/products/{product['id']}/fit").status_code == 401


def test_product_page_size():
    one = '<script type="application/ld+json">{"@type": "Product", "name": "Tee", "size": "M"}</script>'
    offer = '<script type="application/ld+json">{"@type": "Product", "offers": {"@type": "Offer", "size": ["32/32"]}}</script>'
    many = '<script type="application/ld+json">{"@type": "Product", "size": ["S", "M", "L"]}</script>'
    assert find_product_size(one) == "M"
    assert find_product_size(offer) == "32/32"
    assert find_product_size(many) is None


def test_accuracy_summary_rule():
    from scripts.measurement_accuracy import summarise

    good = [{"volunteer": f"V{i}", "zone": "chest", "tape_cm": "90", "app_cm": str(90 + d)}
            for i, d in enumerate([1, -2, 3, 0.5, -1])]
    bad = [{"volunteer": f"V{i}", "zone": "waist", "tape_cm": "80", "app_cm": str(80 + d)}
           for i, d in enumerate([6, -5, 2, 7, 1])]
    few = [{"volunteer": "V1", "zone": "hip", "tape_cm": "100", "app_cm": "100"}]
    zones = summarise(good + bad + few)["zones"]
    assert zones["chest"]["pass"] and not zones["waist"]["pass"] and not zones["hip"]["pass"]
    with pytest.raises(ValueError):
        summarise([{"volunteer": "V1", "zone": "neck", "tape_cm": "1", "app_cm": "1"}])
