import numpy as np
from PIL import Image

from services import garment_cutout
from services.body_analysis import BACKGROUND, BODY_SKIN, CLOTHES, FACE_SKIN


def photo_with(mask: np.ndarray, monkeypatch) -> Image.Image:
    monkeypatch.setattr(garment_cutout.body_analysis, "models_ready", lambda: True)
    monkeypatch.setattr(garment_cutout, "_category_mask", lambda image: mask)
    pixels = np.full((*mask.shape, 3), 90, dtype=np.uint8)
    pixels[mask == CLOTHES] = (220, 150, 170)  # pink dress
    return Image.fromarray(pixels)


def test_model_photo_keeps_only_the_clothes_on_white(monkeypatch):
    mask = np.full((200, 100), BACKGROUND, dtype=np.uint8)
    mask[10:30, 40:60] = FACE_SKIN
    mask[30:190, 30:70] = BODY_SKIN
    mask[40:140, 30:70] = CLOTHES
    result = garment_cutout.cutout_garment(photo_with(mask, monkeypatch))
    assert result is not None
    pixels = np.asarray(result)
    # Cropped to the dress (100x40) plus padding, so much smaller than the photo.
    assert result.height < 130 and result.width < 60
    assert tuple(pixels[0, 0]) == (255, 255, 255)                 # white surround
    centre = pixels[result.height // 2, result.width // 2]
    assert abs(int(centre[0]) - 220) < 6 and abs(int(centre[1]) - 150) < 6  # the dress
    assert not np.any(np.all(np.abs(pixels.astype(int) - 90) < 4, axis=-1))  # no skin/backdrop left


def test_flat_lay_without_a_person_is_left_alone(monkeypatch):
    mask = np.full((200, 100), BACKGROUND, dtype=np.uint8)
    mask[40:140, 30:70] = CLOTHES
    assert garment_cutout.cutout_garment(photo_with(mask, monkeypatch)) is None


def test_missing_models_skip_the_cutout(monkeypatch):
    monkeypatch.setattr(garment_cutout.body_analysis, "models_ready", lambda: False)
    assert garment_cutout.cutout_garment(Image.new("RGB", (50, 50))) is None
