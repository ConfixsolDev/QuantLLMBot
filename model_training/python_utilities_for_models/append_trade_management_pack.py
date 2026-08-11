#!/usr/bin/env python3
"""Append in-trade management examples distilled from topic 10.

Why this pack exists
--------------------
6 of 508 curriculum rows carried a management action, while in-trade decisions
were costing more than entries were making:

    left alone until target reached   n=3   avg +247.38
    closed on the model's judgement   n=8   avg  -20.22

The model was never taught when a trade is genuinely dead versus merely
uncomfortable, so it closed on discomfort. Douglas gives the mechanism: a holder
who fears losing "will gather information against the trade" -- it manufactures
the justification it already wants (`douglas_zone p.99`).

Topic 10 turns the corpus into four named, checkable close conditions:

    R1 invalidation  -- the named level failed on a closed candle of its own
                        timeframe (grimes_art_science p.60, p.172)
    R2 always-in flip-- the opposite entry would now be taken with confidence
                        (brooks_reversals p.11)
    R3 arithmetic    -- remaining reward no longer clears remaining risk
                        (brooks_trends p.326)
    R4 time          -- frame budget elapsed with no structural progress
                        (carter_mastering pp.180, 201)

and one prohibition:

    R5               -- a close supported only by open P&L is not permitted

This generator produces balanced examples of all five, plus protect-instead-of-
close cases (grimes p.327 stop ladder), grounded in real level snapshots from
the cache so no prices are invented (CURRICULUM_AND_DATA_PREP.md 0.1 rule 5).

Usage
-----
    python python_utilities_for_models/append_trade_management_pack.py --dry-run
    python python_utilities_for_models/append_trade_management_pack.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
STAGE_02 = KNOWLEDGE / "stage_02_structured_data.jsonl"
STAGE_04 = KNOWLEDGE / "stage_04_decision_contract.jsonl"
DB = ROOT.parent / "apps" / "qwen_trade_software" / "backend" / "cache" / "market_context.sqlite3"

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
TF_RANK = {tf: i for i, tf in enumerate(TIMEFRAMES)}


def timeframe_of(level_id: str) -> str | None:
    head = str(level_id or "").split("_", 1)[0].upper()
    return head if head in TF_RANK else None


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _open_snapshot(db: Path) -> sqlite3.Connection:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.execute("select 1 from cache_objects limit 1").fetchone()
        return con
    except sqlite3.Error:
        pass
    temp = Path(tempfile.mkdtemp(prefix="qcache_")) / db.name
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(db) + suffix)
        if source.exists():
            shutil.copy2(source, str(temp) + suffix)
    return sqlite3.connect(str(temp))


def read_level_snapshots(db: Path, limit: int = 300) -> list[dict]:
    if not db.exists():
        raise SystemExit(f"cache not found: {db}\nRefusing to invent levels (0.1 rule 5).")
    con = _open_snapshot(db)
    con.row_factory = sqlite3.Row
    out = []
    for row in con.execute(
        """select payload_json from cache_objects where cache_type='levels'
           order by created_at_utc desc limit ?""",
        (limit,),
    ):
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            continue
        levels = {
            lv["level_id"]: float(lv.get("zone_low", 0) or 0)
            for lv in payload.get("levels", [])
            if lv.get("level_id") and lv.get("zone_low")
        }
        if len(levels) >= 6:
            out.append(levels)
    con.close()
    return out


def levels_string(levels: dict[str, float]) -> str:
    return ", ".join(f"{n}={v:.3f}" for n, v in sorted(levels.items()) if v)


# --- scenario builders ------------------------------------------------------

def scenarios(levels: dict[str, float], side: str) -> list[dict]:
    """One example of each management decision, from one real level map."""
    is_buy = side == "buy"
    entry_id = "M30_PREVIOUS_LOW" if is_buy else "M30_PREVIOUS_HIGH"
    inval_id = "H1_PREVIOUS_LOW" if is_buy else "H1_PREVIOUS_HIGH"
    target_id = "M30_PREVIOUS_HIGH" if is_buy else "M30_PREVIOUS_LOW"
    opp_id = "M15_PREVIOUS_HIGH" if is_buy else "M15_PREVIOUS_LOW"
    for needed in (entry_id, inval_id, target_id, opp_id):
        if needed not in levels:
            return []
    entry = levels[entry_id]
    inval = levels[inval_id]
    target = levels[target_id]
    inval_tf = timeframe_of(inval_id)

    return [
        {
            "key": "R1_close_invalidation",
            "action": "close",
            "decision": "Close",
            "thesis_state": "invalidated",
            "confirmation_type": "thesis_invalidation_confirmed",
            "title": f"CLOSE: {inval_id} failed on a closed {inval_tf}",
            "setup": (
                f"{side} from {entry_id} at {entry:.3f}; a closed {inval_tf} candle "
                f"printed through the named invalidation {inval_id} at {inval:.3f}"
            ),
            "why": (
                f"close because the level that defined this trade has failed on its own "
                f"timeframe. There is nothing left to be right about. This is R1 and it does "
                f"not require any judgement about how the position feels."
            ),
            "confirm": (
                f"A closed {inval_tf} candle through {inval_id}. A wick or a forming candle "
                f"would not qualify."
            ),
        },
        {
            "key": "R2_close_flip",
            "action": "close",
            "decision": "Close",
            "thesis_state": "invalidated",
            "confirmation_type": "always_in_flip_confirmed",
            "title": f"CLOSE: always-in flip at {opp_id}",
            "setup": (
                f"{side} from {entry_id}; price built an opposing structure at {opp_id} "
                f"at {levels[opp_id]:.3f} with its own closed M5 response"
            ),
            "why": (
                f"close because the opposite entry would now be taken with confidence at a "
                f"named level with a closed response. Brooks' always-in test: if you would "
                f"enter the other side here, the market is no longer the one this idea was "
                f"built for. This is R2."
            ),
            "confirm": (
                f"A closed M5 response at {opp_id} that would itself justify an entry the "
                f"other way. Discomfort without such a setup is not a flip."
            ),
        },
        {
            "key": "R3_close_arithmetic",
            "action": "close",
            "decision": "Close",
            "thesis_state": "weakening",
            "confirmation_type": "reward_risk_inverted",
            "title": "CLOSE: remaining reward no longer clears remaining risk",
            "setup": (
                f"{side} from {entry_id}; price sits close to {target_id} while the stop "
                f"remains out at {inval_id}, leaving far more risk than reward"
            ),
            "why": (
                "close because the trade's arithmetic has inverted. Brooks: exit only when "
                "chance of success times reward significantly exceeds chance of failure "
                "times risk. Nothing is structurally broken, but what is left to win no "
                "longer pays for what is still at stake. This is R3."
            ),
            "confirm": (
                "Measured from named levels: distance to target versus distance to the "
                "structural stop. Not from unrealised profit."
            ),
        },
        {
            "key": "R4_close_time",
            "action": "close",
            "decision": "Close",
            "thesis_state": "weakening",
            "confirmation_type": "time_stop_expired",
            "title": "CLOSE: frame budget elapsed with no structural progress",
            "setup": (
                f"{side} from {entry_id}; the M30 frame's time budget has elapsed and price "
                f"has covered almost none of the distance toward {target_id}"
            ),
            "why": (
                "close because the thesis has been falsified by silence rather than by "
                "price. Carter runs an explicit clock separate from the hard stop. Note the "
                "qualifier: time alone never closes a trade that is progressing. This is R4."
            ),
            "confirm": (
                "Elapsed time beyond the frame budget AND structural progress below "
                "threshold. Either alone is insufficient."
            ),
        },
        {
            "key": "R5_hold_discomfort",
            "action": "hold",
            "decision": "Wait for confirmation",
            "thesis_state": "valid",
            "confirmation_type": "none",
            "title": "HOLD: underwater but the invalidation is intact",
            "setup": (
                f"{side} from {entry_id}; price has moved well against the position but no "
                f"closed candle has broken {inval_id} and no opposing setup exists"
            ),
            "why": (
                "hold because being underwater is what this trade costs, not evidence that "
                "it is wrong. Douglas: a holder who fears losing will gather information "
                "against the trade. None of R1-R4 is met, so the answer is hold. Judge the "
                "position as if it were someone else's."
            ),
            "confirm": (
                f"No closed break of {inval_id}, no opposing closed response, reward:risk "
                f"intact, time budget not elapsed. Nothing to confirm means nothing to do."
            ),
        },
        {
            "key": "R6_hold_wick_not_close",
            "action": "hold",
            "decision": "Wait for confirmation",
            "thesis_state": "valid",
            "confirmation_type": "none",
            "title": f"HOLD: {inval_id} wicked through but did not close through",
            "setup": (
                f"{side} from {entry_id}; price traded beyond {inval_id} at {inval:.3f} "
                f"intrabar but the {inval_tf} candle closed back inside"
            ),
            "why": (
                f"hold because only a CLOSE carries invalidation. A wick through a level is "
                f"the level being tested, and a test that fails is evidence FOR the position, "
                f"not against it. Acting on the wick converts a successful defence into a loss."
            ),
            "confirm": (
                f"The {inval_tf} candle closed back inside {inval_id}. Re-evaluate only on "
                f"the next closed candle of that timeframe."
            ),
        },
        {
            "key": "R7_hold_time_but_progressing",
            "action": "hold",
            "decision": "Wait for confirmation",
            "thesis_state": "valid",
            "confirmation_type": "none",
            "title": "HOLD: time budget elapsed but the thesis is progressing",
            "setup": (
                f"{side} from {entry_id}; the frame's time budget has passed but price has "
                f"covered most of the distance toward {target_id} at {target:.3f}"
            ),
            "why": (
                "hold because the clock exists to kill dead ideas, not working ones. Dalton: "
                "a thesis can be correct and dormant, and markets bracket most of the time. "
                "R4 requires elapsed time AND absent progress; only one is present."
            ),
            "confirm": (
                "Structural progress is well above the threshold. The time stop does not fire "
                "on its own."
            ),
        },
        {
            "key": "R8_hold_adverse_candle_no_level",
            "action": "hold",
            "decision": "Wait for confirmation",
            "thesis_state": "valid",
            "confirmation_type": "none",
            "title": "HOLD: adverse momentum away from any named level",
            "setup": (
                f"{side} from {entry_id}; several opposing candles closed, but none at a "
                f"named level and none forming a setup that would be entered"
            ),
            "why": (
                "hold because adverse movement in open space is noise, not structure. A close "
                "requires a named level. Momentum that is not located at a level cannot "
                "invalidate a location-based idea."
            ),
            "confirm": (
                "No named level is involved in the adverse move. Nothing to cite means "
                "nothing to act on."
            ),
        },
        {
            "key": "protect_not_close",
            "action": "protect",
            "decision": "Protect",
            "thesis_state": "valid",
            "confirmation_type": "continuation_acceptance_confirmed",
            "title": "PROTECT: structure formed behind price",
            "setup": (
                f"{side} from {entry_id} is well toward {target_id}; a new structure has "
                f"formed and closed behind price in the trade direction"
            ),
            "why": (
                "protect rather than close. Grimes' ladder: tighten behind the new structure "
                "so the worst intended outcome becomes a scratch, while the target stays "
                "live. This is the correct response to wanting to secure the trade."
            ),
            "confirm": (
                "A closed candle forming the new structure behind price. Gap risk means the "
                "stop is a request, not a guarantee."
            ),
        },
    ]


def build_rows(snapshots: list[dict], limit: int, *, only_action: str | None = None,
               start_seq: int = 0) -> tuple[list, list]:
    """Generate management rows.

    ``only_action`` emits a single decision type, used to rebalance the
    hold:close ratio. The distribution is itself a lesson: a curriculum where
    close outnumbers hold teaches the model to close, which is the -20.22
    behaviour this pack exists to correct.
    """
    s2_rows, s4_rows = [], []
    seq = start_seq
    for levels in snapshots:
        if seq - start_seq >= limit:
            break
        for side in ("buy", "sell"):
            if seq - start_seq >= limit:
                break
            for scenario in scenarios(levels, side):
                if seq - start_seq >= limit:
                    break
                if only_action and scenario["action"] != only_action:
                    continue
                seq += 1
                eid = f"tm_{seq:03d}"
                s2_rows.append({
                    "example_id": eid,
                    "topic": "10_trade_management",
                    "title": scenario["title"],
                    "setup": scenario["setup"],
                    "decision": scenario["decision"],
                    "invalidation": scenario["confirm"],
                    "why": scenario["why"],
                    "evidence": "strong",
                    "bucket": "A",
                })
                s4_rows.append({
                    "example_id": eid,
                    "detector_output": "in_trade_review",
                    "trade_decision": scenario["decision"],
                    "decision_conditions": scenario["title"],
                    "evidence_label": "strong",
                    "conviction_score": 0.8,
                    "risk_control": "managed position; bracket on named structure",
                    "key_levels": levels_string(levels),
                    "entry_price": 0.0,
                    "sl_price": 0.0,
                    "tp_price": 0.0,
                    "sl_usd": 0.0,
                    "tp_usd": 0.0,
                    "action": "wait" if scenario["action"] == "hold" else "skip",
                    "direction": "none",
                    "confidence": 50,
                    "auction_state": "transition",
                    "skip_reason_code": None,
                    "target_mode": "none",
                    "role": "management",
                    "missing_fact": None,
                    "management_action": scenario["action"],
                    "thesis_state": scenario["thesis_state"],
                    "confirmation_type": scenario["confirmation_type"],
                    "close_confirmed": scenario["action"] == "close",
                    "trade_reason": (
                        "Concept: a trade ends when a named condition ends it -- invalidation, "
                        "always-in flip, inverted arithmetic, or an expired clock. Being "
                        f"underwater is not one of them. Reason: {scenario['why']}"
                    ),
                    "confirmation_reason": scenario["confirm"],
                })
    return s2_rows, s4_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--only", choices=("hold", "close", "protect"),
                        help="emit a single decision type, to rebalance hold:close")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    snapshots = read_level_snapshots(DB)
    print(f"evidence: {len(snapshots)} real level snapshots")
    existing_ids = {r["example_id"] for r in load_jsonl(STAGE_04)}
    start = sum(1 for i in existing_ids if str(i).startswith("tm_"))
    s2_rows, s4_rows = build_rows(
        snapshots, args.limit, only_action=args.only, start_seq=start
    )
    if not s4_rows:
        print("nothing generated -- cache lacks the required named levels")
        return 1

    print(f"\ngenerated {len(s4_rows)} management rows")
    print(f"  actions     : {dict(Counter(r['management_action'] for r in s4_rows))}")
    print(f"  confirmations: {dict(Counter(r['confirmation_type'] for r in s4_rows))}")
    print(f"  thesis states: {dict(Counter(r['thesis_state'] for r in s4_rows))}")

    if args.dry_run:
        print("\n--- sample ---")
        print(json.dumps(s4_rows[0], indent=2)[:1000])
        print("\n(dry run, nothing written)")
        return 0

    existing = {r["example_id"] for r in load_jsonl(STAGE_04)}
    new_s2 = [r for r in s2_rows if r["example_id"] not in existing]
    new_s4 = [r for r in s4_rows if r["example_id"] not in existing]
    append_jsonl(STAGE_02, new_s2)
    append_jsonl(STAGE_04, new_s4)
    print(f"\nappended {len(new_s4)} management rows")
    print("REMINDER: re-run the holdout restore and bump scripts/config.py bounds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
