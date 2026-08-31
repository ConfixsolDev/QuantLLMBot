"""Convert closed trade data into narrative for post-trade review and learning.

Once a trade closes, the system needs to explain to Qwen (and humans) what
happened and why. This module converts raw P&L, entry/exit prices, and
execution timestamps into a coherent story that enables reasoning about
trade quality, decision calibration, and pattern learning.

Design: Every trade gets ONE narrative paragraph explaining:
1. Why it was entered (structural confluence, signal, timing)
2. What price did during the hold (ran in our favor, reversed, churned)
3. Why it was exited (target hit, stop touched, thesis broken, time exit)
4. What the outcome means (good entry bad exit, bad entry lucky close, etc.)

This feeds back into Qwen's learning loop so it can reason about decision
quality independent of raw P&L (which is noisy/lucky).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class TradeNarrative:
    """One closed trade told as a story."""
    execution_id: str
    proposal_id: str
    symbol: str
    side: str  # "buy" | "sell"
    entry_reason: str  # structured signal from proposal
    entry_time_utc: str
    entry_price: float
    entry_zone: str  # e.g., "D1_PREVIOUS_LOW", "H4_ORDER_BLOCK"

    exit_time_utc: str
    exit_price: float
    exit_reason: str  # "target_hit" | "stop_touched" | "thesis_broken" | "time_exit"
    exit_trigger: str  # structural reason (e.g., "break of HL", "FVG touched")

    holding_time_minutes: int
    gross_pnl: float
    pnl_points: float
    max_favorable: float
    max_adverse: float

    win: bool  # P&L > 0

    def as_narrative(self) -> str:
        """Render as 3-4 sentence story."""
        lines = []

        # Entry story
        lines.append(
            f"{self.side.upper()} at {self.entry_price:.2f} ({self.entry_zone}). "
            f"Reason: {self.entry_reason}. Entry at {self.entry_time_utc.split('T')[1][:5]} UTC."
        )

        # Price action during hold
        if self.max_favorable > 0 and self.max_adverse < 0:
            lines.append(
                f"Price moved {self.max_favorable:.0f}pt in our favor, "
                f"then {self.max_adverse:.0f}pt adverse before close."
            )
        elif self.max_favorable > abs(self.max_adverse):
            lines.append(
                f"Trade ran {self.max_favorable:.0f}pt favorable. "
                f"Max draw {self.max_adverse:.0f}pt."
            )
        else:
            lines.append(
                f"Pressure {self.max_adverse:.0f}pt from entry. "
                f"Best reached {self.max_favorable:.0f}pt."
            )

        # Exit story
        exit_desc = {
            "target_hit": "Target reached",
            "stop_touched": "Stop hit",
            "thesis_broken": "Thesis invalidated",
            "time_exit": "Time-based exit",
        }.get(self.exit_reason, self.exit_reason)

        outcome = "WIN" if self.win else "LOSS"
        lines.append(
            f"{exit_desc} at {self.exit_price:.2f} ({self.exit_trigger}). "
            f"{outcome}: {self.gross_pnl:+.0f} ({self.pnl_points:+.0f}pt) in {self.holding_time_minutes}min."
        )

        # Quality assessment
        if self.win and self.pnl_points >= 0.7 * abs(self.max_favorable):
            quality = "Strong: captured most of favorable move"
        elif self.win and self.pnl_points < 0.3 * abs(self.max_favorable):
            quality = "Weak: early exit missed move"
        elif not self.win and abs(self.pnl_points) <= 0.5 * abs(self.max_adverse):
            quality = "Good risk: stopped quickly"
        else:
            quality = f"Mixed: {self.pnl_points:+.0f}pt realized from {self.max_favorable:.0f}/{self.max_adverse:.0f}pt range"

        lines.append(f"Quality: {quality}.")

        return " ".join(lines)


def trade_narrative_from_execution(
    execution: Mapping[str, Any],
    proposal: Mapping[str, Any] | None = None,
) -> TradeNarrative:
    """Build a narrative from a closed execution record.

    Args:
        execution: mt5_execution_closed event from execution log
        proposal: paper-proposal record (optional, for entry context)

    Returns:
        TradeNarrative object ready to be inserted into trade review prompt
    """
    prop = proposal or {}
    qwen_plan = (prop.get('qwen') or {}).get('execution_plan') or {}

    # Entry context
    entry_reason = qwen_plan.get('reason', 'structural_entry')
    entry_zone = qwen_plan.get('entry_low_id') or qwen_plan.get('zone_id') or 'unmarked'
    entry_side = (prop.get('qwen') or {}).get('bias') or qwen_plan.get('side') or 'unknown'

    # Execution data
    entry_price = float(execution.get('entry_price') or 0)
    exit_price = float(execution.get('exit_price') or 0)
    gross_pnl = float(execution.get('gross_pnl') or 0)
    peak_pnl = float(execution.get('peak_pnl') or 0)
    max_dd = float(execution.get('maximum_drawdown') or 0)

    # Calculate directional PnL
    if entry_side.lower() in ('buy', 'long'):
        pnl_points = exit_price - entry_price
        max_favorable = peak_pnl / abs(entry_price) * 100 if entry_price else 0
        max_adverse = -max_dd / abs(entry_price) * 100 if entry_price else 0
    else:
        pnl_points = entry_price - exit_price
        max_favorable = peak_pnl / abs(entry_price) * 100 if entry_price else 0
        max_adverse = -max_dd / abs(entry_price) * 100 if entry_price else 0

    # Exit reason inference (if not explicit in execution, infer from context)
    close_reason = execution.get('reason', 'unknown')
    if 'target' in close_reason.lower():
        exit_reason = 'target_hit'
    elif 'stop' in close_reason.lower():
        exit_reason = 'stop_touched'
    elif 'break' in close_reason.lower() or 'invalidat' in close_reason.lower():
        exit_reason = 'thesis_broken'
    elif 'time' in close_reason.lower():
        exit_reason = 'time_exit'
    else:
        exit_reason = 'thesis_broken' if max_dd > 0 else 'target_hit'

    # Infer exit trigger from reason
    exit_trigger = close_reason.split('_')[1] if '_' in close_reason else close_reason

    # Holding time
    entry_time = execution.get('created_at_utc', '')
    exit_time = execution.get('closed_at_utc', entry_time)
    holding_minutes = 0
    if entry_time and exit_time:
        try:
            entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
            exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
            holding_minutes = int((exit_dt - entry_dt).total_seconds() / 60)
        except:
            pass

    return TradeNarrative(
        execution_id=execution.get('execution_id', 'unknown'),
        proposal_id=execution.get('proposal_id', 'unknown'),
        symbol=execution.get('symbol', 'XAUUSDr'),
        side=entry_side,
        entry_reason=entry_reason,
        entry_time_utc=execution.get('created_at_utc', ''),
        entry_price=entry_price,
        entry_zone=entry_zone,
        exit_time_utc=exit_time,
        exit_price=exit_price,
        exit_reason=exit_reason,
        exit_trigger=exit_trigger,
        holding_time_minutes=holding_minutes,
        gross_pnl=gross_pnl,
        pnl_points=pnl_points,
        max_favorable=max_favorable,
        max_adverse=max_adverse,
        win=gross_pnl > 0,
    )


def compose_trade_review_narrative(
    closed_trades: list[Mapping[str, Any]],
    proposals: dict[str, Mapping[str, Any]] | None = None,
) -> str:
    """Build a review of multiple closed trades as a cohesive narrative.

    Args:
        closed_trades: List of mt5_execution_closed events
        proposals: Dict keyed by proposal_id for context

    Returns:
        A narrative summary ready to be included in a trade review report
    """
    proposals = proposals or {}
    narratives = []

    for execution in closed_trades:
        pid = execution.get('proposal_id')
        proposal = proposals.get(pid) if pid else None
        narrative = trade_narrative_from_execution(execution, proposal)
        narratives.append(narrative.as_narrative())

    # Compose summary stats
    wins = sum(1 for n in narratives if 'WIN' in n)
    losses = sum(1 for n in narratives if 'LOSS' in n)

    header = f"""TRADE REVIEW SUMMARY
==================
Total: {len(narratives)} trades | Wins: {wins} | Losses: {losses} | Win rate: {wins/len(narratives)*100:.0f}%

INDIVIDUAL TRADE NARRATIVES:
"""

    trade_details = "\n\n".join(
        f"[{i+1}] {n}"
        for i, n in enumerate(narratives)
    )

    return header + "\n" + trade_details


def prompt_section_trade_review(
    closed_trades: list[Mapping[str, Any]],
    proposals: dict[str, Mapping[str, Any]] | None = None,
    title: str = "COMPLETED TRADES FOR ANALYSIS",
) -> str:
    """Format trade review as a prompt section for Qwen.

    Returns:
        A complete section ready to insert into a trade analysis prompt
    """
    narrative = compose_trade_review_narrative(closed_trades, proposals)
    return f"""{title}:

{narrative}

Based on these trade narratives, analyze:
1. Which trades had good entry logic but poor execution (early exit, bad exit timing)?
2. Which trades had poor entry logic but got lucky (thesis broken but still won)?
3. What patterns emerge in wins vs losses (entry zone, holding time, exit reason)?
4. What should the system adjust for the next session?
"""
