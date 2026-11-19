from services.agentic_recommender import critique_candidate, plan_recommendation


def test_planner_selects_context_and_memory_tools():
    plan = plan_recommendation("meeting", 18, "Rain", has_feedback=True)

    assert plan["intent"] == "outfit_recommendation"
    assert "weather_context" in plan["tools"]
    assert "preference_memory" in plan["tools"]
    assert plan["max_revision_rounds"] == 1


def test_critic_rejects_incomplete_or_unowned_outfits():
    top = {"item_id": "top-1", "category": "Top"}
    incomplete = critique_candidate([top], {"top-1"}, 80, 80)
    unowned = critique_candidate(
        [top, {"item_id": "bottom-2", "category": "Bottom"}],
        {"top-1"},
        80,
        80,
    )

    assert incomplete["passed"] is False
    assert "incomplete_base_outfit" in incomplete["issues"]
    assert unowned["passed"] is False
    assert "contains_unowned_item" in unowned["issues"]
