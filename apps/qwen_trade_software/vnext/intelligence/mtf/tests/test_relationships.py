from vnext.intelligence.mtf.relationships import classify_relationship


def test_child_pullback_does_not_invalidate_parent():
    result = classify_relationship({"direction": "bullish", "state": "trend"}, {"direction": "bearish", "state": "moving"})
    assert result["relationship"] == "PULLBACK"


def test_transition_is_warning_before_parent_confirms():
    result = classify_relationship({"direction": "bullish", "state": "trend"}, {"direction": "bearish", "state": "choch"})
    assert result["relationship"] == "TRANSITION_WARNING"
