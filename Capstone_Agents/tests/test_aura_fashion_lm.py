import pytest

from services.fashion_contract import (
    InvalidFashionResponse,
    parse_json_object,
    validate_explanation_json,
    validate_owned_outfit,
)


def wardrobe():
    return [
        {"item_id": "shirt-1", "category": "Top", "available": True},
        {"item_id": "trouser-1", "category": "Bottom", "available": True},
        {"item_id": "shoe-1", "category": "Footwear", "available": True},
        {"item_id": "coat-1", "category": "Outerwear", "available": False},
    ]


def test_json_parser_handles_nested_objects_and_quoted_braces():
    assert parse_json_object('```json\n{"x":{"message":"brace } is text"}}\n```') == {
        "x": {"message": "brace } is text"}
    }


@pytest.mark.parametrize(
    "item_ids",
    [
        ["shirt-1", "trouser-1", "shirt-1"],
        ["shirt-1", "trouser-1", "made-up"],
        ["shirt-1", "trouser-1", "shoe-1", "coat-1"],
        ["shirt-1", "trouser-1"],
    ],
)
def test_owned_outfit_validator_rejects_duplicate_unknown_unavailable_or_missing_shoes(item_ids):
    with pytest.raises(InvalidFashionResponse):
        validate_owned_outfit(item_ids, wardrobe())


def test_language_model_can_explain_but_cannot_change_ranked_item_ids():
    selected = [wardrobe()[0], wardrobe()[1], wardrobe()[2]]
    raw = (
        '{"item_ids":["shirt-1","trouser-1","shoe-1"],'
        '"explanation":"The recorded pieces form a complete look."}'
    )
    assert validate_explanation_json(raw, selected, wardrobe()) == "The recorded pieces form a complete look."
    changed = raw.replace("shoe-1", "invented")
    with pytest.raises(InvalidFashionResponse):
        validate_explanation_json(changed, selected, wardrobe())


def test_scratch_model_takes_explainer_precedence_and_receives_owned_wardrobe(monkeypatch):
    from services import recommendation_explainer as explainer

    selected = [wardrobe()[0], wardrobe()[1], wardrobe()[2]]
    rec = {
        "recommendation_id": "rec-1",
        "item_ids": [item["item_id"] for item in selected],
        "items": selected,
        "compatibility_score": 80,
        "component_scores": {"color": 80, "occasion": 80, "weather": 80},
    }
    seen = {}
    monkeypatch.setattr(explainer, "fashion_lm_info", lambda: {"weights_present": True})

    def scratch(items, owned, **kwargs):
        seen["wardrobe"] = owned
        return "The recorded pieces form a complete look."

    monkeypatch.setattr(explainer, "explain_outfit", scratch)
    monkeypatch.setattr(explainer, "get_model_info", lambda: pytest.fail("Must not fall through to Qwen"))
    result = explainer.explain_recommendations(
        [rec], occasion="casual", temperature=20, condition="Clear", wardrobe=wardrobe()
    )
    assert seen["wardrobe"] == wardrobe()
    assert result["recommendations"][0]["item_ids"] == rec["item_ids"]
    assert result["recommendations"][0]["explanation_source"] == "aura_fashion_lm"


def test_color_ranker_distinguishes_analogous_and_complementary_palettes():
    from services.recommendation_service import color_score

    complementary = [{"color_name": "orange"}, {"color_name": "blue"}]
    analogous = [{"color_name": "teal"}, {"color_name": "blue"}]
    assert color_score(complementary) > color_score(analogous)
    assert color_score(complementary) >= 90


def test_fashion_model_load_requires_local_scratch_weights_and_valid_architecture(tmp_path, monkeypatch):
    import sys
    import types
    from services import aura_fashion_lm as service

    class Tokenizer:
        eos_token_id = 2
        pad_token_id = 0

        def __len__(self):
            return 8000

    class Parameter:
        def numel(self):
            return 5_240_320

    class Model:
        config = types.SimpleNamespace(vocab_size=8000, n_layer=4, n_embd=256, n_head=4)

        def parameters(self):
            return [Parameter()]

        def to(self, **kwargs):
            return self

        def eval(self):
            return self

    def from_pretrained(path, **kwargs):
        assert path == str(tmp_path)
        assert kwargs.get('local_files_only') is True
        return Tokenizer() if 'use_fast' in kwargs else Model()

    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
        float16='float16', float32='float32',
    )
    fake_transformers = types.SimpleNamespace(
        AutoTokenizer=types.SimpleNamespace(from_pretrained=from_pretrained),
        AutoModelForCausalLM=types.SimpleNamespace(from_pretrained=from_pretrained),
    )
    monkeypatch.setitem(sys.modules, 'torch', fake_torch)
    monkeypatch.setitem(sys.modules, 'transformers', fake_transformers)
    monkeypatch.setattr(service, 'settings', types.SimpleNamespace(fashion_lm_path=tmp_path))
    monkeypatch.setattr(service, '_model', None)
    monkeypatch.setattr(service, '_tokenizer', None)
    monkeypatch.setattr(service, '_torch', None)
    monkeypatch.setattr(service, '_device', None)
    monkeypatch.setattr(service, '_last_error', None)
    service.load_model()
    assert service.model_info()['ready'] is True


def test_blind_human_evaluation_sheet_separates_response_key(tmp_path):
    import csv
    import json
    from scripts.make_blind_styling_rating import create_sheet

    pairs = tmp_path / 'pairs.jsonl'
    pairs.write_text(json.dumps({
        'case_id': 'scenario-1', 'occasion': 'office', 'temperature_c': 20,
        'wardrobe': [{'item_id': 'top-1'}], 'selected_item_ids': ['top-1'],
        'baseline_explanation': 'Rule explanation',
        'scratch_explanation': 'Model explanation',
    }) + '\n')
    ratings = tmp_path / 'ratings.csv'
    key_path = create_sheet(pairs, ratings, seed=7)
    with ratings.open(newline='') as stream:
        row = next(csv.DictReader(stream))
    key = json.loads(key_path.read_text())['mapping']['scenario-1']
    assert {row['response_a'], row['response_b']} == {'Rule explanation', 'Model explanation'}
    assert key['A'] in {'scratch', 'deterministic_baseline'}
    assert key['B'] in {'scratch', 'deterministic_baseline'}
    assert key['A'] != key['B']


def test_recommend_format_training_row_becomes_backend_explain_contract():
    import json

    from ml.explain_prompt import CATEGORY, build_request, convert_training_row

    owned = [
        {"item_id": "top_014", "name": "cream linen shirt", "type": "top", "color": "cream"},
        {"item_id": "bottom_022", "name": "navy trousers", "type": "bottom", "color": "navy"},
        {"item_id": "shoe_008", "name": "brown loafers", "type": "shoes", "color": "brown"},
        {"item_id": "bag_003", "name": "tan tote", "type": "bag"},
    ]
    row = {
        "id": 7, "category": CATEGORY,
        "input": json.dumps({"occasion": "office", "weather": "mild", "wardrobe": owned}),
        "output": json.dumps({
            "outfit": [{"item_id": "top_014"}, {"item_id": "bottom_022"}, {"item_id": "shoe_008"}],
            "rationale": "Cream and navy keep the look calm.",
        }),
    }
    converted = convert_training_row(row)
    assert converted is not None and converted["category"] == CATEGORY
    request = json.loads(converted["input"])
    assert "available_wardrobe" not in request and "wardrobe" not in request
    assert [item["category"] for item in request["selected_outfit"]] == ["Top", "Bottom", "Footwear"]

    backend_items = [
        {"item_id": "top_014", "category": "Top", "subcategory": "cream linen shirt", "color_name": "cream"},
        {"item_id": "bottom_022", "category": "Bottom", "subcategory": "navy trousers", "color_name": "navy"},
        {"item_id": "shoe_008", "category": "Footwear", "subcategory": "brown loafers", "color_name": "brown"},
    ]
    # The training target passes the exact validator the backend applies to model output.
    assert validate_explanation_json(converted["output"], backend_items, backend_items) == (
        "Cream and navy keep the look calm."
    )
    # Same outfit through the backend path yields the same serialized request shape.
    backend_request = json.loads(build_request(backend_items, occasion="office", weather="mild"))
    assert backend_request == request


def test_rows_without_a_usable_outfit_or_rationale_are_not_converted():
    from ml.explain_prompt import convert_training_row

    assert convert_training_row({"input": "{}", "output": '{"rationale": "x"}'}) is None
    assert convert_training_row({"input": "not json", "output": "plain text answer"}) is None
    assert convert_training_row({
        "input": '{"wardrobe": []}',
        "output": '{"outfit": [{"item_id": "ghost"}], "rationale": "x"}',
    }) is None
