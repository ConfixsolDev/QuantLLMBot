"""Shared helpers for V5 curriculum append packs (stage_01..04 alignment)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"
TICKS = ROOT / "tick_data"

HOLDOUT_IDS = [
    "02_35",
    "09_100",
    "01_14",
    "01_16",
    "09_99",
    "04_28",
    "07_19",
    "08_21",
    "09_85",
    "02_31",
]


def load(name: str) -> list[dict]:
    path = KNOW / name
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save(name: str, rows: list[dict]) -> None:
    (KNOW / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def day_atr(day: str) -> dict:
    path = TICKS / day / "atr-m1.jsonl"
    empty = {
        "atr_m1_51": None,
        "atr_m1_3": None,
        "atr_ratio_3_51": None,
        "atr_timeframe": "M1",
        "atr_source": "unavailable",
    }
    if not path.exists():
        return empty
    eod = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "eod" and row.get("ok"):
            eod = row
    if not eod:
        return empty
    a51 = eod.get("atr_m1_51")
    a3 = eod.get("atr_m1_3")
    ratio = eod.get("atr_ratio_3_51")
    if ratio is None and a3 is not None and a51:
        try:
            ratio = round(float(a3) / float(a51), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            ratio = None
    return {
        "atr_m1_51": a51,
        "atr_m1_3": a3,
        "atr_ratio_3_51": ratio,
        "atr_timeframe": "M1",
        "atr_source": f"mt5_m1_eod:{day}",
        "atr_as_of_utc": eod.get("as_of_utc") or eod.get("last_closed_time_utc"),
    }


def s2(eid, topic, title, setup, decision, invalidation, why, evidence="strong"):
    return {
        "example_id": eid,
        "topic": topic,
        "title": title,
        "setup": setup,
        "decision": decision,
        "invalidation": invalidation,
        "why": why,
        "evidence": evidence,
        "bucket": "A",
    }


def s3(eid, detector, logic, inputs, outputs):
    return {
        "example_id": eid,
        "detector_name": detector,
        "detector_logic": logic,
        "required_inputs": inputs,
        "expected_outputs": outputs,
    }


def s4(
    *,
    eid,
    detector,
    decision,
    conditions,
    action,
    direction,
    confidence,
    auction,
    key_levels,
    trade_reason,
    confirmation_reason,
    atr,
    skip_code=None,
    missing_fact=None,
    entry=0.0,
    sl=0.0,
    tp=0.0,
    frame="H1",
    role=None,
    side_ideas=None,
    trigger_tf=None,
    target_mode=None,
    management_action=None,
    thesis_state=None,
):
    is_open = action == "open"
    if target_mode is None:
        target_mode = "scalp" if is_open else "none"
    row = {
        "example_id": eid,
        "detector_output": detector,
        "trade_decision": decision,
        "decision_conditions": conditions,
        "evidence_label": "strong",
        "conviction_score": round(min(0.9, max(0.2, confidence / 100)), 2),
        "risk_control": (
            f"SL beyond structure | TP next opposing named level | frame {frame}"
            if is_open
            else "No entry until regime + location + closed trigger align"
        ),
        "key_levels": key_levels,
        "entry_price": entry if is_open else 0.0,
        "sl_price": sl if is_open else 0.0,
        "tp_price": tp if is_open else 0.0,
        "sl_usd": round(abs(entry - sl), 1) if is_open else 0.0,
        "tp_usd": round(abs(tp - entry), 1) if is_open else 0.0,
        "action": action,
        "direction": direction,
        "confidence": confidence,
        "auction_state": auction,
        "skip_reason_code": skip_code,
        "target_mode": target_mode,
        "role": role or ("entry" if is_open else action),
        "missing_fact": missing_fact,
        "structure_timeframe": frame,
        "trigger_tf": trigger_tf or "M1",
        "trade_reason": trade_reason,
        "confirmation_reason": confirmation_reason,
        **atr,
    }
    if side_ideas is not None:
        row["side_ideas"] = side_ideas
    if management_action is not None:
        row["management_action"] = management_action
        row["role"] = role or "management"
    if thesis_state is not None:
        row["thesis_state"] = thesis_state
    return row


def append_examples(
    examples: list[tuple[dict, dict, dict]],
    *,
    principles: list[dict] | None = None,
    dry_run: bool = False,
    label: str = "pack",
) -> int:
    if dry_run:
        print(json.dumps(examples[0][2], indent=2)[:1400])
        print(f"(dry run — {label} nothing written)")
        return 0

    s1 = load("stage_01_principle_foundation.jsonl")
    s2_rows = load("stage_02_structured_data.jsonl")
    s3_rows = load("stage_03_detector_definitions.jsonl")
    s4_rows = load("stage_04_decision_contract.jsonl")

    if principles:
        existing_p = {r.get("principle_id") for r in s1}
        for p in principles:
            if p["principle_id"] not in existing_p:
                s1.append(p)

    new_ids = {a["example_id"] for a, _, _ in examples}
    s2_rows = [r for r in s2_rows if r["example_id"] not in new_ids]
    s3_rows = [r for r in s3_rows if r["example_id"] not in new_ids]
    s4_rows = [r for r in s4_rows if r["example_id"] not in new_ids]

    hold_s2 = [r for r in s2_rows if r["example_id"] in HOLDOUT_IDS]
    train_s2 = [r for r in s2_rows if r["example_id"] not in HOLDOUT_IDS]
    hold_ids = {r["example_id"] for r in hold_s2}
    train_s3 = [r for r in s3_rows if r["example_id"] not in hold_ids]
    hold_s3 = [r for r in s3_rows if r["example_id"] in hold_ids]
    train_s4 = [r for r in s4_rows if r["example_id"] not in hold_ids]
    hold_s4 = [r for r in s4_rows if r["example_id"] in hold_ids]

    new_s2 = [e[0] for e in examples]
    new_s3 = [e[1] for e in examples]
    new_s4 = [e[2] for e in examples]

    save("stage_01_principle_foundation.jsonl", s1)
    save("stage_02_structured_data.jsonl", train_s2 + new_s2 + hold_s2)
    save("stage_03_detector_definitions.jsonl", train_s3 + new_s3 + hold_s3)
    save("stage_04_decision_contract.jsonl", train_s4 + new_s4 + hold_s4)

    total = len(train_s4) + len(new_s4) + len(hold_s4)
    train_end = total - len(hold_s4)
    print(
        f"appended {label} examples={len(examples)} "
        f"stage_04_total={total} holdout={len(hold_s4)}"
    )
    print(
        f"bump scripts/config.py training_lines_end={train_end} "
        f"test_lines_end={total}"
    )
    return total
