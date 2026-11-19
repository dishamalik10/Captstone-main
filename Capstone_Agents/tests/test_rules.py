from services.recommendation_service import (
    color_score,
    fabric_weather_score,
    occasion_score,
    pattern_coordination_score,
    preference_score,
    silhouette_balance_score,
    weather_score,
)
from services.vision_service import map_category
from services.compatibility_service import learned_compatibility_score


def item(
    subcategory: str,
    color: str,
    category: str,
    **extra,
):
    return {
        "subcategory": subcategory,
        "color_name": color,
        "category": category,
        "garment_group": extra.get("garment_group", ""),
        "style_tags": extra.get("style_tags", []),
        "fit": extra.get("fit"),
        "pattern": extra.get("pattern"),
        "fabric": extra.get("fabric"),
    }


def test_hm_category_mapping():
    assert map_category("Blazer", "Garment Upper body") == "Outerwear"
    assert map_category("Dress", "Dresses Ladies") == "Dress"
    assert map_category("Sneakers", "Shoes") == "Footwear"
    assert map_category("Trousers", "Garment Lower body") == "Bottom"
    assert map_category("Trousers", "Jersey Fancy") == "Bottom"
    assert map_category("Underwear bottom", "Swimwear") == "Bottom"
    assert map_category("T-shirt", "Garment Upper body") == "Top"


def test_neutral_palette_scores_well():
    outfit = [
        item("Shirt", "White", "Top"),
        item("Trousers", "Black", "Bottom"),
        item("Loafers", "Brown", "Footwear"),
    ]
    assert color_score(outfit) >= 85


def test_formal_outfit_beats_casual_outfit_for_interview():
    formal = [
        item("Shirt", "White", "Top"),
        item("Trousers", "Black", "Bottom"),
        item("Loafers", "Brown", "Footwear"),
    ]
    casual = [
        item("T-shirt", "Red", "Top"),
        item("Shorts", "Blue", "Bottom"),
        item("Sneakers", "White", "Footwear"),
    ]
    assert occasion_score(formal, "interview") > occasion_score(casual, "interview")


def test_hot_weather_penalizes_heavy_outerwear():
    light = [item("T-shirt", "White", "Top"), item("Shorts", "Blue", "Bottom")]
    heavy = [item("Wool Coat", "Black", "Outerwear")]
    assert weather_score(light, 35, "Clear") > weather_score(heavy, 35, "Clear")


def test_saved_color_preferences_affect_score():
    preferences = {
        "preferred_colors": ["Navy"],
        "avoided_colors": ["Orange"],
        "preferred_styles": [],
        "disliked_styles": [],
        "fit_preference": None,
    }
    liked = [item("Shirt", "Navy", "Top")]
    avoided = [item("Shirt", "Orange", "Top")]
    assert preference_score(liked, preferences) > preference_score(avoided, preferences)


def test_color_theory_scores_analogous_and_complementary_pairs():
    complementary = [item("Top", "Orange", "Top"), item("Trousers", "Blue", "Bottom")]
    analogous = [item("Top", "Teal", "Top"), item("Trousers", "Blue", "Bottom")]
    assert color_score(complementary) >= 90
    assert color_score(complementary) > color_score(analogous)


def test_one_print_with_solid_items_is_preferred_to_conflicting_prints():
    anchored = [
        item("Printed Shirt", "White", "Top", pattern="Floral"),
        item("Trousers", "Black", "Bottom", pattern="Solid"),
    ]
    conflicting = [
        item("Printed Shirt", "White", "Top", pattern="Floral"),
        item("Checked Trousers", "Black", "Bottom", pattern="Checkered"),
    ]
    assert pattern_coordination_score(anchored) > pattern_coordination_score(conflicting)


def test_silhouette_and_fabric_weather_rules_use_recorded_attributes():
    balanced = [
        item("Oversized Shirt", "White", "Top", fit="Oversized"),
        item("Trousers", "Black", "Bottom", fit="Slim"),
    ]
    hot = [item("Linen Shirt", "White", "Top", fabric="Linen")]
    wool = [item("Wool Coat", "Black", "Outerwear", fabric="Wool")]
    assert silhouette_balance_score(balanced) >= 90
    assert fabric_weather_score(hot, 34, "Clear") > fabric_weather_score(wool, 34, "Clear")
    assert fabric_weather_score(wool, 5, "Clear") > fabric_weather_score(hot, 5, "Clear")


def test_palette_analysis_labels_warm_cool_mix_without_claiming_quality():
    from services.fashion_analysis import analyze_outfit

    analysis = analyze_outfit(
        [item("Top", "Red", "Top"), item("Bottom", "Blue", "Bottom")],
        "casual", 22, "Clear",
    )
    assert analysis["palette"]["temperature_tones"] == "warm_and_cool"
    assert "not a calibrated quality score" in analysis["palette"]["note"]


def test_shift15m_model_scores_supported_outfit_pair():
    score = learned_compatibility_score([
        item("Shirt", "White", "Top"),
        item("Trousers", "Black", "Bottom"),
    ])
    assert score is not None
    assert 0 <= score <= 100
