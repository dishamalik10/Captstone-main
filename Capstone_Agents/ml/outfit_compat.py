"""AURA outfit-compatibility transformer (trained from scratch on Polyvore Outfits).

Each garment is represented by the 512-d ``fashion_feature_normalization``
embedding from AURA's own EfficientNetV2 garment CNN plus its broad AURA
category. A small transformer encoder reads the whole outfit as a set and
predicts whether the pieces belong together.

This file is shared verbatim by the backend and
``training/AURA_Outfit_Compatibility_Polyvore_Colab.ipynb``. Keep it free of
backend imports so it can run unchanged in Colab.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

EMBEDDING_DIM = 512
MAX_ITEMS = 16
EMBEDDING_LAYER = "fashion_feature_normalization"

# 0 is padding, the CLS token uses its own learned vector.
AURA_CATEGORIES = ("Top", "Bottom", "Dress", "Footwear", "Outerwear", "Accessory")
CATEGORY_TO_ID = {name: index + 1 for index, name in enumerate(AURA_CATEGORIES)}

# Polyvore Outfits "semantic_category" -> AURA wardrobe category.
POLYVORE_TO_AURA = {
    "tops": "Top",
    "bottoms": "Bottom",
    "all-body": "Dress",
    "shoes": "Footwear",
    "outerwear": "Outerwear",
    "bags": "Accessory",
    "accessories": "Accessory",
    "jewellery": "Accessory",
    "hats": "Accessory",
    "scarves": "Accessory",
    "sunglasses": "Accessory",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "embedding_dim": EMBEDDING_DIM,
    "max_items": MAX_ITEMS,
    "model_dim": 256,
    "num_heads": 4,
    "num_layers": 4,
    "ff_dim": 512,
    "dropout": 0.1,
    "input_noise": 0.05,
    "feature_dropout": 0.1,
}


def category_id(category: str | None) -> int:
    """Map an AURA category name to its integer id (unknown -> Accessory)."""
    return CATEGORY_TO_ID.get(str(category or ""), CATEGORY_TO_ID["Accessory"])


def encode_outfits(
    outfits: Sequence[Sequence[tuple[np.ndarray, str]]],
    max_items: int = MAX_ITEMS,
) -> tuple[np.ndarray, np.ndarray]:
    """Pack outfits of (embedding, AURA category) pairs into padded arrays."""
    features = np.zeros((len(outfits), max_items, EMBEDDING_DIM), dtype=np.float32)
    categories = np.zeros((len(outfits), max_items), dtype=np.int32)
    for row, outfit in enumerate(outfits):
        for column, (embedding, category) in enumerate(list(outfit)[:max_items]):
            features[row, column] = np.asarray(embedding, dtype=np.float32)
            categories[row, column] = category_id(category)
    return features, categories


def build_model(config: dict[str, Any] | None = None):
    """Build the Keras model. Weights are random until trained or loaded."""
    import keras
    from keras import layers, ops

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    d_model = int(cfg["model_dim"])

    @keras.saving.register_keras_serializable(package="AURAOutfitCompat")
    class OutfitEncoder(layers.Layer):
        def __init__(self, cfg: dict[str, Any], **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.cfg = dict(cfg)
            self.project = layers.Dense(d_model, name="item_projection")
            self.category_embedding = layers.Embedding(
                len(AURA_CATEGORIES) + 1, d_model, name="category_embedding"
            )
            self.noise = layers.GaussianNoise(float(cfg["input_noise"]))
            self.feature_dropout = layers.Dropout(float(cfg["feature_dropout"]))
            self.blocks = []
            for index in range(int(cfg["num_layers"])):
                self.blocks.append({
                    "norm_1": layers.LayerNormalization(epsilon=1e-6, name=f"block{index}_norm1"),
                    "attention": layers.MultiHeadAttention(
                        num_heads=int(cfg["num_heads"]),
                        key_dim=d_model // int(cfg["num_heads"]),
                        dropout=float(cfg["dropout"]),
                        name=f"block{index}_attention",
                    ),
                    "drop_1": layers.Dropout(float(cfg["dropout"])),
                    "norm_2": layers.LayerNormalization(epsilon=1e-6, name=f"block{index}_norm2"),
                    "ff_1": layers.Dense(int(cfg["ff_dim"]), activation="gelu", name=f"block{index}_ff1"),
                    "ff_2": layers.Dense(d_model, name=f"block{index}_ff2"),
                    "drop_2": layers.Dropout(float(cfg["dropout"])),
                })
            self.final_norm = layers.LayerNormalization(epsilon=1e-6, name="final_norm")

        def build(self, input_shape: Any) -> None:
            self.cls_token = self.add_weight(
                name="cls_token", shape=(1, 1, d_model), initializer="random_normal", trainable=True
            )
            super().build(input_shape)

        def call(self, features: Any, categories: Any, training: bool | None = None) -> Any:
            features = self.noise(features, training=training)
            features = self.feature_dropout(features, training=training)
            tokens = self.project(features) + self.category_embedding(categories)
            batch = ops.shape(tokens)[0]
            cls = ops.broadcast_to(self.cls_token, (batch, 1, d_model))
            tokens = ops.concatenate([cls, tokens], axis=1)
            valid = ops.concatenate(
                [ops.ones((batch, 1), dtype="bool"), ops.greater(categories, 0)], axis=1
            )
            mask = ops.logical_and(ops.expand_dims(valid, 1), ops.expand_dims(valid, 2))
            x = tokens
            for block in self.blocks:
                y = block["norm_1"](x)
                y = block["attention"](y, y, attention_mask=mask, training=training)
                x = x + block["drop_1"](y, training=training)
                y = block["norm_2"](x)
                y = block["ff_2"](block["ff_1"](y))
                x = x + block["drop_2"](y, training=training)
            return self.final_norm(x)[:, 0, :]

        def get_config(self) -> dict[str, Any]:
            return {**super().get_config(), "cfg": self.cfg}

    features = keras.Input((int(cfg["max_items"]), int(cfg["embedding_dim"])), name="features")
    categories = keras.Input((int(cfg["max_items"]),), dtype="int32", name="categories")
    pooled = OutfitEncoder(cfg, name="outfit_encoder")(features, categories)
    hidden = layers.Dense(d_model, activation="gelu", name="head_hidden")(pooled)
    hidden = layers.Dropout(float(cfg["dropout"]))(hidden)
    logit = layers.Dense(1, name="compatibility_logit")(hidden)
    return keras.Model({"features": features, "categories": categories}, logit, name="aura_outfit_compat")


def predict_scores(model: Any, features: np.ndarray, categories: np.ndarray, batch_size: int = 512) -> np.ndarray:
    """Return compatibility probabilities in [0, 1] for packed outfits."""
    logits = model.predict(
        {"features": features, "categories": categories}, batch_size=batch_size, verbose=0
    )
    logits = np.asarray(logits, dtype=np.float64).reshape(-1)
    return 1.0 / (1.0 + np.exp(-logits))
