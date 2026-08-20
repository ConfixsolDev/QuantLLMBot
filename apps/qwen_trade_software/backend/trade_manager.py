"""Validated strategy layer for managing one open Qwen paper position."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ALLOWED_ACTIONS = {"hold", "protect", "close"}

ALLOWED_THESIS_STATES = {"valid", "weakening", "invalidated", "target_response"}
ALLOWED_CONFIRMATIONS = {
    "none",
    "target_rejection_confirmed",
    "thesis_invalidation_confirmed",
    "momentum_reversal_confirmed",
    "continuation_acceptance_confirmed",
    # 2026-08-10, topic 10 (trade management, distilled from the corpus).
    # Management may end a trade whenever the idea is genuinely dead, but it
    # must name WHICH condition ended it. These are the three additional named
    # conditions beyond invalidation:
    #
    #   always_in_flip_confirmed -- Brooks' always-in test (brooks_reversals
    #       p.11): the opposite entry would now be taken with confidence, at a
    #       named level, with its own closed response. The idea is not merely
    #       struggling; the market is no longer the one it was built for.
    #   reward_risk_inverted -- Brooks' trader's equation (brooks_trends p.326):
    #       remaining reward no longer clears remaining risk. The arithmetic has
    #       turned even though nothing is structurally "wrong".
    #   time_stop_expired -- Carter's clock (carter_mastering pp.180, 201): the
    #       frame's budget elapsed with no structural progress. Falsified by
    #       silence rather than by price.
    #
    # A close supported only by unrealised P&L has no entry here on purpose --
    # see topic 10 R5 and douglas_zone p.99 on manufactured evidence.
    "always_in_flip_confirmed",
    "reward_risk_inverted",
    "time_stop_expired",
    "protected_profit_exit",
}


def _closed_candles(market_context: dict) -> list[dict]:
    candles = []
    for timeframe in ("M1", "M5"):
        keep = 3 if timeframe == "M1" else 2
        for row in market_context.get(timeframe, [])[-keep:]:
            evidence_id = row.get("evidence_id")
            if not evidence_id:
                continue
            candles.append({**row, "timeframe": timeframe, "completed": True})
    return candles


def build_management_facts(
    position: dict,
    entry_plan: dict,
    current_levels: dict,
    market_context: dict,
    execution_state: dict | None = None,
    prior_management: list[dict] | None = None,
    regime_context: dict | None = None,
) -> dict:
    """Build a compact management packet with a resumable trade path."""
    side = position["side"]
    current = float(position["current_price"])
    entry = float(position["open_price"])
    current_move = current - entry if side == "buy" else entry - current
    execution_state = execution_state or {}
    prior_management = list(prior_management or [])[-3:]
    candles = _closed_candles(market_context)
    peak_move = max(
        current_move,
        float(execution_state.get("peak_favorable_price_move", current_move)),
    )
    peak_price = entry + peak_move if side == "buy" else entry - peak_move
    prior_peaks = [
        float(row["peak_price"])
        for row in prior_management
        if row.get("peak_price") is not None
    ]
    if prior_peaks:
        peak_price = (
            max([peak_price, *prior_peaks])
            if side == "buy"
            else min([peak_price, *prior_peaks])
        )
    opened_at = position.get("opened_at")
    opened_time = None
    if opened_at:
        try:
            opened_time = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
        except ValueError:
            opened_time = None
    path_m1 = []
    for row in candles:
        if row.get("timeframe") != "M1":
            continue
        row_time = None
        if row.get("closed_at_utc"):
            try:
                row_time = datetime.fromisoformat(
                    str(row["closed_at_utc"]).replace("Z", "+00:00")
                )
            except ValueError:
                row_time = None
        if opened_time is None or row_time is None or row_time >= opened_time:
            path_m1.append(row)
    if path_m1:
        candle_peak = (
            max(float(row["high"]) for row in path_m1)
            if side == "buy"
            else min(float(row["low"]) for row in path_m1)
        )
        peak_price = (
            max(peak_price, candle_peak)
            if side == "buy"
            else min(peak_price, candle_peak)
        )
    peak_move = peak_price - entry if side == "buy" else entry - peak_price
    flattened_levels = {
        str(level_id): float(price) for level_id, price in current_levels.items()
    }
    nearby = sorted(
        flattened_levels.items(), key=lambda item: abs(item[1] - current)
    )[:6]
    traversed = sorted(
        (
            (level_id, price)
            for level_id, price in flattened_levels.items()
            if (
                entry < price <= peak_price
                if side == "buy"
                else peak_price <= price < entry
            )
        ),
        key=lambda item: abs(item[1] - entry),
        reverse=True,
    )[:6]
    level_references = {
        "planned_target": {
            "level_id": entry_plan["target_level_id"],
            "price": float(entry_plan["take_profit"]),
            "source": "immutable_entry_plan",
        },
        "planned_invalidation": {
            "level_id": entry_plan["stop_level_id"],
            "price": float(entry_plan["stop_loss"]),
            "source": "immutable_entry_plan",
        },
    }
    for level_id, price in dict(nearby + traversed).items():
        level_references[f"current:{level_id}"] = {
            "level_id": level_id,
            "price": price,
            "source": "current_closed_market_map",
        }
    reached_favorable = []
    for level_ref, reference in level_references.items():
        level = float(reference["price"])
        reached = (
            entry < level <= peak_price
            if side == "buy"
            else peak_price <= level < entry
        )
        if reached:
            reached_favorable.append(level_ref)
    reached_favorable.sort(
        key=lambda ref: abs(float(level_references[ref]["price"]) - entry),
        reverse=True,
    )
    return {
        "contract": "single_position_level_to_level_v2",
        "position": {
            "ticket": int(position["ticket"]),
            "symbol": position["symbol"],
            "side": side,
            "volume": float(position["volume"]),
            "entry": entry,
            "current": current,
            "gross_pnl": float(position["profit"]),
            "favorable_price_move": round(current_move, 3),
            "broker_stop": float(position.get("stop_loss") or 0.0),
        },
        "entry_thesis": {
            "reason": entry_plan.get("reason"),
            "entry_zone": [
                float(entry_plan["entry_low"]),
                float(entry_plan["entry_high"]),
            ],
            "side": entry_plan["side"],
            "structure_timeframe": entry_plan.get("structure_timeframe"),
        },
        "trade_path": {
            "peak_price": round(peak_price, 3),
            "peak_favorable_price_move": round(peak_move, 3),
            "current_giveback_price": round(max(0.0, peak_move - current_move), 3),
            "peak_gross_pnl": execution_state.get("peak_pnl"),
            "peak_observed_at_utc": execution_state.get("created_at_utc"),
            "reached_favorable_level_refs": reached_favorable,
            "furthest_reached_level_ref": (
                reached_favorable[0] if reached_favorable else None
            ),
        },
        "regime_context": dict(regime_context or {}),
        "prior_management": prior_management,
        "level_references": level_references,
        "completed_candles": candles,
        "latest_completed_m1": next(
            (row["evidence_id"] for row in reversed(candles) if row["timeframe"] == "M1"),
            None,
        ),
        "latest_completed_m5": next(
            (row["evidence_id"] for row in reversed(candles) if row["timeframe"] == "M5"),
            None,
        ),
    }


def _closed_beyond(row: dict, level: float, side: str, favorable: bool) -> bool:
    close = float(row.get("close"))
    if side == "buy":
        return close > level if favorable else close < level
    return close < level if favorable else close > level


def _candle_touched(row: dict, level: float) -> bool:
    return float(row.get("low", float("inf"))) <= level <= float(
        row.get("high", float("-inf"))
    )


GUARD_TIMEOUT_CYCLES = 3
_NOISE_TIMEFRAMES = frozenset({"M1", "M5"})
_HTF_TIMEFRAMES = frozenset({"M15", "M30", "H1", "H4", "D1"})


def regime_hint(facts: dict) -> str:
    ctx = facts.get("regime_context") or {}
    hint = str(ctx.get("regime_hint") or "").strip().lower()
    return hint if hint else "unknown"


def scalp_regime(facts: dict) -> bool:
    ctx = facts.get("regime_context") or {}
    state = str(ctx.get("regime_state") or "").strip().lower()
    if state:
        return state in {"range", "trending_range", "reversal_confirmed"}
    return regime_hint(facts) in {"range", "exhaustion"}


def _level_timeframe(reference: dict) -> str:
    return str(reference.get("level_id", "")).upper().split("_", 1)[0]


def _reaction_level(reference: dict) -> bool:
    level_id = str(reference.get("level_id", "")).upper()
    timeframe = level_id.split("_", 1)[0]
    if timeframe not in {"M5", "M15", "M30", "H1", "H4", "D1"}:
        return False
    return any(
        marker in level_id
        for marker in ("HIGH", "LOW", "PIVOT", "R1", "R2", "S1", "S2")
    )


def _thesis_timeframe(facts: dict) -> str:
    return str(
        (facts.get("entry_thesis") or {}).get("structure_timeframe") or ""
    ).upper()


def _latest_candles(facts: dict) -> tuple[dict | None, dict | None, str | None, str | None]:
    candles = facts.get("completed_candles", [])
    by_id = {row.get("evidence_id"): row for row in candles}
    m1_id = facts.get("latest_completed_m1")
    m5_id = facts.get("latest_completed_m5")
    return by_id.get(m1_id), by_id.get(m5_id), m1_id, m5_id


def _m1_favorable(latest_m1: dict, side: str) -> bool:
    direction = latest_m1.get("direction")
    if side == "buy":
        return direction == "up"
    return direction == "down"


def _closed_m1_extreme(facts: dict, side: str) -> float | None:
    rows = [
        row for row in facts.get("completed_candles", [])
        if row.get("timeframe") == "M1"
    ]
    if not rows:
        return None
    if side == "buy":
        return max(float(row["high"]) for row in rows)
    return min(float(row["low"]) for row in rows)


def _reached_on_closed_m1(facts: dict, level: float, side: str, entry: float) -> bool:
    """Trend reach: a closed M1 printed through the level, not a live tick wick."""
    extreme = _closed_m1_extreme(facts, side)
    if extreme is None:
        return False
    if side == "buy":
        return entry < level <= extreme
    return extreme <= level < entry


def _thesis_allows_level(facts: dict, reference: dict) -> bool:
    thesis_tf = _thesis_timeframe(facts)
    if thesis_tf not in _HTF_TIMEFRAMES:
        return True
    return _level_timeframe(reference) not in _NOISE_TIMEFRAMES


def _favorable_candidates(facts: dict, *, reached: list, m5_only: bool) -> list[str]:
    levels = facts.get("level_references", {})
    out = [
        level_ref for level_ref in reached
        if level_ref in levels
        and level_ref != "planned_invalidation"
        and (level_ref == "planned_target" or _reaction_level(levels[level_ref]))
    ]
    if m5_only:
        out = [
            level_ref for level_ref in out
            if "M5" in str(levels[level_ref].get("level_id", "")).upper()
            or level_ref == "planned_target"
        ]
    else:
        out = [
            level_ref for level_ref in out
            if _thesis_allows_level(facts, levels[level_ref])
        ]
    out.sort(
        key=lambda ref: abs(
            float(levels[ref]["price"]) - float(facts["position"]["entry"])
        ),
        reverse=True,
    )
    return out


def safety_guard(facts: dict) -> dict | None:
    """Hard stop only. Always active, even when Qwen is responding."""
    latest_m1, latest_m5, m1_id, m5_id = _latest_candles(facts)
    if not latest_m1 or not latest_m5:
        return None
    side = facts.get("position", {}).get("side")
    inv = (facts.get("level_references") or {}).get("planned_invalidation")
    if not inv:
        return None
    price = float(inv["price"])
    if _closed_beyond(latest_m1, price, side, False) and _closed_beyond(
        latest_m5, price, side, False
    ):
        return {
            "action": "close",
            "thesis_state": "invalidated",
            "decision_level_ref": "planned_invalidation",
            "next_target_ref": None,
            "confirmation_type": "thesis_invalidation_confirmed",
            "confirmation_evidence_ids": [m1_id, m5_id],
            "close_confirmed": True,
            "summary": "Hard invalidation: M1+M5 closed beyond stop.",
        }
    return None


def _scalp_guard(facts: dict) -> dict | None:
    """Range/exhaustion timeout path: TP at M5 while M1 is still favorable."""
    latest_m1, latest_m5, m1_id, m5_id = _latest_candles(facts)
    if not latest_m1 or not latest_m5:
        return None
    side = facts.get("position", {}).get("side")
    if not _m1_favorable(latest_m1, side):
        return None
    reached = facts.get("trade_path", {}).get("reached_favorable_level_refs", [])
    candidates = _favorable_candidates(facts, reached=reached, m5_only=True)
    if not candidates:
        return None
    best = candidates[0]
    return {
        "action": "close",
        "thesis_state": "target_response",
        "decision_level_ref": best,
        "next_target_ref": None,
        "confirmation_type": "target_rejection_confirmed",
        "confirmation_evidence_ids": [m1_id, m5_id],
        "close_confirmed": True,
        "summary": f"Range scalp: TP at {best} while M1 favorable.",
    }


def _rejection_guard(facts: dict) -> dict | None:
    """Trend/breakout timeout path: thesis-TF rejection on closed M1 reach."""
    latest_m1, latest_m5, m1_id, m5_id = _latest_candles(facts)
    if not latest_m1 or not latest_m5:
        return None
    side = facts.get("position", {}).get("side")
    entry = float(facts["position"]["entry"])
    levels = facts.get("level_references", {})
    peak_reached = facts.get("trade_path", {}).get(
        "reached_favorable_level_refs", []
    )
    reached = [
        level_ref for level_ref in peak_reached
        if level_ref in levels
        and _reached_on_closed_m1(
            facts, float(levels[level_ref]["price"]), side, entry
        )
    ]
    candidates = _favorable_candidates(facts, reached=reached, m5_only=False)
    if _m1_favorable(latest_m1, side):
        return None
    m5_rows = [
        row for row in facts.get("completed_candles", [])
        if row.get("timeframe") == "M5"
    ]
    for level_ref in candidates:
        level = float(levels[level_ref]["price"])
        if not _closed_beyond(latest_m1, level, side, False):
            continue
        confirming_m5 = next(
            (
                row for row in reversed(m5_rows)
                if _candle_touched(row, level)
                and _closed_beyond(row, level, side, False)
            ),
            None,
        )
        if confirming_m5:
            return {
                "action": "close",
                "thesis_state": "target_response",
                "decision_level_ref": level_ref,
                "next_target_ref": None,
                "confirmation_type": "target_rejection_confirmed",
                "confirmation_evidence_ids": [
                    m1_id,
                    confirming_m5["evidence_id"],
                ],
                "close_confirmed": True,
                "summary": "Reached favorable level rejected by completed M1 and M5.",
            }
    return None


def timeout_guard(facts: dict) -> dict | None:
    """Last-resort mechanical close after Qwen has been down too long."""
    if scalp_regime(facts):
        return _scalp_guard(facts)
    return _rejection_guard(facts)


def unavailable_hold(summary: str) -> dict:
    return {
        "action": "hold",
        "thesis_state": "valid",
        "decision_level_ref": None,
        "next_target_ref": None,
        "confirmation_type": "none",
        "confirmation_evidence_ids": [],
        "close_confirmed": False,
        "summary": str(summary)[:180],
    }


def confirmed_management_guard(facts: dict) -> dict | None:
    """Safety invalidation, then timeout-style mechanical close.

    Live management must not call this before Qwen. Timeout path only.
    """
    return safety_guard(facts) or timeout_guard(facts)


def build_management_prompt(facts: dict, store_root: Path) -> str:
    """Use the compact human-owned manager contract plus current facts only."""
    from market_context_cache import load_prompt_section
    from prompt_composer import compose_market_prompt, instrument_knowledge

    contract = load_prompt_section("qwen_trade_management", store_root)
    symbol = str(facts.get("symbol") or "XAUUSDr")
    return compose_market_prompt(
        generic_contract=contract,
        symbol=symbol,
        instrument_contract=instrument_knowledge(
            symbol, store_root, load_prompt_section
        ),
        facts_label="MANAGEMENT FACTS",
        facts=facts,
    )


def management_schema(facts: dict) -> dict:
    level_refs = sorted(facts.get("level_references", {}))
    evidence_ids = sorted(
        row["evidence_id"] for row in facts.get("completed_candles", [])
    )
    nullable_level = {"type": ["string", "null"], "enum": [None, *level_refs]}
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
            "thesis_state": {
                "type": "string", "enum": sorted(ALLOWED_THESIS_STATES)
            },
            "decision_level_ref": nullable_level,
            "next_target_ref": nullable_level,
            "confirmation_type": {
                "type": "string", "enum": sorted(ALLOWED_CONFIRMATIONS)
            },
            "confirmation_evidence_ids": {
                "type": "array",
                "items": {"type": "string", "enum": evidence_ids},
                "maxItems": 3,
            },
            "close_confirmed": {"type": "boolean"},
            "regime_assessment": {
                "type": ["string", "null"],
                "enum": [
                    None, "range", "trend", "breakout", "exhaustion", "unknown",
                ],
            },
            "summary": {"type": "string", "maxLength": 180},
        },
        "required": [
            "action", "thesis_state", "decision_level_ref", "next_target_ref",
            "confirmation_type", "confirmation_evidence_ids", "close_confirmed",
            "summary",
        ],
        "additionalProperties": False,
    }


def validate_management_decision(
    decision: dict, facts: dict
) -> tuple[dict, list[str]]:
    """Fail closed unless a management response cites exact closed evidence."""
    failures: list[str] = []
    action = str(decision.get("action", "")).lower()
    thesis_state = str(decision.get("thesis_state", "")).lower()
    confirmation = str(decision.get("confirmation_type", "none")).lower()
    if action not in ALLOWED_ACTIONS:
        failures.append("management:invalid_action")
    if thesis_state not in ALLOWED_THESIS_STATES:
        failures.append("management:invalid_thesis_state")
    if confirmation not in ALLOWED_CONFIRMATIONS:
        failures.append("management:invalid_confirmation_type")

    supplied_candles = {
        row["evidence_id"]: row for row in facts.get("completed_candles", [])
    }
    cited = decision.get("confirmation_evidence_ids") or []
    if not isinstance(cited, list) or not set(cited).issubset(supplied_candles):
        failures.append("management:invented_candle_evidence")
        cited = []
    level_ref = decision.get("decision_level_ref")
    levels = facts.get("level_references", {})
    if level_ref is not None and level_ref not in levels:
        failures.append("management:unknown_level_reference")

    close_confirmed = decision.get("close_confirmed") is True
    latest_m1 = facts.get("latest_completed_m1")
    latest_m5 = facts.get("latest_completed_m5")
    required_close = safety_guard(facts)
    scalp_ok = scalp_regime(facts)
    if action == "close":
        protected_profit_exit = (
            confirmation == "protected_profit_exit"
            and bool((facts.get("profit_protection") or {}).get("armed"))
            and float((facts.get("position") or {}).get("gross_pnl") or 0.0) > 0.0
        )
        if not close_confirmed:
            failures.append("management:unconfirmed_close")
        if confirmation == "none":
            failures.append("management:close_without_confirmation_type")
        if not level_ref:
            failures.append("management:close_without_level")
        if latest_m1 not in cited:
            failures.append("management:close_without_latest_m1")
        if not protected_profit_exit and len(set(cited)) < 2:
            failures.append("management:close_needs_two_closed_candles")
        if not protected_profit_exit and not any(
            supplied_candles[item].get("timeframe") == "M5"
            for item in cited
            if item in supplied_candles
        ):
            failures.append("management:close_without_m5_confirmation")
        reached = facts.get("trade_path", {}).get(
            "reached_favorable_level_refs", []
        )
        if (
            confirmation == "target_rejection_confirmed"
            and level_ref not in reached
        ):
            failures.append("management:target_confirmation_level_not_reached")
        if confirmation == "continuation_acceptance_confirmed":
            failures.append("management:continuation_cannot_confirm_close")
        if confirmation in {
            "thesis_invalidation_confirmed",
            "momentum_reversal_confirmed",
        } and thesis_state not in {"weakening", "invalidated"}:
            failures.append("management:countermove_without_thesis_failure")
        if protected_profit_exit and level_ref != "profit_protection_floor":
            failures.append("management:protected_exit_without_floor")
        if level_ref in levels and latest_m1 in supplied_candles and not protected_profit_exit:
            level_price = float(levels[level_ref]["price"])
            latest = supplied_candles[latest_m1]
            touched = any(
                float(supplied_candles[item].get("low", float("inf")))
                <= level_price
                <= float(supplied_candles[item].get("high", float("-inf")))
                for item in cited
            )
            if not touched and not scalp_ok:
                failures.append("management:confirmation_level_not_tested")
            side = facts.get("position", {}).get("side")
            against = (
                latest.get("direction") == "down"
                if side == "buy"
                else latest.get("direction") == "up"
            )
            if not against and not scalp_ok:
                failures.append("management:latest_m1_not_against_position")
            if confirmation in {
                "thesis_invalidation_confirmed",
                "momentum_reversal_confirmed",
                "target_rejection_confirmed",
            } and not scalp_ok:
                crossed = (
                    float(latest.get("close")) < level_price
                    if side == "buy"
                    else float(latest.get("close")) > level_price
                )
                if not crossed:
                    failures.append("management:no_closed_counterbreak")
    else:
        if close_confirmed:
            failures.append("management:non_close_marked_confirmed")
        if required_close:
            failures.append("management:confirmed_close_ignored")
        if action == "hold" and thesis_state == "invalidated":
            failures.append("management:invalidated_thesis_held")
        if action == "hold" and confirmation in {
            "target_rejection_confirmed",
            "thesis_invalidation_confirmed",
            "momentum_reversal_confirmed",
        }:
            failures.append("management:hold_claims_confirmed_exit")
        if action == "protect":
            if not level_ref and not decision.get("next_target_ref"):
                failures.append("management:protect_without_sl_or_tp_level")
            if confirmation != "continuation_acceptance_confirmed":
                failures.append("management:protect_without_acceptance")
            if latest_m1 not in cited or latest_m5 not in cited:
                failures.append("management:protect_without_two_timeframe_confirmation")
            if level_ref in levels and latest_m1 in supplied_candles and latest_m5 in supplied_candles:
                level = float(levels[level_ref]["price"])
                side = facts.get("position", {}).get("side")
                if not (
                    _closed_beyond(supplied_candles[latest_m1], level, side, True)
                    and _closed_beyond(supplied_candles[latest_m5], level, side, True)
                ):
                    failures.append("management:protect_without_closed_acceptance")

    next_target_ref = decision.get("next_target_ref")
    if next_target_ref is not None and next_target_ref not in levels:
        failures.append("management:unknown_next_target")

    normalized = {
        "action": action if action in ALLOWED_ACTIONS else "hold",
        "thesis_state": thesis_state if thesis_state in ALLOWED_THESIS_STATES else "valid",
        "decision_level_ref": level_ref,
        "next_target_ref": next_target_ref,
        "confirmation_type": confirmation,
        "confirmation_evidence_ids": cited,
        "close_confirmed": close_confirmed,
        "regime_assessment": decision.get("regime_assessment"),
        "summary": str(decision.get("summary", ""))[:180],
    }
    if failures:
        normalized.update(
            {
                "action": "hold",
                "close_confirmed": False,
                "summary": "Management response blocked by deterministic validation.",
            }
        )
    return normalized, sorted(set(failures))


def decision_is_currently_applicable(
    decision: dict, facts: dict, current_price: float
) -> bool:
    """Revalidate a completed-candle decision against the post-Qwen quote."""
    if decision.get("action") == "hold":
        return True
    level_ref = decision.get("decision_level_ref")
    target_ref = decision.get("next_target_ref")
    if decision.get("action") == "protect" and not level_ref and target_ref:
        target = facts.get("level_references", {}).get(target_ref)
        if not target:
            return False
        target_price = float(target["price"])
        side = facts.get("position", {}).get("side")
        return current_price < target_price if side == "buy" else current_price > target_price
    reference = facts.get("level_references", {}).get(level_ref)
    if not reference:
        return False
    level = float(reference["price"])
    side = facts.get("position", {}).get("side")
    if decision.get("action") == "close":
        if decision.get("confirmation_type") == "protected_profit_exit":
            # Qwen deliberately harvested an already protected whole-position
            # profit. It remains actionable while the position is still green;
            # the fast worker independently owns the protection-floor breach.
            entry = float(facts.get("position", {}).get("entry") or 0.0)
            return current_price > entry if side == "buy" else current_price < entry
        # A hard invalidation remains actionable on the adverse side of the
        # stop regardless of regime. Previously scalp_regime() ran first, so a
        # range-labelled sell above its invalidation was incorrectly declared
        # stale (the scalp target rule expects a sell to be below its level).
        # That suppressed three deterministic close attempts on 2026-08-19 and
        # left the broker stop to take the loss.
        if level_ref == "planned_invalidation":
            return current_price < level if side == "buy" else current_price > level
        # Rejection stays actionable on the adverse side of the level.
        # Range scalp stays actionable while price is still at/through the TP.
        if scalp_regime(facts):
            return current_price >= level if side == "buy" else current_price <= level
        return current_price < level if side == "buy" else current_price > level
    # Protection is applicable only while price remains accepted beyond it.
    return current_price > level if side == "buy" else current_price < level


def self_test() -> dict:
    facts = {
        "latest_completed_m1": "candle:M1:2",
        "latest_completed_m5": "candle:M5:1",
        "completed_candles": [
            {
                "evidence_id": "candle:M1:2", "timeframe": "M1",
                "open": 10.5, "high": 10.6, "low": 9.8, "close": 9.9,
                "direction": "down",
            },
            {
                "evidence_id": "candle:M5:1", "timeframe": "M5",
                "open": 10.4, "high": 10.7, "low": 9.7, "close": 10.1,
                "direction": "down",
            },
        ],
        "level_references": {"planned_target": {"price": 10.0}},
        "trade_path": {"reached_favorable_level_refs": ["planned_target"]},
        "position": {"side": "buy", "entry": 9.0},
    }
    valid = {
        "action": "close",
        "thesis_state": "target_response",
        "decision_level_ref": "planned_target",
        "next_target_ref": None,
        "confirmation_type": "target_rejection_confirmed",
        "confirmation_evidence_ids": ["candle:M1:2", "candle:M5:1"],
        "close_confirmed": True,
        "summary": "Confirmed rejection at planned target.",
    }
    _, valid_failures = validate_management_decision(valid, facts)
    invalid = {**valid, "confirmation_evidence_ids": ["candle:M1:2"]}
    normalized, invalid_failures = validate_management_decision(invalid, facts)
    failures = []
    if valid_failures:
        failures.append("valid_management_close_rejected")
    if not invalid_failures or normalized["action"] != "hold":
        failures.append("unconfirmed_management_close_accepted")
    if not decision_is_currently_applicable(valid, facts, 9.9):
        failures.append("confirmed_close_rejected_at_live_price")
    if decision_is_currently_applicable(valid, facts, 10.1):
        failures.append("stale_close_accepted_after_live_reclaim")

    replay_facts = build_management_facts(
        {
            "ticket": 2094693268,
            "symbol": "XAUUSDr",
            "side": "buy",
            "volume": 0.5,
            "open_price": 4062.989,
            "current_price": 4065.022,
            "profit": 101.65,
            "stop_loss": 4059.989,
        },
        {
            "side": "buy",
            "entry_low": 4061.929,
            "entry_high": 4063.379,
            "stop_level_id": "M15_PREVIOUS_HIGH",
            "stop_loss": 4061.779,
            "target_level_id": "H4_PREVIOUS_HIGH",
            "take_profit": 4069.493,
            "reason": "M5 bullish with M1 retest",
        },
        {
            "M5_PREVIOUS_HIGH": 4066.449,
            "M15_PREVIOUS_HIGH": 4064.364,
            "M5_CURRENT_OPEN": 4064.706,
            "M1_PREVIOUS_HIGH": 4065.613,
            "M1_PREVIOUS_LOW": 4064.683,
        },
        {
            "M1": [
                {
                    "evidence_id": "candle:M1:04:48",
                    "open": 4064.289,
                    "high": 4066.449,
                    "low": 4064.239,
                    "close": 4065.549,
                    "direction": "up",
                },
                {
                    "evidence_id": "candle:M1:04:49",
                    "open": 4065.545,
                    "high": 4065.613,
                    "low": 4064.683,
                    "close": 4064.695,
                    "direction": "down",
                },
            ],
            "M5": [
                {
                    "evidence_id": "candle:M5:04:45",
                    "open": 4062.757,
                    "high": 4066.449,
                    "low": 4062.385,
                    "close": 4064.695,
                    "direction": "up",
                },
            ],
        },
        execution_state={
            "peak_favorable_price_move": 3.263,
            "peak_pnl": 163.15,
            "created_at_utc": "2026-08-04T04:48:48.409096+00:00",
        },
        prior_management=[
            {
                "timestamp_utc": "2026-08-04T04:50:36.533387+00:00",
                "peak_price": 4066.449,
                "action": "hold",
            }
        ],
    )
    replay_guard = timeout_guard(replay_facts)
    if not replay_guard or replay_guard.get("action") != "close":
        failures.append("profitable_rejection_replay_not_closed")
    elif replay_guard.get("decision_level_ref") != "current:M5_PREVIOUS_HIGH":
        failures.append("profitable_rejection_replay_wrong_level")
    else:
        _, replay_failures = validate_management_decision(
            replay_guard, replay_facts
        )
        if replay_failures:
            failures.append(
                "profitable_rejection_guard_failed_validation:"
                + "|".join(replay_failures)
            )
    bad_hold = {
        "action": "hold",
        "thesis_state": "valid",
        "decision_level_ref": "planned_invalidation",
        "next_target_ref": None,
        "confirmation_type": "none",
        "confirmation_evidence_ids": [],
        "close_confirmed": False,
        "summary": "Hold despite confirmed invalidation.",
    }
    invalidation_facts = {
        "latest_completed_m1": "candle:M1:invalidated",
        "latest_completed_m5": "candle:M5:invalidated",
        "completed_candles": [
            {
                "evidence_id": "candle:M1:invalidated",
                "timeframe": "M1",
                "open": 9.7,
                "high": 9.8,
                "low": 9.1,
                "close": 9.2,
                "direction": "down",
            },
            {
                "evidence_id": "candle:M5:invalidated",
                "timeframe": "M5",
                "open": 9.8,
                "high": 9.9,
                "low": 9.0,
                "close": 9.3,
                "direction": "down",
            },
        ],
        "level_references": {
            "planned_invalidation": {
                "level_id": "M5_PREVIOUS_LOW",
                "price": 9.5,
            }
        },
        "trade_path": {"reached_favorable_level_refs": []},
        "position": {"side": "buy", "entry": 10.0},
    }
    invalidation_guard = confirmed_management_guard(invalidation_facts)
    if (
        not invalidation_guard
        or invalidation_guard.get("confirmation_type")
        != "thesis_invalidation_confirmed"
    ):
        failures.append("confirmed_invalidation_not_closed")
    else:
        _, invalidation_failures = validate_management_decision(
            invalidation_guard, invalidation_facts
        )
        if invalidation_failures:
            failures.append("confirmed_invalidation_guard_failed_validation")
    _, bad_hold_failures = validate_management_decision(bad_hold, invalidation_facts)
    if "management:confirmed_close_ignored" not in bad_hold_failures:
        failures.append("confirmed_invalidation_hold_not_blocked")
    return {"passed": not failures, "failures": failures}
