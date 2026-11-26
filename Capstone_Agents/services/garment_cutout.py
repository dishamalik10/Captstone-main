"""Cut the clothes out of a photo of someone wearing them (e.g. a shop's model photo).

Uses the MediaPipe Selfie Multiclass segmenter already installed for virtual try-on
(categories: background / hair / body skin / face skin / clothes / other). When a
person is visible, only the "clothes" pixels are kept, cropped and centred on a white
background, so the garment CNN sees the garment rather than the model, the pose or
the backdrop. Photos without a person (flat lays, hangers) are left unchanged.
"""
from __future__ import annotations

import logging

import numpy as np
from PIL import Image, ImageFilter

from services import body_analysis
from services.body_analysis import BODY_SKIN, CLOTHES, FACE_SKIN, HAIR

LOGGER = logging.getLogger(__name__)

# A person counts as present when this much of the frame is skin/hair...
MIN_PERSON_FRACTION = 0.02
# ...and the clothes they wear cover at least this much of it.
MIN_CLOTHES_FRACTION = 0.015
PADDING = 0.08
WHITE = (255, 255, 255)


def _category_mask(image: Image.Image) -> np.ndarray:
    _, segmenter = body_analysis._models.load()
    with body_analysis._models._lock:
        result = segmenter.segment(body_analysis._mp_image(image))
    mask = np.asarray(result.category_mask.numpy_view(), dtype=np.uint8)
    mask = mask.reshape(result.category_mask.height, result.category_mask.width)
    if mask.shape != (image.height, image.width):
        mask = np.asarray(Image.fromarray(mask).resize(image.size, Image.NEAREST))
    return mask


def cutout_garment(image: Image.Image) -> Image.Image | None:
    """The worn clothes on white, or None when there is no person / no clear garment
    (or the segmentation models are not installed), meaning: use the photo as it is."""
    if not body_analysis.models_ready():
        return None
    image = image.convert("RGB")
    try:
        categories = _category_mask(image)
    except Exception:  # never block an upload because the optional cut-out failed
        LOGGER.exception("Garment cut-out failed; keeping the original photo")
        return None
    person = np.isin(categories, (HAIR, BODY_SKIN, FACE_SKIN)).mean()
    clothes = categories == CLOTHES
    if person < MIN_PERSON_FRACTION or clothes.mean() < MIN_CLOTHES_FRACTION:
        return None
    # Median filter drops speckles (stray pixels in hair or the backdrop).
    mask = Image.fromarray((clothes * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))
    bbox = mask.getbbox()
    if bbox is None:
        return None
    canvas = Image.new("RGB", image.size, WHITE)
    canvas.paste(image, mask=mask.filter(ImageFilter.GaussianBlur(1)))  # soft edge
    garment = canvas.crop(bbox)
    pad = int(max(garment.size) * PADDING)
    framed = Image.new("RGB", (garment.width + 2 * pad, garment.height + 2 * pad), WHITE)
    framed.paste(garment, (pad, pad))
    return framed
