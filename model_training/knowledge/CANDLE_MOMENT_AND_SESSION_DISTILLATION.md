# Candle moment & session knowledge — distillation framework (v003)

**Purpose:** Collect human-readable trading knowledge **before** MT5 bulk export
or curriculum scripts. This feeds `store/core_skill.md` and later stages 02–03 of
`train.jsonl`.

**Your focus (confirmed):**
1. **Levels** — web app already maps levels on M1→D1; read price *at* levels.
2. **Candle moments** — higher timeframe **always influences** lower; read relation
   D1 → H4 → H1 → M30 → M15 → M5 → M1 (never reverse).
3. **Session handoffs** — especially Asia → pre-London → London: bias carry,
   **juke** (fake counter move), then continuation.

Last updated: 2026-08-07

---

## Reading order (non-negotiable)

```text
D1 context
  └─ H4 story (prior + current completed / forming)
       └─ H1 path inside H4
            └─ M30 / M15 location + level response
                 └─ M5 local map + session range
                      └─ M1 timing only
```

M1 never breaks an M15 level. An M5 wick is not a session break. H4 completion
can look like an M1 spike in the last ~10% of the H4 bar — judge after the H4 close.

---

## What the code already provides (do not re-invent)

| Asset | Location | Use for distillation |
|-------|----------|----------------------|
| Levels all TFs | Dashboard / `snapshot.levels` | Named IDs (`H4_PREVIOUS_HIGH`, `M15_CURRENT_OPEN`, …) |
| Session clock | `market_context_cache.session_at()` | asia, pre_london, london, overlap, new_york |
| H4 internal phases | v001 stage 03 `phase_reads` | first_15m_of_h4, first_30m_of_h4, last_15m_of_h4, … |
| Level double-check | v001 stage 02–03 `level_double_check` | touch + acceptance/rejection + volume effort |
| Live doctrine | `store/core_skill.md` | Canonical — distill *into* here, not parallel rules |

---

## Core concepts to distill

### 1. Candle moment (one bar’s “story”)

For any timeframe, a **moment** is not just OHLC — it is:

| Field | Meaning |
|-------|---------|
| Open location | vs prior bar, vs key level, vs session open |
| Path | which levels were touched in order |
| Close location | acceptance above/below level, inside zone, mid-range |
| Wick bias | upper_rejection / lower_rejection / two_sided |
| Body fraction | conviction vs indecision |
| Volume effort | tick_volume vs average — effort vs result |
| Carry-forward | what this bar leaves for the **next** bar same TF |

**Distillation rule:** Write one sentence: *“This H4 opened X, tested Y level,
rejected/accepted, closed Z — so the next H4 should expect …”*

### 2. HTF → LTF influence

| Parent | Child | Question to answer in knowledge |
|--------|-------|----------------------------------|
| H4 | H1 | Does each H1 inside H4 follow or fade the H4 direction? |
| H4 | M30/M15 | Where did LTF first show rejection of H4 thesis? |
| H1 | M5 | Is M5 aligning or counter-trend scalp inside H1 retracement? |
| Session range | M5 | Is price inside Asia range, sweeping edge, or accepted out? |
| D1 pivot/zone | H4 | Is H4 at daily location (floor pivot, prior high) or mid-range? |

### 3. Session handoff — Asia → London (your example)

**Asia bias (completed session only):**
- `asia_open` vs `asia_close` on M5 or H1 aggregation
- Positive: close > open (e.g. 4156 → 4157+)
- Negative: close < open
- Neutral/balance: overlap body, two-sided

**Hypothesis to distill (your words):**
> If Asia ends positive, London often continues the same direction, but **between
> Asia close and London trend** price often **jukes** the other way first (stop hunt,
> false break of Asia high/low, pre-London 07:00–08:00 chop).

**Knowledge slots to fill with real dates:**

| Slot | What to record |
|------|----------------|
| Asia outcome | open, close, high, low, bias label |
| Pre-London juke | direction, size, level used (Asia high/low?) |
| London open behavior | continuation vs reversal vs balance |
| Level involved | e.g. `M15_PREVIOUS_HIGH`, Asia session high |
| M5 confirmation | closed break or wick-only (invalid) |

**Do not train “always long after positive Asia”** — record *conditions* when
continuation failed (e.g. already at H4 resistance, news, exhausted move).

### 4. Between-session (not only Asia→London)

| Transition | Distill |
|------------|---------|
| Asia → pre-London | Chop, juke, liquidity grab |
| pre-London → London | First M5/M15 acceptance direction |
| London → overlap | Trend continuation vs fade into NY |
| Overlap → NY | Often different character — code currently no-new-entry NY |

---

## Knowledge collection template

Copy one block per observed day/pattern. Store under
`model_training/knowledge/distillation_records/YYYY-MM-DD_<tag>.md`
(or discuss verbally — agent merges into this file).

```markdown
### Record ID: YYYY-MM-DD-001

**Dates/times (UTC):** 
**Symbol:** XAUUSDr

#### Levels in play (from dashboard IDs)
- D1: 
- H4: 
- H1: 
- M30/M15: 
- M5: 
- Session: Asia high / low = 

#### HTF moment
- Prior completed H4: direction, close vs open, key level interaction
- Current H4 (if describing intrabar): phase (first 15m / first 30m / last 30m)

#### LTF response inside HTF
- H1 segments: 
- M15/M30 at levels: accepted / rejected / balance
- M5 session break? (closed yes/no)

#### Session handoff
- Asia bias: positive / negative / neutral
- Pre-London juke: yes/no — describe
- London behavior vs Asia bias: continue / fade / chop

#### Distilled lesson (1–3 sentences, no lookahead)
- 

#### Confidence: low / medium / high
#### Promote to core_skill section: [auction-states | session-rules | SR-rules | …]
```

---

## How this maps to v001 curriculum (later SFT)

| Your knowledge | v001 stage | When we build train.jsonl |
|----------------|------------|---------------------------|
| Principles (reading order, juke definition) | 01 | From approved distillations |
| Multi-H4 + level double-check | 02 | MT5 candles + your labels |
| H4 internal phases + volume | 03 | MT5 M1 trace inside H4 |
| Entry JSON | 04 | After distillations stable + paper review |

**Now:** stages 01 + narrative distillations.  
**Later:** MT5 export auto-fills user JSON; **your labels** fill assistant JSON.

---

## Minimum knowledge pack before any MT5 export

Collect at least:

| # | Topic | Target records |
|---|--------|----------------|
| 1 | H4 → H1 carry-forward at a named level | 5 |
| 2 | M15/M30 double-check vocabulary | 5 |
| 3 | Asia positive → London juke → continue | 5 |
| 4 | Asia positive → London **failed** continuation | 3 |
| 5 | Pre-London chop (07–08 UTC) | 3 |
| 6 | Level respect vs break (M5 close rule) | 5 |

**Total ~26 short records** = enough to rewrite `core_skill.md` session + HTF
sections and define builder rules.

---

## Distillation → store workflow

1. You fill records (template above) with **dashboard level IDs + UTC times**.
2. Human marks: approve / reject / needs-more-days.
3. Approved lines → edit **existing** paragraphs in `store/core_skill.md`
   (bump version comment), not append endlessly.
4. One line in `LESSON_LEDGER.md` per approved pattern.
5. When pack is complete → run MT5 export aligned to these rules.
6. Then `build_market_structure_curriculum.py` (future script).

---

## Open vocabulary (align with you)

| Term | Working definition — confirm or correct |
|------|----------------------------------------|
| **Moment** | One closed candle’s full story: path, level response, close, carry-forward |
| **Juke** | Short counter move against session bias before London/overlap continuation |
| **Positive Asia** | Completed Asia session: close > open on session aggregate |
| **Level double-check** | Touch + close location + rejection/acceptance + volume effort at named zone |

---

## Next step from you

Provide **one real example** in the template format (Asia → London juke) with:
- UTC date
- Level IDs from the dashboard
- Asia open/close (approx prices OK)
- What the juke did and what London did after

We merge that as the first approved distillation record and extend the pack.
