#!/usr/bin/env python3
"""Backfill trade_reason + confirmation_reason on every curriculum example.

Goal (v004 LoRA fuel): teach *concepts + closed-candle confirmation*, not entry
prices alone. Reasons are grounded in distilled topic doctrine
(`model_training/knowledge/topics/`) and the example's own setup facts.

See model_training/CURRICULUM_AND_DATA_PREP.md §1.2.

Usage:
  python enrich_trade_reasons_v004.py --dry-run
  python enrich_trade_reasons_v004.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "knowledge"
STAGE_02 = "stage_02_structured_data.jsonl"
STAGE_04 = "stage_04_decision_contract.jsonl"

# Concept anchors distilled from knowledge/topics — teach structure, not rote entries.
TOPIC_CONCEPTS = {
    "01_market": (
        "Session participation and inventory reset set permission; direction only "
        "after a closed response at a mapped zone inside that session."
    ),
    "02_market_structure": (
        "Named support/resistance and auction state (acceptance/rejection/balance) "
        "outrank pattern names; trade the imbalance at the level."
    ),
    "03_candlestick_patterns": (
        "Candle labels compress bar geometry; they only matter with prior trend, "
        "distance to an HTF level, and a closed confirming bar."
    ),
    "04_timeframe_relations": (
        "H4/H1 locate the auction; M15/M5/M1 only time the response. Never fade an "
        "unfinished higher-timeframe acceptance with a local wick."
    ),
    "05_ict_concepts": (
        "Liquidity/sweeps are close-location facts at session or swing extremes — "
        "breach then close back inside is fakeout; close outside is acceptance."
    ),
    "06_fvg_imbalance": (
        "Imbalance/FVG is context for path after a valid level response, not a "
        "standalone entry signal without closed confirmation."
    ),
    "07_trend_trading": (
        "With-trend pullbacks need a closed reclaim at the mapped level; "
        "countertrend needs stronger location + confirmation or is wait/skip."
    ),
    "08_range_trading": (
        "Fade H4/H1 range edges only after LTF rejection closes; mid-range without "
        "a mapped level is empty space — skip."
    ),
    "09_reversal_trading": (
        "Reversal requires prior trend into a level plus a closed rejection/failure "
        "test; identical geometry without that context is not a reverse."
    ),
}

SHALLOW_WHY = {
    "",
    "session structure",
    "n/a",
    "structure",
    "level",
    "setup",
}


def load(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save(name: str, rows: list[dict]) -> None:
    (ROOT / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def side_of(row: dict) -> str:
    direction = str(row.get("direction") or "").strip().lower()
    if direction in ("buy", "sell"):
        return direction
    td = str(row.get("trade_decision") or "").lower()
    if any(w in td for w in ("short", "sell")) and "long" not in td:
        return "sell"
    if any(w in td for w in ("long", "buy")) and "short" not in td:
        return "buy"
    return "none"


def action_of(row: dict) -> str:
    action = str(row.get("action") or "").strip().lower()
    if action in ("open", "wait", "skip"):
        return action
    td = str(row.get("trade_decision") or "").lower()
    if td.startswith("skip"):
        return "skip"
    if td.startswith("wait"):
        return "wait"
    if float(row.get("entry_price") or 0) > 0:
        return "open"
    return "wait"


def primary_level(key_levels: str) -> str:
    if not key_levels or key_levels == "N/A":
        return "the mapped zone"
    first = key_levels.split(",")[0].strip()
    return first.split("=")[0].strip() or "the mapped zone"


def extract_candle_cues(setup: str) -> list[str]:
    text = setup or ""
    cues: list[str] = []
    patterns = [
        (r"\bbull(?:ish)?\s+engulf", "bullish engulfing close"),
        (r"\bbear(?:ish)?\s+engulf", "bearish engulfing close"),
        (r"\bengulf", "engulfing close"),
        (r"\bhammer\b", "hammer close back above the level"),
        (r"\bhanging\s+man\b", "hanging-man shape needing next-bar confirmation"),
        (r"\bshooting\s+star\b", "shooting-star upper-wick rejection close"),
        (r"\binverted\s+hammer\b", "inverted hammer needing confirming higher close"),
        (r"\bdoji\b", "doji indecision at the level"),
        (r"\bpin\b|\bpinbar\b", "pin / rejection wick with close back inside"),
        (r"two-?bar", "two-bar closed response"),
        (r"upper\s+wick|long\s+upper", "upper-wick rejection"),
        (r"lower\s+wick|long\s+lower", "lower-wick rejection"),
        (r"close\s+inside|closes?\s+back\s+inside", "close back inside the level (fakeout)"),
        (r"close\s+outside|accepted?\s+close|closes?\s+outside", "accepted close outside the level"),
        (r"\bsweep\b", "sweep of the extreme then closed response"),
        (r"\bfakeout\b|\bfalse\s+break", "fakeout — breach then close back inside"),
        (r"\breject(?:ion|ed)?\b", "rejection close at the level"),
        (r"\baccept(?:ance|ed)?\b", "acceptance / continued closes through the level"),
        (r"m5\s+(?:bull|bear|close|engulf|pin)", "closed M5 response"),
        (r"m1\s+(?:bull|bear|close|engulf|pin)", "closed M1 response"),
        (r"m15\s+(?:bull|bear|close|engulf|pin|reject)", "closed M15 response"),
        (r"last\s+5min|end-?bar", "end-bar closed confirmation into the level"),
    ]
    for pat, label in patterns:
        if re.search(pat, text, re.I):
            cues.append(label)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for cue in cues:
        if cue not in seen:
            seen.add(cue)
            out.append(cue)
    return out[:3]


def concept_for(topic: str) -> str:
    return TOPIC_CONCEPTS.get(
        topic,
        "Location + closed response at a named level decide quality; forming candles are context only.",
    )


def ascii_clean(text: str) -> str:
    """Keep Sample Prepared text LoRA-safe (no mojibake from fancy dashes/arrows)."""
    if not text:
        return ""
    repl = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2192": "->",
        "\u2190": "<-",
        "\u00d7": "x",
        "\u2265": ">=",
        "\u2264": "<=",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return text.encode("ascii", "replace").decode("ascii").replace("?", " ")


def build_trade_reason(
    *,
    topic: str,
    side: str,
    action: str,
    auction: str,
    level: str,
    title: str,
    decision: str,
    skip_code: str | None,
    missing_fact: str | None,
) -> str:
    concept = concept_for(topic)
    auction = (auction or "unclear").strip().lower()
    if action == "skip":
        code = skip_code or "discipline"
        return (
            f"Concept: {concept} Reason: skip ({code}) - setup quality is irrelevant "
            f"under a hard gate; no entry while {code.replace('_', ' ')} applies."
        )
    if action == "wait":
        miss = missing_fact or "a closed response at the mapped zone"
        return (
            f"Concept: {concept} Reason: wait - direction not yet earned; missing "
            f"fact is '{miss}'. Forming candles cannot authorize the side."
        )
    side_word = "buy" if side == "buy" else "sell" if side == "sell" else "the side"
    auction_bit = (
        f"Auction reads {auction} at {level}"
        if auction and auction != "unclear"
        else f"Price is interacting with {level}"
    )
    label = ascii_clean(title or decision)
    return (
        f"Concept: {concept} Reason: {side_word} because {auction_bit} "
        f"({label}). Trade the closed response in that direction - "
        f"not the raw pattern name alone."
    )


def build_confirmation_reason(
    *,
    action: str,
    side: str,
    setup: str,
    auction: str,
    level: str,
    missing_fact: str | None,
    decision_conditions: str,
) -> str:
    cues = extract_candle_cues(setup)
    if action == "skip":
        return (
            "Confirmation: N/A - skip gate fired before candle confirmation is judged. "
            "Do not invent a confirming close to override the skip code."
        )
    if action == "wait":
        miss = missing_fact or "one closed M1/M5 response at the zone"
        return (
            f"Confirmation needed: {miss}. Forming bars are context only; "
            f"wait for a closed {'bullish' if 'bull' in (missing_fact or '').lower() else 'directional'} "
            f"response at {level} before taking a side."
        ).replace(" a closed directional", " a closed")

    direction = "bullish" if side == "buy" else "bearish" if side == "sell" else "directional"
    if cues:
        cue_text = "; ".join(cues)
        return (
            f"Confirmation: {cue_text} in the {direction} direction at {level}. "
            f"Closed-bar location confirms the {auction or 'response'}; "
            f"do not enter on the wick alone."
        )
    # Fall back to decision_conditions / auction when setup lacks candle words.
    cond = (decision_conditions or "").strip()
    if re.search(r"close|wick|engulf|pin|reject|hammer|star|sweep|fakeout", cond, re.I):
        return (
            f"Confirmation: {cond} - treat this as the closed {direction} response "
            f"at {level}; forming candles are not proof."
        )
    return (
        f"Confirmation: require one closed M1 or M5 {direction} response at {level} "
        f"(auction={auction or 'unclear'}). Pattern names without that closed "
        f"response are not enough."
    )


def enrich_pair(s2: dict, s4: dict) -> tuple[str, str, bool]:
    topic = str(s2.get("topic") or "")
    setup = str(s2.get("setup") or "")
    title = str(s2.get("title") or "")
    side = side_of(s4)
    action = action_of(s4)
    if str(s4.get("role") or "entry") == "management":
        trade_reason = (
            f"Concept: {concept_for(topic)} Reason: manage the open thesis - "
            f"hold/protect/close from closed facts at the decision level, never average or reverse."
        )
        conf_type = str(s4.get("confirmation_type") or "none")
        confirmation = (
            f"Confirmation: management uses confirmation_type={conf_type} at "
            f"{s4.get('decision_level_ref') or 'the decision level'}; wick alone is not enough to close."
        )
        return trade_reason, confirmation, True

    level = primary_level(str(s4.get("key_levels") or ""))
    trade_reason = build_trade_reason(
        topic=topic,
        side=side,
        action=action,
        auction=str(s4.get("auction_state") or ""),
        level=level,
        title=title,
        decision=str(s4.get("trade_decision") or s2.get("decision") or ""),
        skip_code=s4.get("skip_reason_code"),
        missing_fact=s4.get("missing_fact"),
    )
    confirmation = build_confirmation_reason(
        action=action,
        side=side,
        setup=setup,
        auction=str(s4.get("auction_state") or ""),
        level=level,
        missing_fact=s4.get("missing_fact"),
        decision_conditions=str(s4.get("decision_conditions") or ""),
    )
    return trade_reason, confirmation, False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s2_rows = load(STAGE_02)
    s4_rows = load(STAGE_04)
    s2_map = {r["example_id"]: r for r in s2_rows}

    filled = 0
    why_upgraded = 0
    for row in s4_rows:
        eid = row["example_id"]
        s2 = s2_map.get(eid, {})
        trade_reason, confirmation, _ = enrich_pair(s2, row)
        trade_reason = ascii_clean(trade_reason)
        confirmation = ascii_clean(confirmation)
        row["trade_reason"] = trade_reason
        row["confirmation_reason"] = confirmation
        # Keep decision_conditions informative for open entries when it was thin.
        if action_of(row) == "open":
            cond = str(row.get("decision_conditions") or "").strip()
            if len(cond) < 24 or cond.lower() in SHALLOW_WHY:
                row["decision_conditions"] = confirmation.split("Confirmation: ", 1)[-1][:160]
        filled += 1

        why = str(s2.get("why") or "").strip()
        if why.lower() in SHALLOW_WHY or len(why) <= 24:
            # Stage_02 why becomes the concept+direction sentence (teach doctrine).
            s2["why"] = ascii_clean(
                trade_reason.replace("Concept: ", "").split(" Reason: ", 1)[-1][:180]
            )
            why_upgraded += 1
        elif any(ord(ch) > 127 for ch in why):
            s2["why"] = ascii_clean(why)
            why_upgraded += 1

    print(f"filled_reasons={filled} why_upgraded={why_upgraded}")
    if args.dry_run:
        sample = next(
            (r for r in s4_rows if action_of(r) == "open"),
            s4_rows[0],
        )
        print("sample_trade_reason:", sample.get("trade_reason"))
        print("sample_confirmation:", sample.get("confirmation_reason"))
        print("dry-run: no files written")
        return

    save(STAGE_04, s4_rows)
    save(STAGE_02, s2_rows)
    print(f"wrote {STAGE_04} and {STAGE_02}")


if __name__ == "__main__":
    main()
