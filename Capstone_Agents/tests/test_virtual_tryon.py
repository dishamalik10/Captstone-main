"""My Virtual Look: avatar creation, proportions, masks, render jobs and privacy.

The MediaPipe and CatVTON models are replaced by deterministic doubles, so these tests
need no model downloads; they check AURA's own logic around those models.
"""
import importlib.util
import time
import uuid
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from services import body_analysis as ba
from services import tryon_service

# Body analysis uses OpenCV, which ships with the optional try-on extras
# (mediapipe in requirements-local.txt). Without it these tests are skipped, not failed.
needs_cv2 = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="OpenCV (cv2) not installed; install requirements-local.txt for My Virtual Look",
)

W, H = 600, 1000


def synthetic_person(arms_away: bool = True) -> ba.ParsedPhoto:
    """A simple front-facing figure: face, clothed torso, legs, on a plain background."""
    parsing = np.zeros((H, W), np.uint8)
    cx = W // 2
    parsing[80:200, cx - 50:cx + 50] = ba.FACE_SKIN
    parsing[60:90, cx - 55:cx + 55] = ba.HAIR
    parsing[220:520, cx - 110:cx + 110] = ba.CLOTHES           # top (shoulders 220px wide)
    parsing[360:420, cx - 80:cx + 80] = ba.CLOTHES             # waist narrower than shoulders...
    parsing[360:420, cx - 110:cx - 80] = ba.BACKGROUND
    parsing[360:420, cx + 80:cx + 110] = ba.BACKGROUND
    parsing[520:900, cx - 100:cx - 10] = ba.BODY_SKIN          # legs
    parsing[520:900, cx + 10:cx + 100] = ba.BODY_SKIN
    arm_x = 150 if arms_away else 105
    for side in (-1, 1):
        x = cx + side * arm_x
        parsing[230:500, min(x, x + side * 30):max(x, x + side * 30)] = ba.BODY_SKIN
    lm = np.zeros((33, 3), np.float32)
    lm[:, 2] = 0.95

    def put(i, x, y):
        lm[i] = (x, y, 0.95)

    put(ba.NOSE, cx, 140)
    put(ba.L_SHOULDER, cx + 95, 230), put(ba.R_SHOULDER, cx - 95, 230)
    put(ba.L_ELBOW, cx + arm_x, 370), put(ba.R_ELBOW, cx - arm_x, 370)
    put(ba.L_WRIST, cx + arm_x, 490), put(ba.R_WRIST, cx - arm_x, 490)
    for i in ba.HAND_POINTS:
        put(i, cx + (arm_x if i % 2 else -arm_x), 505)
    put(ba.L_HIP, cx + 60, 500), put(ba.R_HIP, cx - 60, 500)
    put(ba.L_KNEE, cx + 55, 700), put(ba.R_KNEE, cx - 55, 700)
    put(ba.L_ANKLE, cx + 55, 890), put(ba.R_ANKLE, cx - 55, 890)
    for i in ba.FOOT_POINTS:
        put(i, cx + (55 if i % 2 else -55), 910)
    colours = np.array([[240, 240, 240], [40, 30, 20], [150, 100, 80], [160, 110, 90], [200, 30, 40], [0, 0, 0]], np.uint8)
    return ba.ParsedPhoto(image=Image.fromarray(colours[parsing]), parsing=parsing, landmarks=lm)


def test_validation_rejects_cut_off_feet_and_small_photos():
    parsed = synthetic_person()
    parsed.landmarks[[ba.L_ANKLE, ba.R_ANKLE], 2] = 0.1
    with pytest.raises(ba.BodyPhotoError, match="feet"):
        ba.validate(parsed)
    small = synthetic_person()
    small.image = small.image.resize((200, 330))
    with pytest.raises(ba.BodyPhotoError, match="too small"):
        ba.validate(small)


@needs_cv2
def test_avatar_keeps_the_person_and_reports_approximate_proportions():
    parsed = synthetic_person()
    warnings = ba.validate(parsed)
    avatar, parsing, landmarks = ba.build_avatar(parsed)
    assert avatar.size == ba.AVATAR_SIZE and parsing.shape == (ba.AVATAR_SIZE[1], ba.AVATAR_SIZE[0])
    # The person's colours are kept (no restyling); only the background changes.
    shoulder_y = int(landmarks[ba.L_SHOULDER, 1]) + 30
    assert tuple(np.asarray(avatar)[shoulder_y, ba.AVATAR_SIZE[0] // 2]) == (200, 30, 40)
    result = ba.analyze_proportions(parsing, landmarks, avatar, warnings)
    assert result["ratios"]["waist_to_hip"] < 1.0
    assert result["body_shape"] in {"hourglass", "rectangle", "pear", "apple", "athletic"}
    assert "not a body measurement" in result["method"]


@needs_cv2
def test_arms_against_the_body_lower_confidence():
    parsed = synthetic_person(arms_away=False)
    warnings = ba.validate(parsed)
    assert any("arms" in w.lower() for w in warnings)
    avatar, parsing, landmarks = ba.build_avatar(parsed)
    assert ba.analyze_proportions(parsing, landmarks, avatar, warnings)["confidence"] == "low"


def test_body_shape_rules():
    assert ba.classify_shape({"shoulder_to_hip": 0.85, "waist_to_hip": 0.7, "waist_to_shoulder": 0.8})[0] == "pear"
    assert ba.classify_shape({"shoulder_to_hip": 1.2, "waist_to_hip": 0.8, "waist_to_shoulder": 0.65})[0] == "athletic"
    assert ba.classify_shape({"shoulder_to_hip": 1.0, "waist_to_hip": 0.7, "waist_to_shoulder": 0.7})[0] == "hourglass"
    assert ba.classify_shape({"shoulder_to_hip": 1.0, "waist_to_hip": 0.95, "waist_to_shoulder": 0.95})[0] == "apple"


@needs_cv2
def test_tryon_masks_cover_the_garment_area_and_protect_face_and_feet():
    parsed = synthetic_person()
    _, parsing, lm = ba.build_avatar(parsed)
    face = parsing == ba.FACE_SKIN
    feet_row = int(lm[ba.L_ANKLE, 1] + 20)
    for region in ("upper", "lower", "overall"):
        mask = np.asarray(ba.tryon_mask(parsing, lm, region)) > 0
        assert mask.any()
        assert not (mask & face).any(), region
        assert not mask[feet_row:].any(), region
    upper = np.asarray(ba.tryon_mask(parsing, lm, "upper")) > 0
    lower = np.asarray(ba.tryon_mask(parsing, lm, "lower")) > 0
    torso_y = int(lm[ba.L_SHOULDER, 1] + 40)
    knee_y = int(lm[ba.L_KNEE, 1])
    assert upper[torso_y].any() and not upper[knee_y].any()
    assert lower[knee_y].any() and not lower[torso_y].any()


def test_layer_plan_orders_garments_and_reports_unrendered_pieces():
    items = [
        {"category": "Outerwear", "color_name": "Black", "subcategory": "Blazer"},
        {"category": "Top", "color_name": "Pink", "subcategory": "Sweater"},
        {"category": "Footwear", "color_name": "White", "subcategory": "Sneakers"},
        {"category": "Bottom", "color_name": "Black", "subcategory": "Skirt"},
    ]
    layers, skipped = tryon_service.plan_layers(items)
    assert [item["category"] for item in layers] == ["Bottom", "Top", "Outerwear"]
    assert skipped == ["White Sneakers"]
    layers, skipped = tryon_service.plan_layers([{"category": "Dress", "color_name": "Red", "subcategory": "Dress"},
                                                 {"category": "Top", "color_name": "Pink", "subcategory": "Top"}])
    assert [item["category"] for item in layers] == ["Dress"] and skipped == ["Pink Top"]


class FakeCatVTON:
    """Stands in for the diffusion model: paints the masked area with the garment's mean colour."""

    def __init__(self):
        self.calls = 0
        self.loaded = False

    def missing_files(self):
        return []

    def load(self):
        self.loaded = True

    def unload(self):
        self.loaded = False

    def __call__(self, person, garment, mask, *, size, steps, guidance, seed, progress=None):
        self.calls += 1
        colour = tuple(int(c) for c in np.asarray(garment.convert("RGB")).reshape(-1, 3).mean(axis=0))
        if progress:
            progress(1.0)
        return Image.composite(Image.new("RGB", person.size, colour), person, mask)


def _wait(client, auth, render_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        tryon_service.process_next()  # what the worker process does on each poll
        body = client.get(f"/tryon/{render_id}", headers=auth).json()
        if body["status"] in {"done", "failed"}:
            return body
        time.sleep(0.1)
    raise AssertionError("render did not finish")


@needs_cv2
def test_full_virtual_look_workflow(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from services.vision_service import vision_service

    fake = FakeCatVTON()
    monkeypatch.setattr(tryon_service, "model", fake)
    monkeypatch.setattr(ba, "parse_photo", lambda image: synthetic_person())
    monkeypatch.setattr(ba.garment_cutter, "cut", lambda image: image.convert("RGB"))
    garments = iter([
        ("Sweater", "Knitwear", "Pink", "Top"),
        ("Skirt", "Skirts", "Black", "Bottom"),
        ("Sneakers", "Shoes", "White", "Footwear"),
    ])

    def predict(_):
        product, group, color, category = next(garments)
        value = lambda label: {"label": label, "confidence": 0.95, "top_3": [{"label": label, "confidence": 0.95}]}
        return {"product_type": value(product), "garment_group": value(group), "color_group": value(color),
                "category": category, "embedding": [0.01] * 512}

    monkeypatch.setattr(vision_service, "predict", predict)

    def jpeg(colour=(120, 120, 120), size=(64, 64)):
        buffer = BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="JPEG")
        return buffer.getvalue()

    with TestClient(app) as client:
        account = client.post("/auth/signup", json={"full_name": "Look Test", "email": f"v{uuid.uuid4().hex[:6]}@example.com", "password": "secure-pass-123"})
        user_id, token = account.json()["user"]["id"], account.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        item_ids = []
        for colour in ((230, 120, 160), (20, 20, 20), (250, 250, 250)):
            response = client.post("/wardrobe/upload", headers=auth, data={"user_id": user_id},
                                   files={"file": ("g.jpg", jpeg(colour), "image/jpeg")})
            assert response.status_code == 201, response.text
            item_ids.append(response.json()["item_id"])

        # No avatar yet: try-on explains what to do.
        assert client.post("/tryon", headers=auth, json={"item_ids": item_ids}).status_code == 409
        # The first body photo needs the consent statement (4.3).
        assert client.get("/avatar", headers=auth).json()["consent_given"] is False
        refused = client.post("/avatar", headers=auth, files={"file": ("me.jpg", jpeg(size=(600, 1000)), "image/jpeg")})
        assert refused.status_code == 428 and "18 or over" in refused.json()["detail"]
        # Non-images are rejected before any analysis.
        bad = client.post("/avatar", headers=auth, data={"consent": "true"}, files={"file": ("x.jpg", b"not an image", "image/jpeg")})
        assert bad.status_code == 422

        created = client.post("/avatar", headers=auth, files={"file": ("me.jpg", jpeg(size=(600, 1000)), "image/jpeg")})  # consent already recorded
        assert created.status_code == 201, created.text
        avatar = created.json()
        assert avatar["analysis"]["body_shape"]
        assert client.get(avatar["image_url"]).status_code == 200   # signed private link works

        render = client.post("/tryon", headers=auth, json={"item_ids": item_ids}).json()
        done = _wait(client, auth, render["render_id"])
        assert done["status"] == "done", done
        assert done["not_rendered"] == ["White Sneakers"]
        assert fake.calls == 2                                    # skirt, then sweater; shoes not drawn
        assert "not a physical fit" in done["disclaimer"]
        look = client.get(done["image_url"])
        assert look.status_code == 200 and look.content[:4] == b"\x89PNG"

        # Same avatar + outfit is served from cache, not re-rendered.
        again = client.post("/tryon", headers=auth, json={"item_ids": list(reversed(item_ids))}).json()
        assert again["render_id"] == done["render_id"] and fake.calls == 2

        saved = client.post(f"/tryon/{done['render_id']}/save", headers=auth).json()
        assert saved["saved"] is True
        assert [look["render_id"] for look in client.get("/tryon/saved", headers=auth).json()] == [done["render_id"]]

        # Another account can neither read the look nor use someone else's garments.
        other = client.post("/auth/signup", json={"full_name": "Other", "email": f"o{uuid.uuid4().hex[:6]}@example.com", "password": "secure-pass-123"}).json()
        other_auth = {"Authorization": f"Bearer {other['token']}"}
        assert client.get(f"/tryon/{done['render_id']}", headers=other_auth).status_code == 404
        client.post("/avatar", headers=other_auth, data={"consent": "true"}, files={"file": ("me.jpg", jpeg(size=(600, 1000)), "image/jpeg")})
        assert client.post("/tryon", headers=other_auth, json={"item_ids": item_ids}).status_code == 422

        # Privacy: deleting removes the photos and every look, and their links stop working.
        assert client.delete("/avatar", headers=auth).status_code == 204
        assert client.get("/avatar", headers=auth).json()["avatars"] == {}
        assert client.get(avatar["image_url"]).status_code == 404
        assert client.get(done["image_url"]).status_code == 404
        # Deleting body data withdraws consent: the next photo asks again.
        assert client.get("/avatar", headers=auth).json()["consent_given"] is False
        again = client.post("/avatar", headers=auth, files={"file": ("me.jpg", jpeg(size=(600, 1000)), "image/jpeg")})
        assert again.status_code == 428


def test_parsing_masks_are_never_served():
    """Only the avatar and finished looks are reachable through signed media links."""
    from pathlib import Path

    assert not tryon_service.owns_media("nobody", Path("/tmp/parsing_x.png"))


@needs_cv2
def test_stray_objects_are_dropped_from_the_avatar():
    parsing = np.zeros((200, 100), dtype=np.uint8)
    parsing[20:180, 40:60] = ba.CLOTHES        # the person
    parsing[30:40, 45:50] = ba.HAIR            # detail inside the person's box: kept
    parsing[185:198, 2:15] = ba.OTHER          # a bag on the floor, outside the person
    cleaned = ba.keep_person_only(parsing)
    assert (cleaned[185:198, 2:15] == ba.BACKGROUND).all()
    assert (cleaned[20:180, 40:60] != ba.BACKGROUND).all()


@needs_cv2
def test_old_trousers_left_beside_hands_and_ankles_are_found_and_filled():
    from PIL import Image

    height, width = 400, 200
    lm = np.zeros((33, 3), dtype=np.float32)
    lm[:, 2] = 1
    for index, (x, y) in {ba.L_SHOULDER: (130, 60), ba.R_SHOULDER: (70, 60), ba.L_HIP: (120, 180),
                          ba.R_HIP: (80, 180), ba.L_KNEE: (118, 280), ba.R_KNEE: (82, 280),
                          ba.L_ANKLE: (116, 370), ba.R_ANKLE: (84, 370)}.items():
        lm[index, :2] = (x, y)
    parsing = np.zeros((height, width), dtype=np.uint8)
    parsing[180:385, 70:130] = ba.CLOTHES                       # black trousers in the photo
    photo = np.full((height, width, 3), 236, dtype=np.uint8)
    photo[180:385, 70:130] = (20, 20, 22)
    original = Image.fromarray(photo)
    # The new render painted shorts + bare legs down to 360, but kept the hem (protected feet).
    rendered = photo.copy()
    rendered[180:230, 70:130] = (70, 80, 120)                   # blue shorts
    rendered[230:360, 70:130] = (190, 140, 110)                 # legs
    painted = np.zeros((height, width), dtype=bool)
    painted[180:360] = True
    leftover = ba.leftover_bottom(original, parsing, lm, painted)
    assert leftover[365:385, 80:120].all()                      # the hem over the ankles
    assert not leftover[180:230, 80:120].any()                  # the new shorts are left alone
    fixed = np.asarray(ba.remove_leftover(Image.fromarray(rendered), leftover, lm))
    assert fixed[375, 100].mean() > 100                         # no black hem left

    # Fabric the model *continued* in black (inside the mask) is caught when the new garment differs.
    rendered[240:260, 70:80] = (20, 20, 22)
    shorts = Image.new("RGB", (40, 40), (70, 80, 120))
    caught = ba.leftover_bottom(original, parsing, lm, painted, rendered=Image.fromarray(rendered),
                                new_colour=ba.garment_colour_lab(shorts))
    assert caught[245:255, 72:78].all()
    # ...but not when the new garment is the same colour as the old one (black on black).
    same = ba.leftover_bottom(original, parsing, lm, painted, rendered=Image.fromarray(rendered),
                              new_colour=ba.garment_colour_lab(Image.new("RGB", (40, 40), (20, 20, 22))))
    assert not same[245:255, 72:78].any()
