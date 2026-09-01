"""Final modular boundary before the existing validated executor."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from vnext.risk.engine import RiskDecision
from vnext.strategy.contracts import TradeCandidate


def validate_candidate_for_execution(candidate: TradeCandidate) -> dict[str, object]:
    """Return auditable candidate facts; never approves, sizes, or submits orders."""
    if candidate.direction not in {"buy", "sell"}:
        raise ValueError("candidate must have one committed direction")
    return {
        "candidate_id": candidate.candidate_id,
        "pair": candidate.pair,
        "direction": candidate.direction,
        "zone_id": candidate.zone_id,
        "invalidation": candidate.invalidation,
        "target_zone_ids": list(candidate.target_zone_ids),
        "state_hash": candidate.state_hash,
        "execution_authority": "vnext_deterministic_oms",
    }


def build_order_intent(candidate: TradeCandidate, risk: RiskDecision) -> dict[str, Any]:
    """Create one exact, idempotent market-order intent from approved facts."""
    if not risk.approved or None in (risk.normalized_volume, risk.entry_price, risk.stop_price, risk.target_price):
        raise ValueError("approved normalized risk geometry is required for an order intent")
    if datetime.fromisoformat(candidate.expires_at_utc.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise ValueError("candidate expired before order intent creation")
    payload = {
        "candidate_id": candidate.candidate_id, "pair": candidate.pair,
        "direction": candidate.direction, "entry_price": risk.entry_price,
        "stop": risk.stop_price, "target": risk.target_price,
        "volume": risk.normalized_volume, "risk_hash": risk.request_hash,
        "state_hash": candidate.state_hash, "strategy_id": candidate.strategy.strategy_id,
        "strategy_version": candidate.strategy.version, "magic_number": candidate.strategy.magic_number,
        "comment": candidate.strategy.execution_comment, "expires_at_utc": candidate.expires_at_utc,
    }
    payload["order_id"] = "ord-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
    return payload


def validate_order_intent(order: Mapping[str, Any], candidate: TradeCandidate, risk: RiskDecision) -> dict[str, Any]:
    """Reject, rather than repair, an intent that differs from approved facts."""
    expected = build_order_intent(candidate, risk)
    supplied = dict(order)
    mismatches = [name for name, value in expected.items() if supplied.get(name) != value]
    extras = set(supplied).difference(expected)
    if mismatches or extras:
        details = ",".join(sorted(mismatches + [f"unexpected:{name}" for name in extras]))
        raise ValueError(f"order intent differs from approved candidate/risk: {details}")
    return expected
