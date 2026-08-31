"""Contract for the first supplied strategy; no broker or model calls."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from vnext.strategy.contracts import StrategyDefinition
from vnext.strategy.definition import StrategySpec
from vnext.strategy.management import ScalpManagementParameters


STRATEGY_ID = "XAU_M15_M1_STRUCTURE_SCALPER_50PT_V1"
DEFINITION = StrategyDefinition(
    pair="XAUUSDr", strategy_id=STRATEGY_ID, version="1.0.0",
    magic_number=3101, trade_class="MICRO", comment_prefix="QVN:XAU:M15M1:50",
    context_requirements=("D1", "H4", "H2", "H1", "M15", "M1"),
    eligible_zone_types=("SUPPORT", "RESISTANCE", "ACCEPTANCE_CORE", "REJECTION_ENVELOPE",
                         "BOS_ORIGIN", "CHOCH_ORIGIN", "BREAKOUT_RETEST_ZONE", "MAJOR_SWING_ZONE"),
    evaluation_cadence_seconds=60, expiry_seconds=75,
    metadata={"logical_pair": "XAUUSD", "level_timeframe": "M15", "execution_timeframe": "M1",
              "higher_timeframes": ("H1", "H2", "H4", "D1"), "excluded_timeframes": ("M5",),
              "target_profile": "APPROX_50_POINTS"},
)

MANAGEMENT = ScalpManagementParameters(
    initial_check_seconds=10, next_m1_check_seconds=15,
    failed_check_wait_minutes=1, break_even_atr_trigger=1.0,
    break_even_offset_atr=0.05, maximum_early_adverse_atr=0.25,
)

SPEC = StrategySpec(
    definition=DEFINITION,
    structural_requirements=("M15_level_active", "M1_episode_confirmed", "target_space_valid"),
    temporal_requirements=("H1_slot", "H2_slot", "H4_slot", "parent_formation_path", "causal_frontier"),
    trigger="allowed_M1_structure_program_within_active_M15_level",
    invalidation_policy="thesis_structure_failure",
    target_zone_policy="nearest_meaningful_opposing_structure_before_50_points",
    management_policy="ScalpManagementParameters",
    statistical_qualification={"minimum_samples": 100, "required_replay_sessions": 5,
                                "required_cost_adjusted_space": True},
    narrator_request={"context_timeframes": ("D1", "H4", "H2", "H1"),
                      "setup_timeframes": ("M15",), "execution_timeframes": ("M1",),
                      "explicitly_exclude": ("M5",)},
    management_parameters=asdict(MANAGEMENT),
)


def candidate_inputs(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build candidate inputs only from complete shared strategy evidence.

    This function intentionally does not detect structures or create levels.
    Until the shared engines publish the required episode/space contract it
    returns no candidate, keeping the strategy fail-closed.
    """
    evidence = state.get("strategy_evidence")
    if not isinstance(evidence, Mapping):
        return None
    if str(evidence.get("strategy_id")) != STRATEGY_ID or evidence.get("timeframes_used") == "M5":
        return None
    required = ("level_id", "episode_id", "direction", "structure_family", "structure_sequence",
                "entry_mode", "invalidation_structure_id", "target_zone_id", "target_space_points",
                "state_hash", "structure_version", "zone_version", "statistics_snapshot_id")
    if any(key not in evidence or evidence[key] in (None, "", ()) for key in required):
        return None
    if float(evidence["target_space_points"]) <= 0:
        return None
    return {
        "candidate_id": str(evidence.get("candidate_id") or f"{STRATEGY_ID}:{evidence['episode_id']}"),
        "direction": str(evidence["direction"]).lower(), "zone_id": str(evidence["level_id"]),
        "invalidation": str(evidence["invalidation_structure_id"]),
        "target_zone_ids": (str(evidence["target_zone_id"]),),
        "state_hash": str(evidence["state_hash"]),
        "metadata": {key: evidence[key] for key in required if key not in {"state_hash"}},
    }
