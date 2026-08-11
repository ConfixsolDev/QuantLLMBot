# Topic 10 — Trade Management (in-trade decisions)

> **Sources read:** `grimes_art_science` pp.60, 74, 172, 227, 311, 327 · `brooks_trends` pp.11, 326 · `brooks_reversals` p.11 · `brooks_ranges` pp.138, 143 · `carter_mastering` pp.180, 201 · `douglas_zone` p.99 · `elder_trading_room` pp.138–147 · `dalton_mind_over_markets` pp.71, 170–171
> **Status:** v1 distillation, 2026-08-10. Written to close the largest gap in the curriculum — 6 of 508 rows carried a management action while in-trade decisions were costing more than entries were making.

---

## ⚠️ Calibration note — read this before using anything below

This topic is the one place where **our own measured data contradicts the instinct the books
encourage**, so the measurement comes first.

From 2026-08-10 live paper trading (27 closed trades):

| Exit path | n | avg P&L |
|---|---|---|
| Left alone until the target was reached | 3 | **+247.38** |
| Closed on the model's own judgement | 8 | **−20.22** |
| Stopped out at the fixed bracket | 5 | −161.60 |

**Discretionary closing was negative-expectancy.** Every author below endorses exiting early when
the idea stops working — and they are right — but *our* implementation of that permission destroyed
value. The gap is not in the principle, it is in the **test**. A trader (or a model) that exits
because it feels uncomfortable will exit far more often than one that exits because a named
condition was met, and it will do so preferentially at the worst moments.

Douglas explains the mechanism precisely: *"You will gather evidence for the trade if your fear of
missing out is greater than your fear of losing. And you will gather information against the trade
if your fear of losing is greater than your fear of missing out"* (`douglas_zone p.99`). An anxious
position-holder **manufactures** the evidence that justifies the exit it already wants. That is
almost certainly what the −20.22 represents.

Two further measurements that bound everything here:

- **Stops sat inside the invalidation.** Across those trades, winners' stops averaged **1.71**
  inside the level that would prove the idea wrong; losers' **3.76**. The worst case sat **8.46**
  inside and was closed in 81 seconds without the thesis ever being tested.
- **Speed.** The two fastest stop-outs died in **22s** and **50s**. Any management rule that
  requires a model round-trip (16–31s on a 30s cycle) cannot act on those trades at all.

**Therefore:** every rule below must be expressible as a *named, checkable condition on closed
price* — not as a judgement of how the trade feels. Where a rule cannot be stated that way, it is
listed under Gaps instead of Rules.

---

## Core concepts

**C1 — Scratching.** Exiting for a small win or loss before the stop is reached, because the
premise has weakened. Grimes: *"developing price action may suggest that the trend is losing
integrity. If this happens, it is not necessary to hold the trade to the original stop-loss level.
It is often advisable to scratch the trade, exiting for a small win or loss, and to wait for better
opportunities"* (`grimes_art_science p.172`). This is the doctrinal basis for early close. Note what
it is keyed to: *developing price action*, i.e. observable structure — not P&L.

**C2 — The always-in flip (the strongest available invalidation test).** Brooks defines always-in
as: *"If at any time you are forced to decide between initiating a long or a short trade and are
confident in your choice, then the market is in always-in mode"* (`brooks_reversals p.11`). This
converts into an operational test for an open position:

> **Would I enter the opposite side right now, at this price, with confidence?**

If yes, the original idea is dead and the position should be closed. If the honest answer is "no,
but I am uncomfortable", the idea is intact and the position stays. This is the single most useful
rule in this topic because it is symmetric, requires no P&L input, and cannot be satisfied by
discomfort alone.

**C3 — The trader's equation applied to exits.** Brooks: *"A trader should exit a trade only when
the chance of success times the potential reward is significantly greater than the chance of
failure times the risk"* (`brooks_trends p.326`). Exiting is itself a trade decision and must clear
a bar. Restated for an open position: close early only when *remaining* reward × probability no
longer exceeds *remaining* risk × probability. Crucially this makes "the TP will not be reached" a
**quantitative claim about the remaining distance**, not a mood.

**C4 — Structural invalidation vs adverse excursion.** A position is wrong when the level that
defined it fails on a *closed* candle of that level's own timeframe. It is not wrong because price
moved against it. Grimes' entries are built around a *"well-defined risk point"* (`p.60`); the risk
point failing is the exit, and nothing short of it is.

**C5 — The stop ladder.** Grimes' sequence: tighten under structure, then move to breakeven *"so
that the worst intended outcome is a scratch"*, with the warning *"Remember that gap risk exists;
the actual loss may be larger"* (`p.327`). Brooks describes the same with partials: take part off at
a measured target, move the stop to breakeven or tighten it, and hold the remainder
(`brooks_ranges p.138`).

**C6 — Time stops.** Carter runs an explicit clock: *"Time passes by quickly, and my time stop
expires. I exit at the market"* (`carter_mastering p.201`), and distinguishes it from the hard stop:
*"By 'stopped out,' I mean that my physical hard stop is hit, as opposed to the time stop"*
(`p.180`). A thesis has a lifespan; an idea that has not begun to work within its frame's window has
been falsified by silence rather than by price.

**C7 — Consistency dominates rule choice.** Grimes, after listing three legitimate stop plans:
*"Whichever plan makes sense to you, the important thing is to execute it consistently"* (`p.311`).
For a bot this is decisive — a mediocre rule applied uniformly beats a good rule applied when it
feels right, because only the former produces a measurable expectancy.

---

## Distilled rules

Each rule is stated so a machine can evaluate it without reference to open P&L.

| # | Rule | Source | Machine test |
|---|---|---|---|
| **R1** | Close when the structural invalidation fails on a closed candle of its own timeframe. | C4, `grimes p.60` | `closed_candle(tf_of(level)).close` beyond `level` |
| **R2** | Close when the always-in direction flips — i.e. the opposite entry would now be taken with confidence. | C2, `brooks_reversals p.11` | opposite-side setup present at a named level **and** its own closed response exists |
| **R3** | Close when remaining reward no longer clears remaining risk. | C3, `brooks_trends p.326` | `(dist_to_tp × p_success) < (dist_to_sl × p_fail)` using structure, not feeling |
| **R4** | Close when the frame's time budget expires without the thesis progressing. | C6, `carter pp.180, 201` | `held > time_budget(frame)` **and** `structural_progress_pct < threshold` |
| **R5** | Do **not** close on adverse excursion alone. Drawdown inside the risk point is the cost of the trade, not evidence against it. | Calibration note, `douglas p.99` | reject any close whose only justification is unrealised P&L |
| **R6** | Do **not** close on a forming candle. Only closed candles carry invalidation. | C4, house rule across topics 2–4 | `candle.state == closed` |
| **R7** | The stop may be tightened toward breakeven once structure permits; the worst intended outcome becomes a scratch. | C5, `grimes p.327` | new structure formed behind price |
| **R8** | Gap risk means a stop is a request, not a guarantee. Never size on the assumption the stop holds exactly. | `grimes p.327` | risk model uses stop distance, never "max loss = stop" |
| **R9** | Apply whichever exit policy is chosen uniformly across every trade in the session. | C7, `grimes p.311` | policy id logged per trade; deviation is an incident |

**R1, R2 and R4 are the three legitimate reasons to close early.** Anything else is R5.

---

## Worked examples

### 1 — CLOSE: invalidation failed (R1)
Short from an M30 zone, invalidation `H1_PREVIOUS_HIGH`. An H1 candle **closes** above it.
→ Close. The level that defined the trade has failed on its own timeframe. Not a judgement call.

### 2 — HOLD: adverse excursion, invalidation intact (R5)
Same short. Price runs 60% of the way to the stop but no H1 candle closes above the level.
→ Hold. This is the trade costing what it was always going to cost. Closing here is the −20.22.

### 3 — CLOSE: always-in flip (R2)
Short from an M30 zone. Price builds a higher low at a named support and prints a closed M15
bullish response there. Asked honestly, the long entry would now be taken with confidence.
→ Close. The market is no longer the one the idea was built for.

### 4 — HOLD: uncomfortable, but no opposite setup (R2, R5)
Short; price chops sideways above entry, several bull bars, but no closed response at any named
support and no long setup that would be entered.
→ Hold. Discomfort is not a flip.

### 5 — CLOSE: reward no longer justifies remaining risk (R3)
Short with 1.2 remaining to target and 4.0 remaining to stop after the stop was widened to
structure. Remaining reward:risk is now 0.3.
→ Close or scale. The trade's arithmetic has inverted even though nothing is "wrong".

### 6 — CLOSE: time stop with no progress (R4)
M30-framed trade, 4-hour budget. After 4 hours `structural_progress_pct` is under 15% and price sits
where it entered.
→ Close. The thesis has been falsified by silence.

### 7 — HOLD: time elapsed but thesis progressing (R4)
Same trade, but price has covered 70% of the distance to target.
→ Hold. The clock exists to kill dead ideas, not working ones.

### 8 — PROTECT not CLOSE: structure formed behind price (R7)
Short is 60% to target; a new lower high forms and closes.
→ Move the stop behind that lower high. The worst outcome becomes a scratch, and the target is
still live. This is the correct response to "I want to protect this" — not a close.

### 9 — DO NOT REOPEN: closed early, then regret
A trade was closed on R2 and price then resumes in the original direction.
→ No re-entry without a fresh closed response at a named level. Chasing a scratched idea is a new
trade and must clear the entry bar on its own.

---

## Contradictions between sources

| Position A | Position B | Resolution for this bot |
|---|---|---|
| **Grimes:** scratch early and often when the trend loses integrity; a good plan "will encourage the trader to be responsive to developing market conditions" (`p.172`). | **Our own data:** responsiveness cost −20.22 per intervention against +247.38 for leaving trades alone. | Keep Grimes' permission but bind it to R1/R2/R4. "Responsive" means responsive *to named closed structure*, never to price discomfort. The measurement is the referee, not the author. |
| **Brooks:** the trader's equation should govern exits continuously (`brooks_trends p.326`). | **Douglas:** a fearful trader will always find the evidence that makes the equation say "exit" (`douglas_zone p.99`). | Compute the equation from *structural distances* (distance to named target vs named invalidation), never from a subjective probability the model supplies in the moment. Douglas' warning is why the inputs must be external. |
| **Carter:** hard time stops, exit at market when the clock expires (`pp.180, 201`). | **Dalton:** brackets are the normal state 70–80% of the time (`dalton_mind_over_markets p.71`); a thesis can be correct and dormant. | Time stop applies only when `structural_progress_pct` is also low (R4). Time alone never closes a trade that is working. |
| **Brooks/Grimes:** partials plus breakeven (`brooks_ranges p.138`, `grimes p.327`). | Single-position runtime; no partials available. | Implement the breakeven half only (R7). Record the absence of partials as a known limitation, not as a rule silently dropped. |

---

## Gaps

Things this topic needs that no book in the corpus supplies:

1. **Any measured expectancy for early exit versus holding to target, on gold, intraday.** Every
   author asserts scratching is valuable; none reports the differential. Our own n=11 split says the
   opposite of the doctrine. **R1/R2/R4 must be measured per configuration before being trusted** —
   `configuration_ledger.py` is the instrument.
2. **A threshold for R3.** "Significantly greater" (`brooks_trends p.326`) is not a number. Until
   measured, use the entry-time minimum reward:risk as the floor and log every R3 close for review.
3. **Time budgets per frame.** Carter runs a clock but never states its length in a transferable
   way. Current values in `management_policy.TIME_STOP_SECONDS` are estimates, not findings.
4. **What counts as an always-in flip for an algorithm.** Brooks' test is explicitly a
   confidence judgement by a human. R2's machine form (opposite setup at a named level with its own
   closed response) is our construction, not his, and may be stricter or looser than he intends.

---

## Learning outcome

The model should be able to answer, for any open position, exactly one question:

> **Has a named condition been met that ends this trade — R1 invalidation, R2 flip, R3 arithmetic,
> or R4 time — or am I simply uncomfortable?**

and to name which one, with the closed candle and level that satisfied it. A close it cannot
attribute to R1–R4 is an R5 violation and should not be taken.

---

## Implementation

- `management_policy.py` — exit taxonomy, adjustment validation, risk ceiling. R1 maps to
  `INVALIDATION_CLOSED_THROUGH`, R4 to `TIME_STOP`, R5 is what the instrumentation is for.
- `store/sop.md → prompt:qwen_trade_management` — the live contract the model reads.
- `configuration_ledger.py` — records which exit reason produced which P&L, per configuration, so
  the calibration note above can be recomputed weekly rather than assumed.
