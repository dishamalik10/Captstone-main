import pytest

from services.recommendation_service import weather_score
from services.season_classifier import (
    classify_seasons,
    effective_seasons,
    season_label,
    target_season,
)


def item(subcategory, category, **extra):
    return {"subcategory": subcategory, "category": category, "garment_group": "",
            "color_name": "Black", "style_tags": [], **extra}


@pytest.mark.parametrize("subcategory,expected", [
    ("Sweater", "Winter"),
    ("Coat", "Winter"),
    ("Hoodie", "Winter"),
    ("Boots", "Winter"),
    ("Shorts", "Summer"),
    ("T-shirt", "Summer"),
    ("Sandals", "Summer"),
    ("Vest top", "Summer"),
    ("Trousers", "All-season"),
    ("Shirt", "All-season"),
    ("Button-down shirt", "All-season"),
    ("Sneakers", "All-season"),
])
def test_classifies_garment_type(subcategory, expected):
    assert season_label(classify_seasons(item(subcategory, "Top"))) == expected


def test_fabric_drives_season():
    assert season_label(classify_seasons(item("Trousers", "Bottom", fabric="Linen"))) == "Summer"
    assert season_label(classify_seasons(item("Trousers", "Bottom", fabric="Wool"))) == "Winter"


def test_user_season_overrides_classifier():
    sweater = item("Sweater", "Top", seasons=["summer"])
    assert season_label(effective_seasons(sweater)) == "Summer"


@pytest.mark.parametrize("temperature,expected", [
    (38, "Summer"), (26, "Summer"), (25, "Mild"), (20, "Mild"), (16, "Winter"), (2, "Winter"),
    (None, "Mild"),
])
def test_target_season(temperature, expected):
    assert target_season(temperature) == expected


def test_winter_clothes_rejected_in_heat():
    outfit = [item("Sweater", "Top"), item("Trousers", "Bottom"), item("Sneakers", "Footwear")]
    assert weather_score(outfit, 34, "Clear") < 45  # below the critic's weather floor


def test_summer_clothes_rejected_in_cold():
    outfit = [item("Shirt", "Top"), item("Shorts", "Bottom"), item("Sandals", "Footwear")]
    assert weather_score(outfit, 5, "Clear") < 45


def test_tshirt_under_winter_coat_is_fine_in_cold():
    outfit = [item("T-shirt", "Top"), item("Trousers", "Bottom"),
              item("Coat", "Outerwear"), item("Boots", "Footwear")]
    assert weather_score(outfit, 5, "Clear") >= 45


def test_season_appropriate_outfits_pass():
    summer = [item("T-shirt", "Top"), item("Shorts", "Bottom"), item("Sandals", "Footwear")]
    winter = [item("Sweater", "Top"), item("Trousers", "Bottom"), item("Boots", "Footwear")]
    assert weather_score(summer, 34, "Clear") >= 45
    assert weather_score(winter, 5, "Clear") >= 45


def test_mild_weather_allows_both():
    sweater = [item("Sweater", "Top"), item("Trousers", "Bottom"), item("Sneakers", "Footwear")]
    tee = [item("T-shirt", "Top"), item("Shorts", "Bottom"), item("Sneakers", "Footwear")]
    assert weather_score(sweater, 20, "Clear") >= 45
    assert weather_score(tee, 20, "Clear") >= 45
