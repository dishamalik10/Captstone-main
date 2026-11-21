import numpy as np
import pytest


def test_saved_weights_reload_into_a_fresh_model_with_identical_scores(tmp_path):
    """Every trained variable (including the transformer blocks) must survive save/load.

    Regression: blocks held in a list of dicts were silently left out of .weights.h5,
    so a reloaded model scored with random block weights.
    """
    pytest.importorskip("keras")
    from ml.outfit_compat import EMBEDDING_DIM, MAX_ITEMS, build_model, predict_scores

    config = {"num_layers": 2, "model_dim": 32, "ff_dim": 32, "num_heads": 2}
    rng = np.random.default_rng(0)
    features = rng.normal(size=(3, MAX_ITEMS, EMBEDDING_DIM)).astype(np.float32)
    categories = np.zeros((3, MAX_ITEMS), dtype=np.int32)
    categories[:, :4] = [1, 2, 4, 6]

    trained = build_model(config)
    expected = predict_scores(trained, features, categories)
    weights = tmp_path / "outfit_compat.weights.h5"
    trained.save_weights(str(weights))

    reloaded = build_model(config)  # different random initialisation until weights load
    reloaded.load_weights(str(weights))

    assert len(reloaded.weights) == len(trained.weights)
    for original, restored in zip(trained.weights, reloaded.weights):
        np.testing.assert_array_equal(np.asarray(original), np.asarray(restored), err_msg=original.path)
    np.testing.assert_allclose(predict_scores(reloaded, features, categories), expected, atol=1e-6)


def test_stylist_response_schema_has_no_length_limits():
    """llama.cpp unrolls maxLength/maxItems into deeply nested grammar rules; at 420 chars that
    exceeded its recursion limit and crashed the whole backend process (segfault) on the first
    stylist selection. Length is enforced by parse_answer instead."""
    from ml.stylist_prompt import RESPONSE_SCHEMA, parse_answer

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)

    assert not {"maxLength", "minLength", "maxItems", "minItems"} & set(keys(RESPONSE_SCHEMA))
    choice, reason = parse_answer('{"choice": 2, "reason": "' + "a" * 1000 + '"}', 3)
    assert choice == 2 and len(reason) == 420
