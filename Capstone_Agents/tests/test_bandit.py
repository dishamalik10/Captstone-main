import numpy as np

from services.bandit_ranker import (
    RULE_WEIGHTS, COMPAT_WEIGHT, REWARD, BanditModel, FEATURE_NAMES, reward_for,
)

SCORES = {name: 60.0 for name in (*RULE_WEIGHTS, "learned_compatibility")}
DARK_DRESS = [{"category": "Dress", "subcategory": "Dress", "color_name": "Black"}]
LIGHT_SEPARATES = [
    {"category": "Top", "subcategory": "Sweater", "color_name": "White"},
    {"category": "Bottom", "subcategory": "Trousers", "color_name": "Beige"},
]


def test_prior_reproduces_hand_tuned_ranker():
    scores = {**SCORES, "color": 90.0, "learned_compatibility": 30.0}
    model = BanditModel()
    x = model.features(scores, LIGHT_SEPARATES, "date")
    rule_total = sum(scores[name] * weight for name, weight in RULE_WEIGHTS.items())
    expected = (rule_total * (1 - COMPAT_WEIGHT) + scores["learned_compatibility"] * COMPAT_WEIGHT) / 100
    assert abs(float(x @ model.mean()) - expected) < 1e-9


def test_feedback_moves_ranking_toward_liked_style_for_that_occasion():
    model = BanditModel()
    dress, separates = (model.features(SCORES, items, "date") for items in (DARK_DRESS, LIGHT_SEPARATES))
    assert abs(float((dress - separates) @ model.mean())) < 0.05  # prior barely separates them
    for _ in range(4):
        model.update(dress, REWARD["like"])
        model.update(separates, REWARD["dislike"])
    assert float(dress @ model.mean()) > float(separates @ model.mean())
    index = FEATURE_NAMES.index("evening:has_dress")
    assert model.mean()[index] > BanditModel.prior_mean()[index]


def test_visual_taste_uses_liked_embeddings():
    model = BanditModel()
    liked, other = np.ones(512), -np.ones(512)
    model.update(model.features(SCORES, DARK_DRESS, "party", liked), REWARD["like"],
                 group="evening", embedding=liked)
    assert model.visual_taste(liked, "evening") > 0.9
    assert model.visual_taste(other, "evening") < -0.9
    # Falls back to all-occasion taste for an occasion group with no feedback yet.
    assert model.visual_taste(liked, "formal") > 0.9


def test_thompson_sampling_explores_but_centres_on_posterior():
    model = BanditModel()
    rng = np.random.default_rng(0)
    samples = np.array([model.sample_weights(rng) for _ in range(400)])
    assert samples.std(axis=0).min() > 0
    assert np.allclose(samples.mean(axis=0), model.mean(), atol=0.05)


def test_state_round_trips_and_rewards_are_ordered():
    model = BanditModel()
    model.update(model.features(SCORES, DARK_DRESS, "date", np.ones(512)), 1.0,
                 group="evening", embedding=np.ones(512))
    restored = BanditModel.from_json(model.to_json())
    assert restored.updates == 1 and np.allclose(restored.mean(), model.mean())
    assert reward_for("wear") > reward_for("save") > reward_for("like") > reward_for("skip") > reward_for("dislike")
    assert reward_for("rate", 5) == 1.0 and reward_for("rate", 1) == 0.0 and reward_for("rate") is None
