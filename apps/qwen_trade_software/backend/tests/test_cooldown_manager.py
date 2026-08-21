from cooldown_manager import VolatilityDetector


def test_five_dollar_one_minute_move_triggers_once():
    detector = VolatilityDetector()
    assert detector.observe("XAU", 0, 4500) is None
    event = detector.observe("XAU", 59, 4505)
    assert event and event["window_seconds"] == 60
    assert detector.observe("XAU", 60, 4505.2) is None


def test_seven_dollar_two_minute_move_triggers():
    detector = VolatilityDetector()
    assert detector.observe("XAU", 0, 4500) is None
    event = detector.observe("XAU", 119, 4507)
    assert event and event["window_seconds"] == 120


def test_normal_move_does_not_trigger():
    detector = VolatilityDetector()
    detector.observe("XAU", 0, 4500)
    assert detector.observe("XAU", 119, 4504.9) is None
