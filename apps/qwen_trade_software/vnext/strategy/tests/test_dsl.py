from vnext.strategy.dsl import Rule, StrategyProgram


def state(direction="buy", zones=None):
    return {"state_hash": "h1", "structure": {"direction": direction},
            "zones": zones or [
                {"zone_id": "z1", "lifecycle_state": "FRESH", "acceptance_density": .8},
                {"zone_id": "z2", "lifecycle_state": "ACTIVE", "acceptance_density": .6},
            ]}


def program():
    return StrategyProgram("reclaim", "break", "next", rules=(Rule("structure.direction", "in", ("buy", "sell")),), minimum_acceptance_density=.5)


def test_dsl_emits_only_when_two_valid_zones_exist():
    intent = program().propose(state())
    assert intent is not None and intent.direction == "buy" and intent.target_zone_ids == ("z2",)
    assert program().propose(state(zones=state()["zones"][:1])) is None


def test_dsl_rejects_unknown_direction():
    assert program().propose(state(direction="neutral")) is None
