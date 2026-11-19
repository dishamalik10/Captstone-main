"""Item-level outfit compatibility from the Polyvore-trained AURA transformer.

Unlike the older SHIFT15M model (which only sees broad categories), this model
reads the visual embedding of each specific garment, so it can tell a good
navy-blazer/grey-trouser pairing from a clashing one. It is optional: when the
exported weights are absent the recommender falls back to the previous signals.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

import numpy as np

from ml.outfit_compat import build_model, encode_outfits, predict_scores
from settings import settings
from services.item_embeddings import embeddings_for_items

LOGGER = logging.getLogger(__name__)
_lock = threading.Lock()
_model: Any | None = None
_config: dict[str, Any] | None = None
_last_error: str | None = None
_load_attempted = False


def _load() -> Any | None:
    global _model, _config, _last_error, _load_attempted
    if _model is not None or _load_attempted:
        return _model
    with _lock:
        if _model is not None or _load_attempted:
            return _model
        _load_attempted = True
        if not (settings.outfit_compat_weights_path.is_file() and settings.outfit_compat_config_path.is_file()):
            _last_error = "Polyvore outfit-compatibility weights are not installed."
            return None
        try:
            config = json.loads(settings.outfit_compat_config_path.read_text("utf-8"))
            model = build_model(config.get("model_config"))
            model.load_weights(str(settings.outfit_compat_weights_path))
            _model, _config, _last_error = model, config, None
            LOGGER.info("Loaded Polyvore outfit-compatibility model")
        except Exception as exc:  # pragma: no cover - depends on local artifacts
            _last_error = f"Could not load outfit-compatibility model: {exc}"
            LOGGER.exception(_last_error)
    return _model


def reset_for_tests() -> None:
    global _model, _config, _last_error, _load_attempted
    _model = _config = _last_error = None
    _load_attempted = False


def status() -> dict[str, Any]:
    _load()
    metrics = (_config or {}).get("test_metrics")
    return {
        "available": _model is not None,
        "kind": "item_level_visual_transformer",
        "training_data": (_config or {}).get("training_split"),
        "test_metrics": metrics,
        "last_error": _last_error,
    }


def score_outfits(user_id: str, outfits: list[list[dict[str, Any]]]) -> list[float | None] | None:
    """Return 0-100 compatibility per outfit, ``None`` per outfit lacking embeddings.

    Returns ``None`` overall when the model is not installed.
    """
    model = _load()
    if model is None or not outfits:
        return None
    unique = {item["item_id"]: item for outfit in outfits for item in outfit}
    embeddings = embeddings_for_items(user_id, list(unique.values()))
    scorable: list[int] = []
    packed: list[list[tuple[np.ndarray, str]]] = []
    for index, outfit in enumerate(outfits):
        if all(item["item_id"] in embeddings for item in outfit):
            scorable.append(index)
            packed.append([(embeddings[item["item_id"]], item.get("category", "")) for item in outfit])
    scores: list[float | None] = [None] * len(outfits)
    if not packed:
        return scores
    features, categories = encode_outfits(packed)
    probabilities = predict_scores(model, features, categories)
    for index, probability in zip(scorable, probabilities):
        scores[index] = float(probability) * 100.0
    return scores
