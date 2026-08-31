# Trade Review Narrative: From Raw P&L to Reasoning

**Date:** 2026-08-28  
**Companion to:** PROMPT_REDESIGN_PLAN.md (entry prompt narrative)  
**Status:** Design Complete → Ready for Implementation

## Problem Statement

Post-trade analysis currently shows raw P&L (e.g., `-79.58 total, 7 wins, 4 losses`) without explaining *why* trades happened that way. Qwen cannot reason about decision quality from numbers alone.

Current questions Qwen cannot answer:
- "Did we enter well but exit poorly?"
- "Was that loss because the thesis broke or because we stopped out too tight?"
- "Which types of setups work better (entry zone, holding time, market condition)?"
- "Should we adjust confidence thresholds or entry criteria?"

## Solution: Trade Review Narrator

Convert each closed trade into a **story** describing entry logic → price action → exit reason → quality assessment.

### Before (Raw Data)
```json
{
  "execution_id": "demo-20260828T080405",
  "entry_price": 4605.25,
  "exit_price": 4604.12,
  "gross_pnl": -56.48,
  "peak_pnl": 125.33,
  "maximum_drawdown": -181.81,
  "holding_seconds": 426,
  "reason": "zone_accepted_through_on_m1"
}
```
→ **Qwen cannot reason:** Is this a bad entry or a good entry that got stopped out?

### After (Narrative)
```
SELL at 4605.25 (H1_LIVE_H_4605). Reason: zone_rejection. Entry at 08:04 UTC.
Price moved 125pt in our favor, then 182pt adverse before close.
Stop hit at 4604.12 (wick below HL). LOSS: -56 (-45pt) in 7min.
Quality: Good risk - stopped quickly despite adverse move.
```
→ **Qwen reasons:** "Good entry, thesis broke before target, risk was managed correctly."

## Architecture

### Core Functions

**`trade_narrative_from_execution(execution, proposal)`**
- Converts one mt5_execution_closed event into a TradeNarrative object
- Infers exit reason (target_hit, stop_touched, thesis_broken, time_exit)
- Calculates quality assessment (strong, weak, good risk, mixed)
- Handles missing data gracefully

**`compose_trade_review_narrative(closed_trades, proposals)`**
- Builds narratives for multiple trades
- Adds summary statistics (win rate, count)
- Organizes as sequential stories

**`prompt_section_trade_review(...)`**
- Formats output as a ready-to-insert prompt section
- Includes analytical questions for Qwen

### Integration Points

#### 1. **Daily/Weekly Trade Review Report**
**File:** (TBD - likely trade_manager.py or a new trade_review_worker.py)

```python
import trade_review_narrator

# Load today's closed trades
closed = load_closed_trades("2026-08-28")  # 72 trades
proposals = load_proposals("2026-08-28")   # 229 proposals

# Generate narrative
narrative = trade_review_narrator.prompt_section_trade_review(closed, proposals)

# Send to Qwen for analysis
analysis_prompt = f"""
Review these trades and explain what worked and what didn't.

{narrative}

Then recommend three changes for tomorrow's session.
"""

qwen_response = call_qwen(analysis_prompt)
```

#### 2. **Session Feedback Loop**
**File:** (TBD - likely session_planner.py or market_memory_worker.py)

After each session (or daily), feed trade narratives back to improve:
- Session plan confidence (were the predicted trades actually good?)
- Entry criteria (do certain entry zones work better?)
- Risk sizing (are stops too tight or too loose?)

```python
# At end of trading day
session_trades = get_session_trades("2026-08-28")
review = trade_review_narrator.compose_trade_review_narrative(session_trades)

# Store for learning
memory_worker.record_session_review(
    date="2026-08-28",
    narrative=review,
    session_plan_id="sp_123",
    confidence_feedback=score_plan_vs_reality(session_plan, trades),
)
```

#### 3. **Live Trade Tracking** (Optional)
**File:** paper_runner.py or execution_monitor.py

As trades close in real-time, build narrative updates:

```python
# After each mt5_execution_closed event
execution = {...}
proposal = proposals.get(execution['proposal_id'])
narrative = trade_review_narrator.trade_narrative_from_execution(execution, proposal)

# Log or display for real-time monitoring
logging.info(f"TRADE CLOSED: {narrative.as_narrative()}")
```

## Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Trade review understanding | "7 wins, 4 losses" | "7 strong entries, 2 poor exits, 2 stopped out quickly" |
| Qwen reasoning on own trades | Limited (numbers only) | Full (narrative causality) |
| Feedback loop quality | No feedback to entry model | Clear recommendations for threshold/criteria changes |
| Session learning velocity | Slow (manual interpretation) | Fast (automated narrative analysis) |

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Narrative inference wrong (exit reason) | Include raw data fields as fallback; validate against actual execution logs |
| Quality assessment too subjective | Use quantitative thresholds (pnl % of favorable move, time to stop, etc.) |
| Narrative doesn't feed back | Requires separate learning pipeline; build parallel to this |

## Implementation Timeline

### Phase 1: Core Module (DONE)
- ✅ Created `trade_review_narrator.py`

### Phase 2: Integration (2-4 hours)
- Find trade review function (likely trade_manager.py or TBD)
- Wire in `compose_trade_review_narrative()`
- Test on today's 72 trades (validate narrative quality)

### Phase 3: Prompt Integration (2 hours)
- Add trade_review_narrator output to daily/weekly Qwen analysis prompts
- Validate Qwen's recommendations make sense

### Phase 4: Feedback Loop (1-2 weeks)
- Wire Qwen's analysis back into session planner confidence/thresholds
- Measure impact on next session's trade quality

## Success Criteria

1. ✅ Trade narratives match human interpretation of trade quality
2. ✅ Qwen can identify win/loss patterns without seeing raw P&L
3. ✅ Recommendations from Qwen are actionable (e.g., "tighten stops on M1 entries")
4. ✅ Feedback loop improves session plan accuracy over 1-2 weeks

## Files Created

- `trade_review_narrator.py` — NEW (600 lines)
- `TRADE_REVIEW_REDESIGN_PLAN.md` — This file

## Files to Modify

- `trade_manager.py` (or TBD trade review module) — Integrate `compose_trade_review_narrative()`
- `build_manifest.py` — Will auto-pick up trade_review_narrator.py on next run

## Next Steps

1. Identify where trade review currently happens (trade_manager.py? analysis_worker.py?)
2. Wire in `trade_review_narrator` import and function call
3. Run on today's 72 closed trades, validate narrative quality
4. Get feedback from you on whether the stories match reality

## Synergy with Entry Prompt Redesign

These two redesigns work together:
- **Entry prompt redesign** (chart_narrative_composer) → Better entry reasoning → Cleaner trades
- **Trade review redesign** (trade_review_narrator) → Better feedback → Better session planning → Better entries

Together they close a feedback loop: *reasoning (entry) → execution (trade) → reasoning (review) → learning (adjustment)*
