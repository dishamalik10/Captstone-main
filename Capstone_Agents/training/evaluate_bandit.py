"""Offline evaluation of the personalised contextual-bandit ranker with simulated users.

There is no real feedback data yet, so — as is standard for bandit recommenders — the
policies are compared on simulated users whose hidden taste is known. Each simulated user
owns a synthetic wardrobe; every round they are dressing for a random occasion, the policy
shows one outfit built by AURA's real candidate generator and scored by AURA's real rule
functions, and the user likes or dislikes it according to their hidden taste.

Policies compared (same wardrobes, occasions and random draws):
* ``hand_tuned``  – the original fixed-weight ranker (the bandit's prior, never updated).
* ``greedy``      – learns from feedback but always shows the current best guess.
* ``thompson``    – AURA's policy: learns from feedback and explores via posterior sampling.

Run from Capstone_Agents:  python -m training.evaluate_bandit
Writes model_artifacts/bandit_evaluation.json and model_artifacts/bandit_learning_curve.svg.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from services.bandit_ranker import BanditModel, REWARD, occasion_group, style_vector
from services.recommendation_service import (
    _candidates, color_score, fabric_weather_score, occasion_score,
    pattern_coordination_score, silhouette_balance_score, weather_score,
)

ROUNDS = 40
SEEDS = 15
OCCASIONS = ("date", "party", "meeting", "office", "casual", "travel", "college", "wedding")
OUT_DIR = Path(__file__).resolve().parent.parent / "model_artifacts"

CATALOGUE = {
    "Top": [("T-shirt", "t-shirt"), ("Shirt", "shirt"), ("Sweater", "sweater"), ("Blouse", "blouse")],
    "Bottom": [("Trousers", "trousers"), ("Jeans", "jeans"), ("Skirt", "skirt")],
    "Dress": [("Dress", "dress")],
    "Outerwear": [("Jacket", "jacket"), ("Blazer", "blazer")],
    "Footwear": [("Sneakers", "sneakers"), ("Heels", "heels"), ("Boots", "boots")],
}
COLOURS = ["black", "white", "navy", "beige", "grey", "brown", "red", "dark red",
           "blue", "light blue", "green", "pink", "yellow", "olive"]
PATTERNS = ["solid", "solid", "solid", "striped", "floral", "checked"]
WARDROBE_SHAPE = {"Top": 5, "Bottom": 3, "Dress": 2, "Outerwear": 2, "Footwear": 2}

# Hidden tastes: weights on style descriptors, globally and for evening / formal occasions.
# Order matches bandit_ranker.STYLES:
# has_dress, layered, dark, light, colourful, patterned, piece_count, has_footwear
PERSONAS = {
    "bold_evening": {"all": [0, 0, 0.5, -0.5, 0, 0, 0, 0],
                     "evening": [2.0, 0, 2.0, -1.5, 0, 0, 0, 0]},
    "minimal_light": {"all": [0, 0, -0.5, 2.0, -2.0, -1.5, -0.5, 0]},
    "layer_lover": {"all": [-1.0, 2.5, 0, 0, 0, 0, 0.5, 0],
                    "formal": [0, 1.0, 1.0, 0, -0.5, 0, 0, 0]},
    "colour_pop": {"all": [0, 0, -1.0, -0.5, 2.5, 1.5, 0, 0]},
}


def _prototypes(rng: np.random.Generator) -> dict[tuple[str, str], np.ndarray]:
    """Shared visual 'look' per (category, colour) so taste can generalise across items."""
    return {(category, colour): rng.normal(size=512)
            for category in CATALOGUE for colour in COLOURS}


def make_wardrobe(rng: np.random.Generator, prototypes) -> list[dict]:
    items = []
    for category, count in WARDROBE_SHAPE.items():
        for index in range(count):
            subcategory, group = CATALOGUE[category][rng.integers(len(CATALOGUE[category]))]
            colour = COLOURS[rng.integers(len(COLOURS))]
            embedding = prototypes[(category, colour)] + 0.5 * rng.normal(size=512)
            items.append({
                "item_id": f"{category}-{index}", "category": category, "subcategory": subcategory,
                "garment_group": group, "color_name": colour.title(),
                "pattern": PATTERNS[rng.integers(len(PATTERNS))], "fabric": None, "fit": None,
                "style_tags": [], "occasion_tags": [], "seasons": [], "embedding": embedding,
            })
    return items


def component_scores(items, occasion, temperature, rng_key: int) -> dict[str, float]:
    jitter = np.random.default_rng(rng_key).normal()
    return {
        "color": color_score(items), "occasion": occasion_score(items, occasion),
        "weather": weather_score(items, temperature, "Clear"), "preference": 70.0,
        "feedback": 50.0, "learned_preference": 50.0, "novelty": 100.0, "trend": 50.0,
        "pattern": pattern_coordination_score(items), "silhouette": silhouette_balance_score(items),
        "fabric_weather": fabric_weather_score(items, temperature, "Clear"),
        # Stand-in for the learned compatibility model (no images in simulation).
        "learned_compatibility": float(np.clip(50 + 15 * jitter, 0, 100)),
    }


def like_probability(persona: dict, items, occasion: str, favourite: np.ndarray, embedding) -> float:
    style = style_vector(items)
    utility = float(np.dot(persona["all"], style))
    group = occasion_group(occasion)
    if group in persona:
        utility += float(np.dot(persona[group], style))
    utility += 1.0 * float(embedding @ favourite / (np.linalg.norm(embedding) * np.linalg.norm(favourite)))
    return 1.0 / (1.0 + math.exp(-(2.0 * utility - 0.5)))


def run_user(persona_name: str, seed: int) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed)
    prototypes = _prototypes(np.random.default_rng(10_000 + seed))
    wardrobe = make_wardrobe(rng, prototypes)
    persona = {key: np.asarray(value) for key, value in PERSONAS[persona_name].items()}
    persona.setdefault("all", np.zeros(8))
    favourite = prototypes[("Top", COLOURS[rng.integers(len(COLOURS))])]
    all_outfits = _candidates(wardrobe, seed=seed)

    models = {"greedy": BanditModel(), "thompson": BanditModel()}
    prior = BanditModel()
    policy_rng = np.random.default_rng(seed + 1)
    curves = {name: [] for name in ("hand_tuned", "greedy", "thompson", "oracle")}
    for round_index in range(ROUNDS):
        occasion = OCCASIONS[rng.integers(len(OCCASIONS))]
        temperature = float(rng.uniform(16, 32))
        # Like the app, every round ranks every outfit the wardrobe can make.
        outfits = all_outfits
        embeddings = [np.mean([item["embedding"] for item in outfit], axis=0) for outfit in outfits]
        scores = [component_scores(outfit, occasion, temperature, seed * 1000 + round_index * 50 + k)
                  for k, outfit in enumerate(outfits)]
        probability = [like_probability(persona, outfit, occasion, favourite, emb)
                       for outfit, emb in zip(outfits, embeddings)]
        curves["oracle"].append(max(probability))
        group = occasion_group(occasion)

        x_prior = [prior.features(s, o, occasion, e) for s, o, e in zip(scores, outfits, embeddings)]
        chosen = int(np.argmax([x @ prior.mean() for x in x_prior]))
        curves["hand_tuned"].append(probability[chosen])

        for name, model in models.items():
            xs = [model.features(s, o, occasion, e) for s, o, e in zip(scores, outfits, embeddings)]
            weights = model.sample_weights(policy_rng) if name == "thompson" else model.mean()
            chosen = int(np.argmax([x @ weights for x in xs]))
            curves[name].append(probability[chosen])
            liked = rng.random() < probability[chosen]
            reward = REWARD["like"] if liked else REWARD["dislike"]
            model.update(xs[chosen], reward, group=group, embedding=embeddings[chosen])
    return curves


def _svg(curves: dict[str, list[float]], path: Path) -> None:
    width, height, pad = 720, 380, 48
    colours = {"oracle": "#9ca3af", "hand_tuned": "#b45309", "greedy": "#2563eb", "thompson": "#16a34a"}
    labels = {"oracle": "Best possible", "hand_tuned": "Hand-tuned ranker (before)",
              "greedy": "Bandit, no exploration", "thompson": "Bandit + Thompson sampling (AURA)"}
    low, high = 0.3, 1.0

    def point(i: int, value: float) -> str:
        x = pad + i * (width - 2 * pad) / (ROUNDS - 1)
        y = height - pad - (value - low) / (high - low) * (height - 2 * pad)
        return f"{x:.1f},{y:.1f}"

    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'font-family="sans-serif" font-size="12"><rect width="100%" height="100%" fill="white"/>']
    for tick in (0.4, 0.6, 0.8, 1.0):
        y = point(0, tick).split(",")[1]
        lines.append(f'<line x1="{pad}" x2="{width - pad}" y1="{y}" y2="{y}" stroke="#e5e7eb"/>'
                     f'<text x="{pad - 8}" y="{y}" text-anchor="end" dy="4" fill="#6b7280">{tick:.0%}</text>')
    for name in ("oracle", "hand_tuned", "greedy", "thompson"):
        smooth = np.convolve(curves[name], np.ones(5) / 5, mode="same")
        smooth[:2], smooth[-2:] = curves[name][:2], curves[name][-2:]
        points = " ".join(point(i, v) for i, v in enumerate(smooth))
        dash = ' stroke-dasharray="4 4"' if name == "oracle" else ""
        lines.append(f'<polyline fill="none" stroke="{colours[name]}" stroke-width="2.5"{dash} points="{points}"/>')
    for index, name in enumerate(("thompson", "greedy", "hand_tuned", "oracle")):
        y = pad + 6 + index * 18
        lines.append(f'<rect x="{width - 300}" y="{y - 9}" width="14" height="4" fill="{colours[name]}"/>'
                     f'<text x="{width - 280}" y="{y}" fill="#374151">{labels[name]}</text>')
    lines.append(f'<text x="{width / 2}" y="{height - 10}" text-anchor="middle" fill="#374151">'
                 f'Feedback round</text><text x="14" y="{height / 2}" fill="#374151" '
                 f'transform="rotate(-90 14 {height / 2})" text-anchor="middle">Chance the user likes the shown outfit</text>')
    lines.append(f'<text x="{pad}" y="22" font-size="14" font-weight="bold" fill="#111827">'
                 f'Personalised ranking learns from feedback ({len(PERSONAS)} simulated tastes × {SEEDS} users)</text></svg>')
    path.write_text("\n".join(lines), "utf-8")


def main() -> None:
    per_persona: dict[str, dict[str, list[float]]] = {}
    pooled = {name: np.zeros(ROUNDS) for name in ("hand_tuned", "greedy", "thompson", "oracle")}
    for persona in PERSONAS:
        runs = [run_user(persona, seed) for seed in range(SEEDS)]
        per_persona[persona] = {
            name: np.mean([run[name] for run in runs], axis=0).tolist() for name in pooled
        }
        for name in pooled:
            pooled[name] += np.asarray(per_persona[persona][name]) / len(PERSONAS)

    def summary(curve) -> dict[str, float]:
        curve = np.asarray(curve)
        return {"first_5_rounds": round(float(curve[:5].mean()), 3),
                "last_10_rounds": round(float(curve[-10:].mean()), 3),
                "overall": round(float(curve.mean()), 3)}

    regret = {name: round(float(np.sum(pooled["oracle"] - pooled[name])), 2)
              for name in ("hand_tuned", "greedy", "thompson")}
    report = {
        "setup": {"rounds": ROUNDS, "users_per_persona": SEEDS, "personas": list(PERSONAS),
                  "candidates_per_round": "all outfits the wardrobe can make (as in the app)",
                  "metric": "probability the simulated user likes the top outfit"},
        "summary": {name: summary(pooled[name]) for name in pooled},
        "cumulative_regret": regret,
        "per_persona_last_10": {persona: {name: round(float(np.mean(curves[name][-10:])), 3)
                                          for name in curves}
                                for persona, curves in per_persona.items()},
        "curves": {name: [round(v, 4) for v in pooled[name].tolist()] for name in pooled},
        "caveat": "Simulated users with synthetic wardrobes and a stand-in compatibility score; "
                  "this shows the learning mechanism works, not real-user satisfaction.",
    }
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "bandit_evaluation.json").write_text(json.dumps(report, indent=2), "utf-8")
    _svg({name: pooled[name].tolist() for name in pooled}, OUT_DIR / "bandit_learning_curve.svg")
    print(json.dumps({k: report[k] for k in ("summary", "cumulative_regret", "per_persona_last_10")}, indent=2))


if __name__ == "__main__":
    main()
