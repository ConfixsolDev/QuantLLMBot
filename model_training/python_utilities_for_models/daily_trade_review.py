"""Daily trade review utility (model_training/python_utilities_for_models).

Reconstructs filled trades from a day's logs and writes a short review next to
tick_data (or --output-dir). Process policy:
model_training/CURRICULUM_AND_DATA_PREP.md §5 — promote lessons into store +
curriculum JSONL; do not create satellite review docs.

Usage:
    python daily_trade_review.py
    python daily_trade_review.py --date 2026-08-05
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Step 1: defaults. Override any of these with a CLI flag; nothing here is
# read by the live trading system, so changing these is always safe.
# ---------------------------------------------------------------------------
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "apps" / "qwen_trade_software" / "backend" / "logs"
DEFAULT_TICK_DATA_DIR = Path(__file__).resolve().parent / "tick_data"
# Default: write beside that day's tick archive (no satellite reviews/ tree).
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "tick_data"


def parse_args():
    parser = argparse.ArgumentParser(description="Build one day's trade review report.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD, local date. Defaults to today.")
    parser.add_argument(
        "--log-dir",
        default=str(DEFAULT_LOG_DIR),
        help="Hot runtime logs (fallback if ticket archive missing for the day).",
    )
    parser.add_argument(
        "--tick-data-dir",
        default=str(DEFAULT_TICK_DATA_DIR),
        help="Permanent daily tick archive (model_training/tick_data).",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now().date()
    )
    return target_date, Path(args.log_dir), Path(args.tick_data_dir), Path(args.output_dir)


# ---------------------------------------------------------------------------
# Small helpers used by steps 2-4.
# ---------------------------------------------------------------------------
def read_jsonl(path: Path) -> list:
    """Read a JSONL file, skipping any blank or unparseable lines."""
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def local_date_of(iso_timestamp: str):
    """Convert a UTC ISO timestamp to this machine's local calendar date.

    Run this script on the same machine the trading system runs on so this
    lines up with how the dated log files are already named (local date,
    same convention as reviews-YYYY-MM-DD.jsonl).
    """
    return datetime.fromisoformat(iso_timestamp).astimezone().date()


def load_day_records(
    log_dir: Path,
    tick_data_dir: Path,
    base_name: str,
    target_date,
) -> list:
    """Prefer permanent tick_data archive, then hot runtime log, then legacy file."""
    archive_path = tick_data_dir / f"{target_date:%Y-%m-%d}" / f"{base_name}.jsonl"
    if archive_path.exists():
        return read_jsonl(archive_path)
    dated_path = log_dir / f"{base_name}-{target_date:%Y-%m-%d}.jsonl"
    if dated_path.exists():
        return read_jsonl(dated_path)
    legacy_path = log_dir / f"{base_name}.jsonl"
    matched = []
    for record in read_jsonl(legacy_path):
        timestamp = record.get("created_at_utc")
        if not timestamp:
            continue
        try:
            if local_date_of(timestamp) == target_date:
                matched.append(record)
        except ValueError:
            continue
    return matched


# ---------------------------------------------------------------------------
# Step 4: management-review snapshots are already written one file per day.
# ---------------------------------------------------------------------------
def load_reviews(log_dir: Path, tick_data_dir: Path, target_date) -> list:
    archive_path = tick_data_dir / f"{target_date:%Y-%m-%d}" / "reviews.jsonl"
    if archive_path.exists():
        return read_jsonl(archive_path)
    return read_jsonl(log_dir / f"reviews-{target_date:%Y-%m-%d}.jsonl")


# ---------------------------------------------------------------------------
# Step 5: index execution events by proposal_id, and count review coverage.
# ---------------------------------------------------------------------------
def index_executions(executions: list) -> dict:
    by_proposal = defaultdict(lambda: {
        "started": None, "fill": None, "closed": None, "skipped": None,
    })
    for event in executions:
        proposal_id = event.get("proposal_id")
        if not proposal_id:
            continue
        bucket = by_proposal[proposal_id]
        kind = event.get("event")
        if kind == "mt5_execution_started":
            bucket["started"] = event
        elif kind == "mt5_fill":
            bucket["fill"] = event
        elif kind == "mt5_execution_closed":
            bucket["closed"] = event
        elif kind == "mt5_execution_skipped":
            bucket["skipped"] = event
    return by_proposal


def count_review_coverage(reviews: list, execution_id: str) -> int:
    """How many management-review snapshots saw this position open.

    The reviewer tags each position's MT5 comment as QWEN_<suffix>, where
    <suffix> is the tail of the execution_id. Zero means this trade's
    outcome was decided before Qwen's management ever got a look at it.
    """
    if not execution_id:
        return 0
    suffix = execution_id.rsplit("-", 1)[-1]
    target_comment = f"QWEN_{suffix}"
    count = 0
    for entry in reviews:
        positions = entry.get("snapshot", {}).get("positions", [])
        if any(position.get("comment") == target_comment for position in positions):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Step 6: one narrative record per filled trade.
# ---------------------------------------------------------------------------
def build_trade_narratives(proposals: list, execution_index: dict, reviews: list) -> list:
    trades = []
    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        bucket = execution_index.get(proposal_id)
        if not bucket or not bucket["fill"] or not bucket["closed"]:
            continue  # never filled, or was still open when this ran

        qwen = proposal.get("qwen", {})
        plan = qwen.get("execution_plan", {})
        fill = bucket["fill"].get("fill", {})
        closed = bucket["closed"]
        execution_id = bucket["fill"].get("execution_id")

        trades.append({
            "proposal_id": proposal_id,
            "execution_id": execution_id,
            "entry_time_utc": fill.get("filled_at_utc"),
            "side": plan.get("side"),
            "confidence": qwen.get("confidence"),
            "reason": plan.get("reason") or qwen.get("summary"),
            "entry_low": plan.get("entry_low"),
            "entry_high": plan.get("entry_high"),
            "qwen_stop_ref": plan.get("stop_loss"),
            "qwen_target_ref": plan.get("take_profit"),
            "fill_price": fill.get("price"),
            "close_time_utc": closed.get("created_at_utc"),
            "close_reason": closed.get("reason"),
            "exit_price": closed.get("exit_price"),
            "net_pnl": closed.get("net_pnl"),
            "gross_pnl": closed.get("gross_pnl"),
            "peak_pnl": closed.get("peak_pnl"),
            "max_drawdown": closed.get("maximum_drawdown"),
            "holding_seconds": closed.get("position_holding_seconds", closed.get("holding_seconds")),
            "favorable_price_move": closed.get("favorable_price_move"),
            "peak_favorable_price_move": closed.get("peak_favorable_price_move"),
            "reviewed_count": count_review_coverage(reviews, execution_id),
        })
    trades.sort(key=lambda t: t["entry_time_utc"] or "")
    return trades


# ---------------------------------------------------------------------------
# Step 7: aggregate stats for the day.
# ---------------------------------------------------------------------------
def compute_day_summary(proposals: list, execution_index: dict, trades: list) -> dict:
    ready = [
        p for p in proposals
        if p.get("qwen", {}).get("execution_plan", {}).get("status") == "ready"
    ]
    skipped = sum(1 for bucket in execution_index.values() if bucket["skipped"])
    expired = sum(
        1 for bucket in execution_index.values()
        if bucket["closed"] and bucket["closed"].get("reason") == "signal_expired"
    )
    net_pnl = sum(t["net_pnl"] or 0.0 for t in trades)
    buy_ready = sum(1 for p in ready if p.get("qwen", {}).get("execution_plan", {}).get("side") == "buy")
    sell_ready = sum(1 for p in ready if p.get("qwen", {}).get("execution_plan", {}).get("side") == "sell")
    qwen_closed = sum(1 for t in trades if t["close_reason"] == "qwen_confirmed_close")
    bracket_closed = sum(
        1 for t in trades if t["close_reason"] in ("managed_or_safety_sl", "managed_or_safety_tp")
    )
    never_reviewed = sum(1 for t in trades if t["reviewed_count"] == 0)
    return {
        "ready_proposals": len(ready),
        "filled": len(trades),
        "expired_unfilled": expired,
        "skipped_runtime_validation": skipped,
        "net_pnl": round(net_pnl, 2),
        "buy_ready": buy_ready,
        "sell_ready": sell_ready,
        "closed_by_qwen_management": qwen_closed,
        "closed_by_bracket": bracket_closed,
        "filled_trades_never_reviewed": never_reviewed,
    }


# ---------------------------------------------------------------------------
# Step 8: render the markdown report (promote lessons via CURRICULUM §5).
# ---------------------------------------------------------------------------
SUMMARY_LABELS = [
    ("ready_proposals", "Proposals generated (ready)"),
    ("filled", "Proposals filled"),
    ("expired_unfilled", "Proposals expired unfilled"),
    ("skipped_runtime_validation", "Proposals skipped (runtime validation)"),
    ("net_pnl", "Net P&L (filled trades)"),
    ("buy_ready", "Ready proposals — buy"),
    ("sell_ready", "Ready proposals — sell"),
    ("closed_by_qwen_management", "Trades closed by confirmed Qwen management"),
    ("closed_by_bracket", "Trades closed by broker bracket / stop-out"),
    ("filled_trades_never_reviewed", "Filled trades that closed before any management review"),
]


def render_report(target_date, summary: dict, trades: list) -> str:
    lines = [f"# Daily Trade Review — {target_date:%Y-%m-%d}", ""]
    lines += [
        "Generated by `daily_trade_review.py`. Sections 1-2 are filled in;",
        "finish sections 3-5 by hand (or with Claude) — see "
        "`CURRICULUM_AND_DATA_PREP.md` §5.",
        "",
    ]

    lines += ["## 1. Day summary", "", "| Metric | Value |", "|---|---|"]
    for key, label in SUMMARY_LABELS:
        lines.append(f"| {label} | {summary[key]} |")
    lines.append("")

    lines += [
        "## 2. Trade-by-trade", "",
        "| # | Entry time (UTC) | Confidence | Fill | Exit | Reason | "
        "Net P&L | Hold (s) | Peak P&L | Reviewed |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, t in enumerate(trades, 1):
        entry_time = (t["entry_time_utc"] or "")[11:19]
        hold = round(t["holding_seconds"], 1) if t["holding_seconds"] is not None else ""
        fill_price = round(t["fill_price"], 3) if t["fill_price"] is not None else ""
        exit_price = round(t["exit_price"], 3) if t["exit_price"] is not None else ""
        lines.append(
            f"| {i} | {entry_time} | {t['confidence']} | {fill_price} | "
            f"{exit_price} | {t['close_reason']} | {t['net_pnl']} | "
            f"{hold} | {t['peak_pnl']} | {t['reviewed_count']} |"
        )
    lines.append("")

    lines += [
        "## 3. Candidate trading-skill lessons", "",
        "*(fill in by hand — promote into store if evidenced)*", "",
        "## 4. Candidate engineering findings", "",
        "*(fill in by hand — optional stage_02/04 rows)*", "",
        "## 5. Ledger updates made today", "",
        "*(fill in by hand — store version bump if doctrine changed)*", "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration: the whole flow, one step at a time.
# ---------------------------------------------------------------------------
def main():
    target_date, log_dir, tick_data_dir, output_dir = parse_args()          # 1
    proposals = load_day_records(log_dir, tick_data_dir, "paper-proposals", target_date)   # 2
    executions = load_day_records(log_dir, tick_data_dir, "paper-executions", target_date) # 3
    reviews = load_reviews(log_dir, tick_data_dir, target_date)             # 4
    execution_index = index_executions(executions)                           # 5
    trades = build_trade_narratives(proposals, execution_index, reviews)     # 6
    summary = compute_day_summary(proposals, execution_index, trades)        # 7
    report = render_report(target_date, summary, trades)                     # 8

    day_out = output_dir / f"{target_date:%Y-%m-%d}"
    day_out.mkdir(parents=True, exist_ok=True)
    output_path = day_out / "daily_review.md"
    output_path.write_text(report, encoding="utf-8")

    print(
        f"Reviewed {target_date:%Y-%m-%d}: {summary['filled']} filled trades, "
        f"net P&L {summary['net_pnl']}, "
        f"{summary['filled_trades_never_reviewed']} closed before any review."
    )
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
