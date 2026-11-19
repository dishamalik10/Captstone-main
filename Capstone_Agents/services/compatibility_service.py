from __future__ import annotations

import itertools
import json
import logging
from functools import lru_cache
from typing import Any

import numpy as np

from settings import settings


LOGGER = logging.getLogger(__name__)

# SHIFT15M/IQON broad category families. The exported training artifact does
# not include human-readable category_id2 names, so AURA averages over every
# learned subcategory in the matching broad family. This is deliberately more
# conservative than guessing a precise numeric subcategory.
CATEGORY_PREFIXES: dict[str, tuple[str, ...]] = {
    "Outerwear": ("10",),
    "Top": ("11",),
    "Bottom": ("12",),
    "Dress": ("13",),
    "Footwear": ("14",),
    "Accessory": ("15", "16"),
}

_model: Any | None = None
_family_ids: dict[str, tuple[int, ...]] | None = None
_load_attempted = False


def _load_artifacts() -> tuple[Any | None, dict[str, tuple[int, ...]]]:
    global _model, _family_ids, _load_attempted

    if _load_attempted:
        return _model, _family_ids or {}
    _load_attempted = True

    try:
        import tensorflow as tf

        @tf.keras.utils.register_keras_serializable(package="AURA")
        class AbsoluteDifference(tf.keras.layers.Layer):
            def call(self, inputs: list[Any]) -> Any:
                left, right = inputs
                return tf.abs(left - right)

            def compute_output_shape(self, input_shape: list[Any]) -> Any:
                return input_shape[0]

        vocab = json.loads(settings.compatibility_vocab_path.read_text("utf-8"))
        _family_ids = {
            category: tuple(
                int(index)
                for code, index in vocab.items()
                if code.startswith(prefixes)
            )
            for category, prefixes in CATEGORY_PREFIXES.items()
        }
        _model = tf.keras.models.load_model(
            settings.compatibility_model_path,
            custom_objects={
                "AbsoluteDifference": AbsoluteDifference,
                "AURA>AbsoluteDifference": AbsoluteDifference,
            },
            compile=False,
        )
    except Exception:
        LOGGER.exception("SHIFT15M compatibility model is unavailable")
        _model = None
        _family_ids = {}

    return _model, _family_ids


@lru_cache(maxsize=32)
def _category_pair_score(left_category: str, right_category: str) -> float | None:
    model, family_ids = _load_artifacts()
    left_ids = family_ids.get(left_category, ())
    right_ids = family_ids.get(right_category, ())
    if model is None or not left_ids or not right_ids:
        return None

    pairs = list(itertools.product(left_ids, right_ids))
    predictions = model.predict(
        {
            "left_item": np.asarray([pair[0] for pair in pairs], dtype=np.int32),
            "right_item": np.asarray([pair[1] for pair in pairs], dtype=np.int32),
        },
        verbose=0,
    )
    return float(np.mean(predictions) * 100.0)


def learned_compatibility_score(items: list[dict[str, Any]]) -> float | None:
    """Return the mean learned pair score, or None when it cannot be scored."""
    pair_scores: list[float] = []
    for left, right in itertools.combinations(items, 2):
        left_category = str(left.get("category", ""))
        right_category = str(right.get("category", ""))
        score = _category_pair_score(*sorted((left_category, right_category)))
        if score is not None:
            pair_scores.append(score)
    return float(np.mean(pair_scores)) if pair_scores else None


def compatibility_model_status() -> dict[str, Any]:
    model, family_ids = _load_artifacts()
    return {
        "available": model is not None,
        "model_path": str(settings.compatibility_model_path),
        "mapped_categories": sorted(
            category for category, ids in family_ids.items() if ids
        ),
    }
