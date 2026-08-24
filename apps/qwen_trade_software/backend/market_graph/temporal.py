"""Pure temporal normalization for instrument-neutral graph projection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")

TIMEFRAME_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}
ORDERED_TIMEFRAMES = tuple(TIMEFRAME_SECONDS)


def utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def bucket_start(value: datetime, timeframe: str) -> datetime:
    seconds = TIMEFRAME_SECONDS[timeframe]
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, timezone.utc)


def ny_trading_bucket_start(value: datetime, hours: int) -> datetime:
    local = value.astimezone(NEW_YORK)
    anchor_date = local.date() if local.hour >= 17 else (local - timedelta(days=1)).date()
    anchor = datetime(anchor_date.year, anchor_date.month, anchor_date.day, 17,
                      tzinfo=NEW_YORK)
    slot = int((local - anchor).total_seconds() // (hours * 3600))
    return (anchor + timedelta(hours=slot * hours)).astimezone(timezone.utc)


def time_buckets(symbol: str, event_time: datetime, event_timeframe: str) -> list[dict]:
    event_seconds = TIMEFRAME_SECONDS.get(event_timeframe, 0)
    buckets = []
    for timeframe, seconds in TIMEFRAME_SECONDS.items():
        if seconds < event_seconds:
            continue
        moment = event_time - timedelta(microseconds=1)
        if timeframe == "H4":
            start = ny_trading_bucket_start(moment, 4)
            end = (start.astimezone(NEW_YORK) + timedelta(hours=4)).astimezone(timezone.utc)
            convention = "new_york_1700_dst"
        else:
            start = bucket_start(moment, timeframe)
            end = start + timedelta(seconds=seconds)
            convention = "utc_epoch"
        buckets.append({
            "id": f"{symbol}:{timeframe}:{convention}:{iso_utc(start)}",
            "symbol": symbol,
            "timeframe": timeframe,
            "starts_at": iso_utc(start),
            "ends_at": iso_utc(end),
            "time_convention": convention,
        })
    return buckets


def bucket_edges(buckets: list[dict]) -> list[dict]:
    by_size = sorted(buckets, key=lambda row: TIMEFRAME_SECONDS[row["timeframe"]])
    return [
        {"child_id": by_size[index]["id"], "parent_id": by_size[index + 1]["id"]}
        for index in range(len(by_size) - 1)
    ]


def session_phase(event_time: datetime, calendar_version: str) -> dict:
    # Candle events are stamped at close. Subtracting the smallest supported
    # unit keeps a candle closing exactly on a session boundary in the session
    # during which its price was actually formed.
    moment = event_time.astimezone(timezone.utc) - timedelta(microseconds=1)
    minute = moment.hour * 60 + moment.minute
    intervals = (
        (0, 420, "asia"), (420, 480, "pre_london"),
        (480, 780, "london"), (780, 960, "overlap"),
        (960, 1260, "new_york"), (1260, 1440, "off_session"),
    )
    start_minute, end_minute, name = next(row for row in intervals if row[0] <= minute < row[1])
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = day + timedelta(minutes=start_minute)
    ends = day + timedelta(minutes=end_minute)
    elapsed = (moment - starts).total_seconds()
    duration = max(1.0, (ends - starts).total_seconds())
    ratio = elapsed / duration
    phase = "opening" if ratio < 0.2 else "closing" if ratio >= 0.8 else "development"
    return {
        "id": f"{calendar_version}:{iso_utc(starts)}:{name}",
        "calendar_version": calendar_version,
        "name": name,
        "phase": phase,
        "starts_at": iso_utc(starts),
        "ends_at": iso_utc(ends),
    }


def graph_row(event: dict, schema_version: int, calendar_version: str) -> dict:
    occurred = utc_datetime(event["event_time_utc"])
    payload = event.get("payload") or {}
    facts = {key: payload.get(key) for key in (
        "open", "high", "low", "close", "tick_volume", "real_volume", "spread", "volume",
        "source", "time_convention", "constituent_count",
        "direction", "state", "transition", "active_leg",
        "invalidation_level_id", "unresolved_condition",
        "mode", "execution_authority", "status", "detector", "detector_version",
        "rule_version", "confirmation_time_utc", "knowledge_time_utc",
        "source_time_utc", "source_evidence_id", "structure_label", "prior_structure",
        "zone_id", "zone_kind", "zone_low", "zone_high", "zone_status",
        "displacement_body", "explanation",
        "supervision_mode", "uses_forward_visibility", "eligible_for_live_context",
        "eligible_for_training", "audit_rule_version", "decision_as_of_utc",
        "forward_end_utc", "quality_status", "quality_score", "combined_status",
        "defect_count", "defects", "supervised_analysis", "level_status",
        "zone_status_summary", "market_structure_status", "cross_pair_status",
        "timeframe_movement_status", "volume_profile_status", "big_tf_direction",
        "small_tf_direction", "xau_h1_direction", "dxy_h1_direction",
        "xau_h1_volume_ratio", "dxy_h1_volume_ratio", "active_zone_count",
        "total_active_zone_count", "overlapping_zone_count",
        "next_1h_return", "next_4h_return", "next_4h_mfe", "next_4h_mae",
        "decision_type", "decision_state", "confidence", "summary", "model",
        "execution_id", "event_name", "reason", "side", "entry_price",
        "exit_price", "net_pnl", "gross_pnl", "mfe", "mae", "duration_seconds",
        "market_story", "sequence_explanation", "drivers_so_far",
        "contradicting_evidence", "prior_view_status", "prior_view_reason",
        "next_focus", "observer_contract_version", "observer_fingerprint",
        "trigger", "day_open", "day_high", "day_low", "day_close",
        "day_net_move", "day_range", "structure_method",
        "deterministic_structure_state",
    ) if payload.get(key) is not None}
    buckets = time_buckets(event["symbol"], occurred, event["timeframe"])
    intraday_story = None
    if event.get("event_type") == "intraday_story":
        story_id = event["event_id"]
        swings = []
        for index, swing in enumerate((payload.get("structure_sequence") or [])[-12:]):
            swings.append({
                "id": f"{story_id}:swing:{index}:{swing.get('evidence_id') or 'none'}",
                "ordinal": index,
                "label": swing.get("label"),
                "kind": swing.get("kind"),
                "price": swing.get("price"),
                "time_utc": swing.get("time_utc"),
                "evidence_id": swing.get("evidence_id"),
            })
        level_reads = []
        for level in (payload.get("level_reads") or [])[:12]:
            level_id = str(level.get("level_id") or "")
            if not level_id:
                continue
            level_reads.append({
                "id": f"{story_id}:level:{level_id}",
                **{key: level.get(key) for key in (
                    "level_id", "timeframe", "role", "price", "zone_low", "zone_high",
                    "touch_episodes_today", "last_touch_utc", "latest_closed_response",
                    "current_relation", "qwen_quality", "qwen_price_story",
                    "next_verification",
                )},
            })
        intraday_story = {
            "id": story_id,
            "event_id": event["event_id"],
            "episode_id": payload.get("episode_id"),
            "symbol": event["symbol"],
            "as_of_utc": iso_utc(occurred),
            "recorded_at_utc": event["recorded_at_utc"],
            "state": payload.get("state"),
            "market_story": payload.get("market_story"),
            "sequence_explanation": payload.get("sequence_explanation"),
            "drivers_so_far": payload.get("drivers_so_far"),
            "contradicting_evidence": payload.get("contradicting_evidence"),
            "prior_view_status": payload.get("prior_view_status"),
            "prior_view_reason": payload.get("prior_view_reason"),
            "next_focus": payload.get("next_focus"),
            "model": payload.get("model"),
            "mode": payload.get("mode"),
            "execution_authority": bool(payload.get("execution_authority")),
            "eligible_for_live_context": bool(payload.get("eligible_for_live_context")),
            "contract_version": payload.get("observer_contract_version"),
            "fingerprint": payload.get("observer_fingerprint"),
            "trigger": payload.get("trigger"),
            "day_open": payload.get("day_open"),
            "day_high": payload.get("day_high"),
            "day_low": payload.get("day_low"),
            "day_close": payload.get("day_close"),
            "day_net_move": payload.get("day_net_move"),
            "day_range": payload.get("day_range"),
            "structure_method": payload.get("structure_method"),
            "deterministic_structure_state": payload.get("deterministic_structure_state"),
            "evidence_ids": list(dict.fromkeys(
                str(value) for value in (payload.get("evidence_ids") or []) if value
            ))[:24],
            "swings": swings,
            "level_reads": level_reads,
        }
    return {
        "event_id": event["event_id"],
        "symbol": event["symbol"],
        "timeframe": event["timeframe"],
        "event_type": event["event_type"],
        "event_time": iso_utc(occurred),
        "recorded_at": event["recorded_at_utc"],
        "evidence_id": event.get("evidence_id"),
        "used_evidence_ids": list(dict.fromkeys(
            str(value) for value in (payload.get("evidence_ids") or []) if value
        ))[:24],
        "payload_hash": event["payload_hash"],
        "previous_event_id": event.get("previous_event_id"),
        "schema_version": schema_version,
        "episode_id": payload.get("episode_id"),
        "episode_status": (
            "closed" if payload.get("event_name") in {"mt5_execution_closed", "mt5_execution_skipped"}
            else "active" if payload.get("event_name") == "mt5_execution_started" else None
        ),
        "facts": facts,
        "buckets": buckets,
        "bucket_edges": bucket_edges(buckets),
        "session": session_phase(occurred, calendar_version),
        "intraday_story": intraday_story,
    }
