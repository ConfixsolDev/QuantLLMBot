# XAUUSD Trading Cycle (Qwen + Trade Plus)

This is the operational cycle the live system and future models must follow.
Full rules are in `store/core_skill.md` and `store/sop.md`.

## 1. Session and HTF context (before any entry)

- Identify UTC session: Asia, pre-London, London, overlap, New York, off-session.
- Read H4 → H1 → M30 → M15 structure before M5/M1 timing.
- Mark support/resistance as **zones**; levels need a fresh price response.
- London receives completed Asia high, low, and bias.

## 2. Level behavior at a meaningful zone

At each level, compare three paths:

1. **Continuation / acceptance** — closed break + retest on the level's timeframe.
2. **Rejection / reversal** — respected zone with room to the next level.
3. **Unfinished retracement** — wait; do not force an entry.

A valid trade needs several independent reasons, room to the next level, and
structural stop/target — not EMA cross alone.

## 3. Context cache qualification (system gate)

Before entry proposals can go `ready`:

1. **Warmup** — load playbook + history chunks into Ollama context cache.
2. **Session warmup** — session-specific facts aligned to current UTC window.
3. **Context challenge** — Qwen must answer structural questions from cache only.
4. **Minute shadow** — derived minute packets match live MT5 feed.

If cache status is `blocked`, the system waits — no paper execution.

## 4. Entry decision (reviewer)

Each M1 (or configured) tick:

1. Build closed-data snapshot (no look-ahead).
2. Send stable prefix (`core_skill.md` + `sop.md` section `qwen_cached_entry`) + dynamic facts.
3. Qwen returns JSON: action, confidence, SL/TP, reasons.
4. Validation checks contract; proposal logged as `wait` or `ready`.

## 5. Paper execution (paper runner)

- Only `ready` proposals with passing validation are sent to MT5 demo.
- Executions and outcomes logged to `logs/paper-executions-*.jsonl`.

## 6. In-trade management (trade management)

Open positions reviewed on schedule:

- Prompt section `qwen_trade_management` from `sop.md`.
- Actions: hold, tighten stop, partial close, full exit — each with structural reason.

## 7. Learning (offline, human-in-the-loop)

After the session:

1. Run `daily_trade_review.py` on today's logs.
2. Record patterns in `LESSON_LEDGER.md`.
3. Propose store/sop edits only after repeated evidence — not one trade.
4. Re-export LoRA → Ollama when doctrine changes materially.

## Quick reference: what blocks trading

| Blocker | Fix |
|---------|-----|
| `context_cache.status = blocked` | Run cache qualification (`run-qualification.ps1`) |
| All proposals `wait` | Cache not ready or model confidence 0 |
| Pre-London / off-session | Doctrine default — no new entry |
