# Daily Trade Review — YYYY-MM-DD

Copy this file to `model_training\reviews\YYYY-MM-DD_review.md` each day and
fill it in. See `DAILY_REVIEW_PROCESS.md` for the full loop this feeds into.

## 1. Day summary

| Metric | Value |
|---|---|
| Proposals generated (ready) | |
| Proposals filled | |
| Proposals expired unfilled | |
| Proposals skipped (runtime validation) | |
| Net P&L (filled trades) | |
| Buy / sell split | |
| Trades closed by confirmed Qwen management | |
| Trades closed by broker bracket / stop-out | |

## 2. Trade-by-trade

| # | Entry time | Confidence | Fill | Exit | Reason | Net P&L | Hold | Peak P&L |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |

(Add rows as needed. Reuse the reconstruction method from
`TRADE_REVIEW_2026-08-06.md` — join proposals + execution-started + fill +
closed events per proposal_id / execution_id.)

## 3. Candidate trading-skill lessons

Something about *market behavior or trading judgment* worth capturing —
not a code issue. One entry per candidate; be specific about which trade(s)
it's drawn from and how confident this is with a sample of one day.

- **Lesson:**
  **Evidence (trade #s):**
  **Confidence this generalizes (low/medium/high):**
  **Proposed edit to TRADING_KNOWLEDGE_BASE.md (section + wording):**
  **Decision (approved / rejected / needs more days):**

## 4. Candidate engineering findings

Something the *code* did that's unexpected, undocumented, or worth fixing.
These do NOT go into the trading knowledge base — track them separately
(e.g. as a `ResearchLab\PROVEN_HARMFUL_CHANGES.md` entry or a plain to-do).

- **Finding:**
  **Evidence:**
  **Where it lives in code:**
  **Status (needs fix / needs decision / tracked, not yet actioned):**

## 5. Ledger updates made today

- Lessons appended to `LESSON_LEDGER.md`: (list, or "none")
- Running count toward next retrain threshold: (copy from ledger header)
