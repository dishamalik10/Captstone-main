from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from settings import settings


OUTERWEAR = {
    "Blazer", "Coat", "Jacket", "Outdoor Waistcoat", "Parka", "Vest jacket",
}
DRESSES = {"Dress", "Dungarees", "Garment Set", "Jumpsuit/Playsuit"}
BOTTOMS = {
    "Bikini bottom", "Leggings/Tights", "Outdoor trousers", "Shorts",
    "Skirt", "Swimwear bottom", "Trousers", "Underwear bottom",
}
FOOTWEAR_HINTS = {"Boots", "Flat shoe", "Heels", "Other shoe", "Sandals", "Slippers", "Sneakers"}
ACCESSORY_HINTS = {
    "Bag", "Backpack", "Belt", "Cap/peaked", "Earring", "Gloves",
    "Hair clip", "Hair string", "Hat/beanie", "Necklace", "Ring", "Scarf",
    "Sunglasses", "Tie", "Umbrella", "Wallet", "Watch",
}


def map_category(product_type: str, garment_group: str) -> str:
    if product_type in OUTERWEAR:
        return "Outerwear"
    if product_type in DRESSES or "dress" in product_type.lower():
        return "Dress"
    if product_type in BOTTOMS:
        return "Bottom"
    if product_type in FOOTWEAR_HINTS or garment_group == "Shoes":
        return "Footwear"
    if product_type in ACCESSORY_HINTS or garment_group in {"Accessories", "Bags", "Items and Equipments"}:
        return "Accessory"
    if garment_group in {"Garment Lower body", "Skirts"}:
        return "Bottom"
    return "Top"


class VisionService:
    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()
        self.metadata = json.loads(settings.metadata_path.read_text(encoding="utf-8"))
        self.image_size = int(self.metadata["image_size"])

    def _load_model(self) -> Any:
        """Load the CNN with an extra output: the 512-d garment embedding."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    import tensorflow as tf
                    from ml.outfit_compat import EMBEDDING_LAYER

                    base = tf.keras.models.load_model(
                        settings.model_path,
                        compile=False,
                    )
                    self._output_names = ["embedding", "color_group", "garment_group", "product_type"]
                    self._model = tf.keras.Model(
                        base.input,
                        [base.get_layer(EMBEDDING_LAYER).output, *base.outputs],
                    )
        return self._model

    def _open(self, image_path: Path) -> Image.Image:
        image = Image.open(image_path)
        # Phone photos are often stored sideways with an EXIF rotation tag.
        image = ImageOps.exif_transpose(image)
        return image.convert("RGB")

    def _batch(self, image: Image.Image) -> np.ndarray:
        image = image.resize((self.image_size, self.image_size), Image.Resampling.LANCZOS)
        return np.expand_dims(np.asarray(image, dtype=np.float32), axis=0)

    def _run(self, image: Image.Image) -> dict[str, np.ndarray]:
        raw = self._load_model().predict(self._batch(image), verbose=0)
        return {name: np.asarray(values)[0] for name, values in zip(self._output_names, raw, strict=True)}

    def embed(self, image_path: Path) -> list[float]:
        """512-d visual embedding used by the outfit-compatibility model."""
        return self._run(self._open(image_path))["embedding"].astype(float).tolist()

    def _decode(self, probabilities: np.ndarray, target: str) -> dict[str, Any]:
        labels = self.metadata["targets"][target]
        indexes = np.argsort(probabilities)[-3:][::-1]
        choices = [
            {"label": labels[int(index)], "confidence": float(probabilities[index])}
            for index in indexes
        ]
        return {
            "label": choices[0]["label"],
            "confidence": choices[0]["confidence"],
            "top_3": choices,
        }

    def predict(self, image_path: Path) -> dict[str, Any]:
        image = self._open(image_path)
        # A center crop supplies a rough pixel sample alongside the model's
        # garment color class; it is not a segmentation mask or exact garment color.
        width, height = image.size
        crop = image.crop((width // 4, height // 4, width * 3 // 4, height * 3 // 4))
        sample = np.asarray(crop.resize((32, 32), Image.Resampling.BILINEAR), dtype=np.uint8)
        median_rgb = np.median(sample.reshape(-1, 3), axis=0).round().astype(int).tolist()
        color_sample = {
            "rgb": median_rgb,
            "hex": "#" + "".join(f"{channel:02X}" for channel in median_rgb),
            "method": "median_center_crop_approximation",
            "note": "Approximate image color; background and lighting are not segmented or corrected.",
        }
        outputs = self._run(image)
        predictions: dict[str, Any] = {
            name: self._decode(outputs[name], name)
            for name in ("color_group", "garment_group", "product_type")
        }
        predictions["embedding"] = outputs["embedding"].astype(float).tolist()
        predictions["category"] = map_category(
            predictions["product_type"]["label"],
            predictions["garment_group"]["label"],
        )
        predictions["color_sample"] = color_sample
        return predictions


vision_service = VisionService()
