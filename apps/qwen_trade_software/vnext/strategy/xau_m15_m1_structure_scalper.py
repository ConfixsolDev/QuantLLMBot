"""Contract for the first supplied strategy; no broker or model calls."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from vnext.strategy.contracts import StrategyDefinition
from vnext.strategy.definition import StrategySpec
from vnext.strategy.management import ScalpManagementParameters


STRATEGY_ID = "XAU_M15_M1_STRUCTURE_SCALPER_50PT_V1"
DEFINITION = StrategyDefinition(
    pair="XAUUSDr", strategy_id=STRATEGY_ID, version="1.6.0",
    magic_number=3101, trade_class="MICRO", comment_prefix="QVN:XAU:M15M1:50",
    context_requirements=("D1", "H4", "H2", "H1", "M15", "M1"),
    eligible_zone_types=("SUPPORT", "RESISTANCE", "ACCEPTANCE_CORE", "REJECTION_ENVELOPE",
                         "BOS_ORIGIN", "CHOCH_ORIGIN", "BREAKOUT_RETEST_ZONE", "MAJOR_SWING_ZONE"),
    evaluation_cadence_seconds=60, expiry_seconds=75,
    metadata={"logical_pair": "XAUUSD", "level_timeframe": "M15", "execution_timeframe": "M1",
              "higher_timeframes": ("H1", "H2", "H4", "D1"), "excluded_timeframes": ("M5",),
              "target_profile": "APPROX_50_POINTS"},
)

# Strategy-owned execution policy. The $3/$5 bracket is the existing scalp
# doctrine; $300/$2,000 and single-position limits were explicitly confirmed
# by the operator for the demo activation path on 2026-08-31.
RISK_POLICY = {
    "schema_version": "XAU_M15_M1_RISK_POLICY_V1",
    "entry_mode": "MARKET",
    "stop_distance_price": 3.0,
    "target_distance_price": 5.0,
    "max_cash_loss": 300.0,
    "daily_loss_cap": 2000.0,
    "max_open_positions": 1,
    "max_deviation_points": 20,
}

# Entry-session contract. These are UTC fixed windows, deliberately not
# DST-adjusted. Evidence: the approved doctrine defines New York as 16:00-21:00
# and the operator explicitly selected its full session on 2026-08-31. Contrary
# evidence: a retired entry gate cut New York at 17:00. This v1.3.0 change must
# be falsified by the permitted two-month leakage-safe replay before activation.
# This belongs to this strategy because it decides whether this strategy may
# create an entry candidate; common market state merely carries the UTC clock.
ENTRY_SESSION_WINDOWS_UTC = (
    ("asia", 0, 7),
    ("london", 8, 13),
    ("overlap", 13, 16),
    ("new_york", 16, 21),
)


def entry_session_at(moment: datetime) -> dict[str, Any]:
    """Return the unchanged, half-open UTC entry window containing ``moment``."""
    now = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    for name, start_hour, end_hour in ENTRY_SESSION_WINDOWS_UTC:
        if start_hour <= now.hour < end_hour:
            end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
            return {"session": name, "trade_permitted": True,
                    "session_end_utc": end.isoformat(),
                    "seconds_remaining": max(0, int((end - now).total_seconds()))}
    next_midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                     + timedelta(days=1))
    return {"session": "off_session", "trade_permitted": False,
            "session_end_utc": next_midnight.isoformat(),
            "seconds_remaining": max(0, int((next_midnight - now).total_seconds()))}

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
    target_zone_policy="nearest_meaningful_opposing_structure_or_fixed_5_price_tp",
    management_policy="ScalpManagementParameters",
    statistical_qualification={"minimum_samples": 100, "required_replay_sessions": 5,
                                "required_cost_adjusted_space": True},
    narrator_request={"context_timeframes": ("D1", "H4", "H2", "H1"),
                      "setup_timeframes": ("M15",), "execution_timeframes": ("M1",),
                      "explicitly_exclude": ("M5",), "max_bars_per_timeframe": 32,
                      "max_structure_events": 16, "max_zones": 12,
                      "include_statistics": False,
                      "focus_tags": ("active_M15_level", "M1_episode_confirmation",
                                     "higher_timeframe_path", "target_space")},
    model_contract={
        "schema_version": "XAU_M15_M1_QWEN_ARBITRATION_V1",
        "decision_scope": "arbitrate_the_supplied_candidate_only",
        "focus": {
            "context_timeframes": ("D1", "H4", "H2", "H1"),
            "setup_timeframes": ("M15",),
            "execution_timeframes": ("M1",),
            "excluded_timeframes": ("M5",),
            "focus_tags": ("active_M15_level", "M1_episode_confirmation",
                           "higher_timeframe_path", "target_space"),
        },
        "required_entry_feedback": ("M15_level_active", "M1_episode_confirmed", "target_space_valid"),
        "required_temporal_feedback": ("H1_slot", "H2_slot", "H4_slot", "parent_formation_path", "causal_frontier"),
        "excluded_timeframes": ("M5",),
        "approval_rule": "Approve only when the supplied candidate and its cited strategy evidence remain coherent; otherwise WAIT, VETO, or NO_TRADE.",
        "prohibited_actions": ("change_candidate_geometry", "size_risk", "submit_order"),
    },
    management_parameters=asdict(MANAGEMENT),
)

REQUIRED_EVIDENCE_FIELDS = (
    "level_id", "episode_id", "direction", "structure_family", "structure_sequence",
    "entry_mode", "invalidation_structure_id", "target_zone_id", "target_space_points",
    "state_hash", "structure_version", "zone_version", "statistics_snapshot_id",
)


def build_strategy_evidence(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Select this strategy's M15 level and M1 trigger from neutral facts.

    The selection is deliberately here rather than in a shared intelligence
    module.  The active M15 level, M1 swing direction, opposing M1
    invalidation, and nearest opposing M15 target are all this strategy's
    entry semantics.  `store/sop.md` supplies the approved principle that the
    target is the nearest meaningful opposing structure; this implementation
    is an executable, testable form of that principle, not a common rule.
    """
    zones = [row for row in state.get("zones", ()) if isinstance(row, Mapping)
             and row.get("timeframe") == "M15"
             and row.get("lifecycle_state") in {"FRESH", "ACTIVE", "TESTED"}]
    events = [row for row in state.get("structural_events", ()) if isinstance(row, Mapping)
              and row.get("timeframe") == "M1"
              and row.get("event_type") in {"SWING_HIGH_CONFIRMED", "SWING_LOW_CONFIRMED"}]
    if not zones or not events:
        return None
    latest = max(events, key=lambda row: (str(row.get("observed_at_utc", "")), str(row.get("event_id", ""))))
    direction = "buy" if latest["event_type"] == "SWING_LOW_CONFIRMED" else "sell"
    opposing = "SWING_HIGH_CONFIRMED" if direction == "buy" else "SWING_LOW_CONFIRMED"
    invalidations = [row for row in events if row.get("event_type") == opposing]
    if not invalidations:
        return None
    invalidation = max(invalidations, key=lambda row: (str(row.get("observed_at_utc", "")), str(row.get("event_id", ""))))
    price = _latest_close(state)
    if price is None:
        return None
    entry = min(zones, key=lambda row: (abs(((float(row["lower"]) + float(row["upper"])) / 2) - price),
                                        str(row.get("zone_id", ""))))
    targets = [row for row in zones if row.get("zone_id") != entry.get("zone_id")
               and ((direction == "buy" and float(row["lower"]) > float(entry["upper"]))
                    or (direction == "sell" and float(row["upper"]) < float(entry["lower"])))]
    target = min(targets, key=lambda row: (float(row["lower"]) - float(entry["upper"])
                                            if direction == "buy"
                                            else float(entry["lower"]) - float(row["upper"]),
                                            str(row.get("zone_id", "")))) if targets else None
    state_hash = str(state.get("state_hash") or _facts_hash(state))
    # Operator-approved strategy default: a $5 XAUUSD price target whenever
    # the bounded M15 packet has no meaningful opposing target zone.
    target_id = str(target["zone_id"]) if target else "FIXED_TP_5_PRICE"
    target_space = (abs((float(target["lower"]) if direction == "buy" else float(target["upper"])) - price)
                    if target else float(RISK_POLICY["target_distance_price"]))
    return {
        "strategy_id": STRATEGY_ID, "level_id": str(entry["zone_id"]),
        "episode_id": f"{entry['zone_id']}:{latest['event_id']}", "direction": direction,
        "structure_family": "SUPPORT" if direction == "buy" else "RESISTANCE",
        "structure_sequence": (str(latest["event_id"]), str(invalidation["event_id"])),
        "entry_mode": "market_after_M1_confirmation", "invalidation_structure_id": str(invalidation["event_id"]),
        "target_zone_id": target_id, "target_space_points": target_space,
        "state_hash": state_hash, "structure_version": "causal_structure_v1",
        "zone_version": str(entry.get("algorithm_version", "ZONE_V1")),
        "statistics_snapshot_id": f"snapshot_{state_hash}", "timeframes_used": "M15,M1",
    }


def _latest_close(state: Mapping[str, Any]) -> float | None:
    rows = state.get("timeframes", {}).get("M1", ()) if isinstance(state.get("timeframes"), Mapping) else ()
    if not rows or not isinstance(rows[-1], Mapping):
        return None
    try:
        return float(rows[-1]["close"])
    except (KeyError, TypeError, ValueError):
        return None


def _facts_hash(state: Mapping[str, Any]) -> str:
    raw = json.dumps({"frontier": state.get("time_frontier_utc"), "zones": state.get("zones", ()),
                      "events": state.get("structural_events", ())}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def candidate_blockers(state: Mapping[str, Any]) -> tuple[str, ...]:
    """Explain why the unchanged strategy contract cannot create a candidate."""
    evidence = state.get("strategy_evidence") or build_strategy_evidence(state)
    if not isinstance(evidence, Mapping) or not evidence:
        return ("strategy_evidence_missing",)
    blockers: list[str] = []
    temporal = state.get("temporal_state")
    if isinstance(temporal, Mapping):
        entry_session = temporal.get("entry_session")
        if not isinstance(entry_session, Mapping):
            blockers.append("entry_session_missing")
        elif not bool(entry_session.get("trade_permitted")):
            blockers.append("entry_off_session")
    if str(evidence.get("strategy_id")) != STRATEGY_ID:
        blockers.append("strategy_id_mismatch")
    if evidence.get("timeframes_used") == "M5":
        blockers.append("m5_is_excluded")
    missing = [key for key in REQUIRED_EVIDENCE_FIELDS
               if key not in evidence or evidence[key] in (None, "", ())]
    blockers.extend(f"missing:{key}" for key in missing)
    try:
        if "target_space_points" not in missing and float(evidence["target_space_points"]) <= 0:
            blockers.append("target_space_not_positive")
    except (TypeError, ValueError):
        blockers.append("target_space_invalid")
    return tuple(blockers)


def candidate_inputs(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build candidate inputs only from complete shared strategy evidence.

    This function intentionally does not detect structures or create levels.
    Until the shared engines publish the required episode/space contract it
    returns no candidate, keeping the strategy fail-closed.
    """
    if candidate_blockers(state):
        return None
    evidence = state.get("strategy_evidence") or build_strategy_evidence(state)
    assert isinstance(evidence, Mapping)
    return {
        "candidate_id": str(evidence.get("candidate_id") or f"{STRATEGY_ID}:{evidence['episode_id']}"),
        "direction": str(evidence["direction"]).lower(), "zone_id": str(evidence["level_id"]),
        "invalidation": str(evidence["invalidation_structure_id"]),
        "target_zone_ids": (str(evidence["target_zone_id"]),),
        "metadata": {
            **{key: evidence[key] for key in REQUIRED_EVIDENCE_FIELDS if key != "state_hash"},
            "evidence_state_hash": str(evidence["state_hash"]),
            "qwen_feedback": dict(SPEC.model_contract),
            "risk_policy": dict(RISK_POLICY),
        },
    }
