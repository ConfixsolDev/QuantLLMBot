# Trading-Skill Lesson Ledger

Tracks approved trading-skill lessons since the last LoRA version, and
whether it's time for a retrain. See `DAILY_REVIEW_PROCESS.md` for the full
loop. Engineering findings (bugs, divergences) are NOT tracked here — see
that doc's "two lanes" section for where those go instead.

## Retrain threshold

- **Threshold:** 20 approved lessons since the last retrain (default —
  adjust here if that number turns out too high or too low in practice).
- **Approved since last retrain:** 0 / 20
- **Last LoRA version trained:** qwen-trading-v002 (current production;
  no retrain has happened yet under this process)
- **Corpus at last retrain:** not yet applicable

## Approved lessons (running log, newest first)

*(Empty — no trading-skill lesson has been approved yet under this process.
See the note below on 2026-08-06's findings.)*

<!--
Entry format once lessons start getting approved:

### YYYY-MM-DD — one-line summary
- Evidence: trade #s / day(s) it's drawn from
- Section touched in TRADING_KNOWLEDGE_BASE.md: <section name>
- Confidence it generalizes: low / medium / high
-->

## Notes

- **2026-08-06:** First day this process covered. Both findings from that
  day's review (the ±5.0 safety-bracket divergence, and the
  apply_confirmed_protection mechanism never firing) are engineering
  findings, not trading-skill lessons — they belong in
  `ResearchLab\PROVEN_HARMFUL_CHANGES.md` / the code fix track, not here.
  The one candidate trading-skill observation from that day — all 50 ready
  proposals were buy-side with zero sells — was marked *needs more days* in
  the daily template rather than approved, since one day's one-sided
  session isn't enough evidence to generalize into doctrine yet. Worth
  revisiting once a few more days of data exist.
