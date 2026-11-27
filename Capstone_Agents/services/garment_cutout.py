"""Isolate one garment from a photo of someone wearing it (ENGINEERING_PLAN 4.2b).

SegFormer-B2 Clothes labels each pixel (upper clothes, skirt, pants, dress, shoes, bag,
...). The user's chosen category decides which labels are kept, so a model photo of a
sweater with jeans gives just the sweater for "Top" and just the jeans for "Bottom".
The cut-out is the kept pixels, cropped and centred on white.

Photos without a person (flat lays, hangers) are not segmented. The person check uses
the MediaPipe segmenter already installed for My Virtual Look (cheap at 256x256), or
SegFormer's own face/arm/leg labels when MediaPipe isn't installed.

(The earlier MediaPipe cut-out kept every "clothes" pixel, i.e. the whole outfit. It is
removed, not kept as a second path.)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from services import body_analysis
from services.body_analysis import BODY_SKIN, FACE_SKIN, HAIR
from services.garment_segmenter import LABEL, PERSON_LABELS, segmenter

LOGGER = logging.getLogger(__name__)

MIN_PERSON_FRACTION = 0.02   # this much skin/hair in the frame means a person is present
MIN_GARMENT_FRACTION = 0.02  # candidates smaller than this are dropped
PADDING = 0.08
WHITE = (255, 255, 255)
CATEGORIES = ("Top", "Bottom", "Dress", "Outerwear", "Footwear", "Accessory")


@dataclass
class Candidate:
    category: str
    label: str           # what the cut-out shows, for the app ("Upper-clothes", "Set", ...)
    fraction: float      # share of the photo it covers
    image: Image.Image


def _options(category: str) -> list[tuple[str, tuple[str, ...]]]:
    """(label, SegFormer labels kept) for each cut-out a category can produce, best first."""
    if category in ("Top", "Outerwear"):
        # Known limitation: a jacket worn over a tee comes out as both.
        return [("Upper-clothes", ("Upper-clothes",))]
    if category == "Bottom":
        return [("Pants", ("Pants",)), ("Skirt", ("Skirt",))]
    if category == "Dress":
        return [("Dress", ("Dress",)), ("Set", ("Upper-clothes", "Skirt")), ("Set", ("Upper-clothes", "Pants"))]
    if category == "Footwear":
        return [("Shoes", ("Left-shoe", "Right-shoe"))]
    if category == "Accessory":
        return [(name, (name,)) for name in ("Bag", "Hat", "Scarf", "Belt", "Sunglasses")]
    return []


def _render(image: Image.Image, keep: np.ndarray) -> Image.Image | None:
    mask = Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.BILINEAR)
    # Crop to the garment's main body: an opening (erode, then dilate) removes small
    # stray blobs (e.g. a speck near the feet) that would otherwise stretch the crop.
    size = max(5, min(mask.size) // 40) | 1
    bbox = mask.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size)).getbbox() or mask.getbbox()
    if bbox is None:
        return None
    canvas = Image.new("RGB", image.size, WHITE)
    canvas.paste(image, mask=mask.filter(ImageFilter.GaussianBlur(1)))  # soft edge
    garment = canvas.crop(bbox)
    pad = int(max(garment.size) * PADDING)
    framed = Image.new("RGB", (garment.width + 2 * pad, garment.height + 2 * pad), WHITE)
    framed.paste(garment, (pad, pad))
    return framed


def candidates(image: Image.Image, labels: np.ndarray, category: str) -> list[Candidate]:
    """Cut-outs for ``category`` from a SegFormer label map, largest first (the first one
    follows the plan's table: e.g. Bottom = Pants or Skirt, whichever is larger;
    Dress = the dress, else an Upper-clothes + Skirt/Pants "set")."""
    image = image.convert("RGB")
    found: list[Candidate] = []
    for label, names in _options(category):
        parts = [labels == LABEL[name] for name in names]
        keep = np.logical_or.reduce(parts)
        fraction = float(keep.mean())
        # A set needs both of its pieces, and is only offered when no dress was found.
        if (label == "Set" and (found or any(part.mean() < MIN_GARMENT_FRACTION for part in parts))) \
                or fraction < MIN_GARMENT_FRACTION:
            continue
        rendered = _render(image, keep)
        if rendered is not None:
            found.append(Candidate(category, label, fraction, rendered))
    if category in ("Bottom", "Accessory"):
        found.sort(key=lambda candidate: candidate.fraction, reverse=True)
    return found


def person_present(image: Image.Image, labels: np.ndarray | None = None) -> bool | None:
    """True/False, or None when no model is installed to tell."""
    if labels is not None:
        return float(np.isin(labels, [LABEL[name] for name in PERSON_LABELS]).mean()) >= MIN_PERSON_FRACTION
    if body_analysis.models_ready():
        try:
            _, mp_segmenter = body_analysis._models.load()
            with body_analysis._models._lock:
                result = mp_segmenter.segment(body_analysis._mp_image(image.convert("RGB")))
            mask = np.asarray(result.category_mask.numpy_view(), dtype=np.uint8)
            return float(np.isin(mask, (HAIR, BODY_SKIN, FACE_SKIN)).mean()) >= MIN_PERSON_FRACTION
        except Exception:  # an optional check must never block an import
            LOGGER.exception("Person check failed")
            return None
    if segmenter.available():
        return person_present(image, segmenter.segment(image))
    return None


def segment(image: Image.Image) -> np.ndarray | None:
    """SegFormer label map, or None if the model isn't installed or fails."""
    if not segmenter.available():
        return None
    try:
        return segmenter.segment(image)
    except Exception:
        LOGGER.exception("Garment segmentation failed; keeping the original photo")
        return None


def cutout_garment(image: Image.Image, category: str | None = None) -> Image.Image | None:
    """The best cut-out of ``category`` when a person is wearing it, else None (use the
    photo as it is). Without a category the largest top, bottom or dress is used."""
    image = image.convert("RGB")
    labels = segment(image)
    if labels is None or not person_present(image, labels):
        return None
    if category:
        found = candidates(image, labels, category)
    else:
        found = sorted((c for cat in ("Top", "Bottom", "Dress") for c in candidates(image, labels, cat)),
                       key=lambda candidate: candidate.fraction, reverse=True)
    return found[0].image if found else None


# -- target category from the shop page (LQ1) -------------------------------------------
_CATEGORY_WORDS = [
    ("Dress", r"dress(es)?|gown|jumpsuit|playsuit|romper|saree|sari|lehenga|anarkali|co-?ord"),
    ("Outerwear", r"jacket|(?:over|rain|top)?coat|blazer|parka|puffer|gilet|windbreaker|trench|overshirt|shacket"),
    ("Footwear", r"shoes?|sneakers?|trainers?|boots?|sandals?|heels|loafers?|flip-?flops|mules|slippers|juttis?"),
    ("Accessory", r"bag|handbag|tote|backpack|clutch|wallet|hat|cap|beanie|scarf|stole|dupatta|belt|sunglasses|watch|jewell?ery|necklace|earrings?"),
    ("Bottom", r"jeans|trousers?|pants|chinos|joggers|leggings|shorts|skirts?|culottes|palazzos?|salwar|cargos?"),
    ("Top", r"t-?shirts?|tees?|shirts?|tops?|blouses?|sweaters?|jumpers?|hoodies?|sweatshirts?|cardigans?|kurtas?|kurtis?|tanks?|camis?|polos?|pullovers?|tunics?"),
]


def infer_category(*texts: str | None) -> str | None:
    """A category from the product title, JSON-LD category and breadcrumbs, or None.
    The last matching word before any "with ..." wins within a text ("dress shirt" is a
    shirt, "shirt dress" a dress), and earlier texts (the title) win over later ones."""
    for text in texts:
        if not text:
            continue
        lowered = text.lower()
        main = re.split(r"\s+with\s+", lowered)[0]  # "kurta with palazzo" is a kurta
        for part in (main, lowered):
            best: tuple[int, str] | None = None
            for category, pattern in _CATEGORY_WORDS:
                for match in re.finditer(rf"\b(?:{pattern})\b", part):
                    if best is None or match.start() > best[0]:
                        best = (match.start(), category)
            if best:
                return best[1]
    return None
