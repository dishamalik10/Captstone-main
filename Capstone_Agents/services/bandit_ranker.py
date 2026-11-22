"""Personalised outfit ranking as a contextual bandit (Thompson sampling).

Reinforcement-learning framing
------------------------------
* Context / state: the occasion plus each candidate outfit's features.
* Action: which outfit to put at the top of the list.
* Reward: the user's reaction (wear > save > like > skip > dislike), mapped to [0, 1].
* Policy: a Bayesian linear model ``reward ≈ w · x``. Each ranking samples ``w`` from
  the posterior (Thompson sampling), so the app keeps exploring outfits it is unsure
  about instead of always repeating the same one.

Cold start: the prior mean reproduces the hand-tuned ranker exactly (60% rule signals,
40% learned compatibility), so a new user sees the same ranking as before. Every
reaction then moves that user's own posterior; nothing is shared between users.

Features (``FEATURE_NAMES``):
* 12 ranker signals (colour, occasion, weather, …, learned compatibility), scaled to 0–1.
* 8 style descriptors (dress, layered, dark/light/colourful share, …) — once globally and
  once per occasion group, so "likes dark looks for dates" is learned separately from
  "likes light looks for the office".
* 1 visual-taste feature: how close the outfit's garment-CNN embeddings are to what the
  user liked versus disliked (per occasion group, falling back to all occasions).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

SIGNALS = (
    "color", "occasion", "weather", "preference", "feedback", "learned_preference",
    "novelty", "trend", "pattern", "silhouette", "fabric_weather", "learned_compatibility",
)
# The hand-tuned ranker: rule_total * 0.6 + learned_compatibility * 0.4.
RULE_WEIGHTS = {
    "color": 0.17, "occasion": 0.17, "weather": 0.14, "preference": 0.14, "feedback": 0.08,
    "learned_preference": 0.13, "novelty": 0.05, "trend": 0.03, "pattern": 0.03,
    "silhouette": 0.03, "fabric_weather": 0.03,
}
COMPAT_WEIGHT = 0.40
PRIOR_SIGNAL_WEIGHTS = {
    **{name: weight * (1.0 - COMPAT_WEIGHT) for name, weight in RULE_WEIGHTS.items()},
    "learned_compatibility": COMPAT_WEIGHT,
}

STYLES = (
    "has_dress", "layered", "dark_share", "light_share", "colourful_share",
    "patterned_share", "piece_count", "has_footwear",
)
OCCASION_GROUPS = ("formal", "evening", "casual", "active")
_GROUP_OF = {
    **{name: "formal" for name in ("meeting", "office", "work", "interview", "wedding", "formal", "smart casual")},
    **{name: "evening" for name in ("date", "party", "festival", "concert")},
    **{name: "active" for name in ("gym", "workout", "sport")},
}

FEATURE_NAMES = (
    *SIGNALS,
    *(f"style:{name}" for name in STYLES),
    *(f"{group}:{name}" for group in OCCASION_GROUPS for name in STYLES),
    "visual_taste",
)
DIM = len(FEATURE_NAMES)

# Prior precision: trust the hand-tuned signal weights, learn personal style quickly.
PRIOR_PRECISION_SIGNALS = 40.0
PRIOR_PRECISION_STYLE = 2.0
NOISE_VARIANCE = 0.08
# Posterior-sampling scale; 0.5 chosen on the simulated-user evaluation (training/evaluate_bandit.py).
EXPLORATION = 0.5

REWARD = {"wear": 1.0, "save": 0.9, "like": 0.85, "skip": 0.35, "dislike": 0.0}

DARK = {"black", "navy", "charcoal", "maroon", "burgundy", "brown", "dark", "olive"}
LIGHT = {"white", "cream", "ivory", "beige", "light", "pastel"}
NEUTRAL = {"black", "white", "grey", "gray", "beige", "cream", "ivory", "navy", "brown", "tan", "camel", "khaki", "charcoal"}


def occasion_group(occasion: str) -> str:
    return _GROUP_OF.get((occasion or "").lower(), "casual")


def reward_for(action: str, rating: int | None = None) -> float | None:
    if action == "rate":
        return None if rating is None else (min(5, max(1, rating)) - 1) / 4.0
    return REWARD.get(action)


def style_vector(items: list[dict[str, Any]]) -> np.ndarray:
    if not items:
        return np.zeros(len(STYLES))
    words = [set(str(item.get("color_name") or "").lower().replace("-", " ").split()) for item in items]
    categories = [str(item.get("category") or "") for item in items]
    patterns = [str(item.get("pattern") or "").lower() for item in items]
    n = float(len(items))
    return np.array([
        float("Dress" in categories),
        float("Outerwear" in categories),
        sum(bool(w & DARK) for w in words) / n,
        sum(bool(w & LIGHT) for w in words) / n,
        sum(not (w & NEUTRAL) for w in words) / n,
        sum(p not in {"", "solid", "plain", "none", "unknown"} for p in patterns) / n,
        min(len(items), 5) / 5.0,
        float("Footwear" in categories),
    ])


def _unit(vector: np.ndarray | None) -> np.ndarray | None:
    if vector is None:
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else None


@dataclass
class BanditModel:
    """Bayesian linear regression over outfit features, plus a visual taste memory."""

    precision: np.ndarray = field(default_factory=lambda: BanditModel.prior_precision())
    b: np.ndarray = field(default_factory=lambda: BanditModel.prior_precision() @ BanditModel.prior_mean())
    updates: int = 0
    # Running sums of liked / disliked outfit embeddings, per occasion group and "all".
    taste: dict[str, dict[str, list[float]]] = field(default_factory=dict)

    @staticmethod
    def prior_mean() -> np.ndarray:
        mean = np.zeros(DIM)
        for index, name in enumerate(SIGNALS):
            mean[index] = PRIOR_SIGNAL_WEIGHTS[name]
        return mean

    @staticmethod
    def prior_precision() -> np.ndarray:
        diagonal = np.full(DIM, PRIOR_PRECISION_STYLE)
        diagonal[: len(SIGNALS)] = PRIOR_PRECISION_SIGNALS
        return np.diag(diagonal)

    # -- features -----------------------------------------------------------------
    def visual_taste(self, embedding: np.ndarray | None, group: str) -> float:
        embedding = _unit(embedding)
        if embedding is None:
            return 0.0
        for key in (group, "all"):
            memory = self.taste.get(key) or {}
            liked = _unit(np.asarray(memory["pos"])) if memory.get("pos") else None
            disliked = _unit(np.asarray(memory["neg"])) if memory.get("neg") else None
            if liked is None and disliked is None:
                continue
            return float((embedding @ liked if liked is not None else 0.0)
                         - (embedding @ disliked if disliked is not None else 0.0))
        return 0.0

    def features(self, component_scores: dict[str, float], items: list[dict[str, Any]],
                 occasion: str, embedding: np.ndarray | None = None) -> np.ndarray:
        x = np.zeros(DIM)
        for index, name in enumerate(SIGNALS):
            x[index] = float(component_scores.get(name, 50.0)) / 100.0
        style = style_vector(items)
        start = len(SIGNALS)
        x[start:start + len(STYLES)] = style
        group = occasion_group(occasion)
        offset = start + len(STYLES) * (1 + OCCASION_GROUPS.index(group))
        x[offset:offset + len(STYLES)] = style
        x[-1] = self.visual_taste(embedding, group)
        return x

    # -- policy -------------------------------------------------------------------
    def mean(self) -> np.ndarray:
        return np.linalg.solve(self.precision, self.b)

    def sample_weights(self, rng: np.random.Generator) -> np.ndarray:
        covariance = NOISE_VARIANCE * EXPLORATION ** 2 * np.linalg.inv(self.precision)
        covariance = (covariance + covariance.T) / 2.0
        return rng.multivariate_normal(self.mean(), covariance, method="cholesky")

    def update(self, x: np.ndarray, reward: float, *, group: str | None = None,
               embedding: np.ndarray | None = None) -> None:
        self.precision = self.precision + np.outer(x, x)
        self.b = self.b + reward * x
        self.updates += 1
        embedding = _unit(embedding)
        if embedding is not None and group is not None and reward != REWARD["skip"]:
            side = "pos" if reward >= 0.5 else "neg"
            for key in (group, "all"):
                memory = self.taste.setdefault(key, {})
                current = np.asarray(memory.get(side) or np.zeros_like(embedding))
                memory[side] = (current + embedding).tolist()

    # -- persistence --------------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({
            "precision": self.precision.tolist(), "b": self.b.tolist(),
            "updates": self.updates, "taste": self.taste, "features": list(FEATURE_NAMES),
        })

    @classmethod
    def from_json(cls, payload: str) -> "BanditModel":
        data = json.loads(payload)
        if data.get("features") != list(FEATURE_NAMES):
            return cls()  # feature layout changed: start again from the prior
        return cls(np.asarray(data["precision"]), np.asarray(data["b"]),
                   int(data.get("updates", 0)), data.get("taste") or {})


# ---------------------------------------------------------------------------------
# Database-backed per-user models
# ---------------------------------------------------------------------------------

def load_model(user_id: str) -> BanditModel | None:
    from database import row

    record = row("SELECT state_json FROM bandit_models WHERE user_id=?", (user_id,))
    return BanditModel.from_json(record["state_json"]) if record else None


def save_model(user_id: str, model: BanditModel) -> None:
    from database import connection, utc_now

    with connection() as db:
        db.execute(
            """INSERT INTO bandit_models(user_id, state_json, updates, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json,
               updates=excluded.updates, updated_at=excluded.updated_at""",
            (user_id, model.to_json(), model.updates, utc_now()),
        )


def outfit_embedding(user_id: str, items: list[dict[str, Any]]) -> np.ndarray | None:
    from services.item_embeddings import embeddings_for_items

    try:
        vectors = list(embeddings_for_items(user_id, items).values())
    except Exception:  # embeddings are optional; ranking must not fail without them
        return None
    return np.mean(vectors, axis=0) if vectors else None


def rank(user_id: str, entries: list[dict[str, Any]], occasion: str,
         rng: np.random.Generator | None = None) -> bool:
    """Set ``entry["bandit_score"]`` (0–100) on each entry. Returns False when the user has
    no feedback yet, in which case the caller keeps the prior (hand-tuned) order."""
    model = load_model(user_id)
    if model is None or model.updates == 0:
        return False
    weights = model.sample_weights(rng or np.random.default_rng())
    for entry in entries:
        x = model.features(entry["component_scores"], entry["items"], occasion,
                           outfit_embedding(user_id, entry["items"]))
        entry["bandit_score"] = round(float(x @ weights) * 100.0, 1)
    return True


def learn_from_feedback(user_id: str, recommendation_id: str | None, action: str,
                        rating: int | None = None) -> bool:
    """Update the user's bandit from one reaction to a shown recommendation."""
    from database import row
    from services.wardrobe_service import list_items

    reward = reward_for(action, rating)
    if reward is None or not recommendation_id:
        return False
    record = row(
        "SELECT occasion, item_ids, component_scores FROM recommendations "
        "WHERE recommendation_id=? AND user_id=?",
        (recommendation_id, user_id),
    )
    if record is None:
        return False
    item_ids = set(json.loads(record["item_ids"]))
    items = [item for item in list_items(user_id) if item["item_id"] in item_ids]
    if not items:
        return False
    model = load_model(user_id) or BanditModel()
    embedding = outfit_embedding(user_id, items)
    x = model.features(json.loads(record["component_scores"]), items, record["occasion"], embedding)
    model.update(x, reward, group=occasion_group(record["occasion"]), embedding=embedding)
    save_model(user_id, model)
    return True


def describe(user_id: str, top: int = 8) -> dict[str, Any]:
    """What this user's model has learned so far (largest moves away from the prior)."""
    model = load_model(user_id)
    if model is None:
        return {"updates": 0, "learned": []}
    shift = model.mean() - BanditModel.prior_mean()
    order = np.argsort(-np.abs(shift))[:top]
    return {
        "updates": model.updates,
        "learned": [{"feature": FEATURE_NAMES[i], "weight_change": round(float(shift[i]), 3)}
                    for i in order if abs(shift[i]) > 1e-4],
    }
