# Tick data — permanent learning archive

**Tick data** in QuantLLMBot means **each timed observation** the system records:
price (bid/ask), structure context, Qwen prompt/response, and the decision at
that moment. One line in these files = one tick of the trading process.

This is **not** MT5 order tickets (broker position IDs). Those appear inside
records as `mt5_position_id` when relevant.

## Daily folder layout

```
tick_data/
  2026-08-07/
    paper-proposals.jsonl   ← entry decision ticks (price + plan)
    paper-executions.jsonl  ← fill/close ticks
    reviews.jsonl           ← management cycle ticks
    qwen-decisions.jsonl    ← unified decision tree per price/time
    qwen-io.jsonl           ← full Qwen request/response per call
    mt5-io.jsonl            ← MT5 API ticks (orders, quotes)
    manifest.json
```

## What keeps growing (Part 1)

After code matures, **tick_data/** is the main asset that grows every session —
used to compare how decisions changed at different prices over 30, 60, 90+ days.

## Raw market ticks

The live cache also stores MT5 bid/ask ticks in
`apps/qwen_trade_software/backend/cache/market_context.sqlite3` (`ticks` table).
Decision JSONL here links each Qwen call to the price/context at that instant.

## Policy

- **Never auto-deleted**
- Dual-written from the live app on every tick
- Back up externally; not committed to git
