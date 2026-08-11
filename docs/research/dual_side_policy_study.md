# Would dual-side observations improve the system?

**Question asked:** does having the model assess both directions (and letting code
pick) improve efficiency?

**Short answer:** the data cannot show that it would, and two of the three
mechanisms it adds are already in place or inert. The binding constraint is not
the policy architecture — it is that 71 closed trades across 4 days of changing
code cannot evaluate any architectural change at all.

Date: 2026-08-11 · Sample: 71 closed trades with settled P&L, 3,694 entry
decisions, 2026-08-06 to 2026-08-11.

---

## 1. What the sample actually is

| day | trades | net | avg | win |
|---|---|---|---|---|
| 2026-08-06 | 15 | +53.95 | +3.60 | 47% |
| 2026-08-07 | 8 | −11.00 | −1.37 | 62% |
| 2026-08-10 | 42 | −1033.75 | −24.61 | 36% |
| 2026-08-11 | 6 | −32.45 | −5.41 | 33% |
| **total** | **71** | **−1023.25** | **−14.41** | **41%** |

Every finding below has to survive the fact that the code changed on each of
these days. Most do not.

## 2. Does the model's confidence predict the outcome?

Unanswerable from this data.

| confidence | n | net | avg | win |
|---|---|---|---|---|
| 60–69 | 6 | −32.45 | −5.41 | 33% |
| 70–79 | 15 | +366.40 | +24.43 | 53% |
| 80+ | 50 | −1357.20 | −27.14 | 38% |

Pearson r = −0.10. That looks like an inversion — high confidence, worse
results — and it survives trimming the largest wins and losses from both
groups.

**But it is a date effect.** Confidence band is almost perfectly confounded
with day: 08-06 supplies 14 of the 21 sub-80 trades, 08-10 supplies 41 of the
50 high-confidence trades. The comparison is 08-06 versus 08-10, not low
confidence versus high. Within a single day there is no usable contrast.

The honest statement: model confidence is **unvalidated**, in either direction.
It has never been tested against outcome on a stable codebase.

## 3. Would forcing a committed side help?

No — that filter already exists.

Across all 3,694 entry decisions:

| bias | count | share |
|---|---|---|
| conditional | 2,790 | 75.5% |
| buy | 507 | 13.7% |
| sell | 397 | 10.7% |

The model already declines to pick a side three quarters of the time, and
**all 71 filled trades came from a committed directional call.** Conditional
reads never reach execution. The main intuitive benefit of dual-side scoring —
"stop trading when the two sides are close" — is already enforced by the
existing funnel.

## 4. Frame coherence — the one v2 rule with a testable history

`decide()` refuses an entry when the entry-zone frame and the invalidation
frame are more than `MAX_INVALIDATION_GAP = 4` steps apart.

| gap | n | net | avg | win |
|---|---|---|---|---|
| 0 | 15 | −763.15 | −50.88 | 20% |
| 1 | 10 | −6.30 | −0.63 | 40% |
| 2 | 13 | −159.85 | −12.30 | 38% |
| 3 | 4 | −284.40 | −71.10 | 25% |
| 4 | 2 | −157.00 | −78.50 | 0% |
| >4 | **0** | — | — | — |

**No trade in the sample exceeds the threshold**, so the rule would have
refused none of them. Worse, the relationship is not monotonic — gap 0, the
perfectly coherent case, is the worst bucket in the table.

An earlier analysis in this project reported gap ≥ 5 costing −1070 across 14
trades. Those trades are not in this dataset. That figure should be treated as
unreplicated until the query that produced it is re-run against the same join
used here.

## 5. Is the sell side weak?

The widely-held assumption in this project is that sell is the weak side in a
bullish regime. **Pooled data agrees. Within-day data reverses it.**

Pooled: buy n=33 avg −9.01 win 52% · sell n=38 avg −19.10 win 32%

Within day, on the only two days where both sides traded:

| day | buy | sell |
|---|---|---|
| 2026-08-10 | n=8 avg −35.26 | n=34 avg **−22.11** |
| 2026-08-11 | n=2 avg −29.15 | n=4 avg **+6.46** |

Sell underperformed buy on **0 of the 2** days where both traded. The pooled
result is a mix artefact: sells cluster on 08-10, a bad day; buys dominate the
flat early days. Sell has a lower win rate but a better average — it loses
less per loss.

This does not prove sell is fine. It does mean the case for penalising the sell
side rests on evidence that disappears under the most basic control.

## 6. The constraint that actually binds

Per-trade P&L: mean −14.41, **standard deviation 152.62**. The spread between
trades is 10.6× the average result.

Trades required per arm to detect an improvement at 80% power:

| improvement | trades needed per arm |
|---|---|
| +$10/trade | 3,653 |
| +$20/trade | 914 |
| +$30/trade | 406 |
| +$50/trade | 147 |
| +$80/trade | 58 |

At roughly 20 trades a day, distinguishing a +$20/trade improvement takes about
**three months per arm**. The current sample is 71 trades over four days with
daily code changes.

No architectural change — dual-side or otherwise — can be justified or refuted
on this evidence base. Anything that looks decisive at n=71 with σ=152 is noise.

## 7. Verdict

**Do not enable dual-side policy now.** Not because it is wrong, but because:

1. Its side-commitment benefit is already delivered by the existing funnel.
2. Its frame-coherence rule is inert on all 71 trades.
3. Its component scores have never been emitted, so their predictive value is
   entirely unmeasured — the one part that might genuinely add information is
   the one part with zero evidence.
4. It costs a prompt-contract change plus a retrain, and training changes are
   deferred.

## 8. What to do instead, in order

**a. Freeze the code.** The single largest obstacle is that no two days share a
codebase. Nothing is measurable until this stops.

**b. Shadow-run the dual-side schema.** `dual_side_observation_schema()` already
exists but is never sent. Ask the model the dual-side question on a second call
per bar, log the component scores, act on nothing. Schema-guided generation
works without retraining; quality may be poor, but poor and *measured* beats
unmeasured. After a few hundred bars, check whether the composed score separates
winners better than the single confidence number. That is the only way to test
the interesting hypothesis without paying for it first.

**c. Validate confidence before replacing it.** Section 2 could not answer
whether confidence works. On frozen code that becomes answerable in weeks. If
confidence turns out to be well calibrated, most of v2's value evaporates; if it
is uncalibrated, v2 gets a real target.

**d. Delete the `QWEN_POLICY_V2` flag.** It is defined and never read — setting
it to 1 does nothing. Keep `entry_policy.py`; drop the switch that promises a
behaviour change and delivers none.

## Reproducing this

Analyses ran against `logs/qwen-decisions-*.jsonl`,
`logs/paper-proposals-*.jsonl` and `logs/paper-executions-*.jsonl`, joining
proposals to closes on `proposal_id` and excluding rows with
`pnl_is_complete: false`.
