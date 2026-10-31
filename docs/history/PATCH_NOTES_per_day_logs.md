# Per-day proposals/executions/log files — patch notes

You asked for separate log and proposals files per day going forward,
after seeing how big `paper-proposals.jsonl` (74MB) and `paper-executions.jsonl`
(24MB) had gotten — a single file spanning every day since launch, which is
why today's trade review needed a grep-filter step just to isolate today.

`reviews-YYYY-MM-DD.jsonl` already worked this way. This patch brings the
other files in line with that same pattern.

## What changed

- `paper-proposals.jsonl` → `paper-proposals-YYYY-MM-DD.jsonl` (new file each day)
- `paper-executions.jsonl` → `paper-executions-YYYY-MM-DD.jsonl` (new file each day)
- `paper-runner.log`, `reviewer.log`, `market-context-cache.log` — unchanged
  filenames, but now use Python's standard `TimedRotatingFileHandler`, which
  rolls over at local midnight and renames the previous day's file to
  `paper-runner.log.2026-08-06` (the date suffix is appended by the standard
  library, not inserted before the extension — that's a library convention,
  not something worth fighting).

Files touched: `paper_executor.py`, `paper_runner.py`, `reviewer.py`,
`market_context_cache.py`. `trade_manager.py` doesn't read or write any of
these files, so it's untouched.

## Why this needed care, not just a rename

`paper-proposals.jsonl` and `paper-executions.jsonl` aren't just logs —
`paper_runner.py`, `paper_executor.py`, and `reviewer.py` all read them back
to answer questions like "has this proposal already been executed" and "what
was the entry thesis for this open position." Splitting them by day means a
position opened at 23:59 and still open at 00:01 has its opening record in
yesterday's file while its ongoing monitoring events land in today's file.
Every lookup-by-id in this patch checks today's file **and** yesterday's, so
that case is covered. Lookups for "the single latest thing" (like the
dashboard's most recent execution) also fall back to yesterday's file if
today's is empty or doesn't have what's needed.

The one exception is `reviewer.py`'s incremental executions tail (used to
recover each open position's peak/giveback path without re-reading the whole
file every cycle) — it now tracks which file it's tailing, and when the date
rolls over it just starts a fresh tail on the new day's file at offset 0.
Nothing is lost: any position still open across midnight keeps getting fresh
monitor events in the new file under the same execution ID.

One incidental fix: `paper_runner.py`'s `processed_ids()` used to re-read the
*entire* executions file on every 250ms poll — which is almost certainly why
that file reached 24MB. With per-day files it now only reads today's (plus
yesterday's near midnight), so this should also measurably cut CPU/disk I/O
on the runner loop, not just tidy up log size.

## What did NOT change

No entry, management, or execution logic changed — no gates, no cache
qualification, no SL/TP behavior, nothing on the strategy side. This is
purely how these files are named and read. The `deployed_patch/` copies of
`paper_executor.py` and `reviewer.py` include the ±5.0 safety-bracket
behavior that's already running on your machine today (see the trade review
doc from this same session) — I preserved it as-is rather than silently
reverting it, since whether to keep, change, or roll that back is your call,
not mine to make while fixing something unrelated.

## Two folders in this delivery

- `source_patch/` — matches your committed source tree
  (`D:\QuantLLMBot\apps\qwen_trade_software\backend\`). Does **not** include
  the ±5.0 bracket change, since that isn't in source today either.
- `deployed_patch/` — matches what's actually running
  (`C:\Users\HP\AppData\Local\QwenTradeReviewer\`), i.e. source_patch plus
  the bracket behavior already live there. **Use this folder to update the
  running system.**

## How to apply it (deployed_patch → the running system)

1. Stop the live processes first. `software_runtime.py` restarts any child
   it finds dead within 5 seconds, so just replacing a `.py` file while it's
   running risks the restart happening mid-copy. Stop the three
   `QuantLLMBot -*` scheduled tasks (or however you currently start the
   supervisor) before touching any file.
2. Back up the current deployed folder — a plain copy of
   `C:\Users\HP\AppData\Local\QwenTradeReviewer` is enough, it's just a
   safety net if something needs reverting.
3. Copy the four files from `deployed_patch/` into
   `C:\Users\HP\AppData\Local\QwenTradeReviewer\`, overwriting the existing
   ones.
4. Restart (re-enable the scheduled tasks / start the supervisor again).
5. Verify: after it's running, check
   `C:\Users\HP\AppData\Local\QwenTradeReviewer\logs\` for a new
   `paper-proposals-2026-08-06.jsonl` and `paper-executions-2026-08-06.jsonl`
   appearing alongside (not replacing) whatever the old monolithic files
   left behind. The old `paper-proposals.jsonl` / `paper-executions.jsonl`
   files are not touched or deleted by this change — they just stop being
   written to, so they're safe to archive once you've confirmed the new
   per-day files are being written correctly.

Also copy the same four files into
`D:\QuantLLMBot\apps\qwen_trade_software\backend\` from `source_patch/` so
the committed source tree matches what's about to run — otherwise this
patch itself becomes the next undocumented divergence.

## Update 2026-08-06 (later same day): Qwen decision timing + a staleness gate

Two more changes landed in `reviewer.py` and `paper_runner.py`, on top of
the per-day logging change above. Both came out of the trade-by-trade
review that afternoon.

**1. Qwen entry-decision timing (logging only, no behavior change).**
`generate_dashboard_deal_sheet()` in `reviewer.py` now times the
`ollama_generate()` call for entry decisions the same way `review_positions()`
already timed management decisions. Each proposal's `qwen` section gains two
new fields: `decision_wall_seconds` (wall-clock time the call actually took)
and `decision_duration_ns` (Ollama's own reported `total_duration`). Both are
`None` on the wait/off-session branches, where no model call happens. This
was previously a real blind spot — the proposal's own timestamp is stamped
*after* this call finishes, so nothing before this patch measured it at all.
A line is also written to `reviewer.log`: `Qwen entry decision took Xs`.

Once the faster machine is in place, compare `decision_wall_seconds` before
and after the move — that's the direct evidence of how much the hardware
change actually helped, rather than inferring it indirectly.

**2. A pre-execution staleness gate (behavior change — reads before you rely on it).**
`paper_runner.py` gained `entry_reward_risk_eroded()` and a live-price check
inside `proposal_runtime_failures()`. Right before a proposal is dispatched,
it fetches a fresh MT5 tick and compares the *remaining* distance to Qwen's
own `take_profit` reference against the *remaining* distance to Qwen's own
`stop_loss` reference, both measured from the live price, not the price at
decision time. If the remaining reward has dropped below 40% of the
remaining risk (`MIN_REMAINING_REWARD_RISK_RATIO = 0.4`), or price has
already reached/passed the target outright, the proposal is skipped with a
new failure code, `entry_reward_risk_eroded`, logged the same way existing
`entry_runtime_validation_failed` skips already are.

This does **not** change anything about how Qwen decides bias, confidence,
or levels — it only refuses to chase a signal whose own numbers have
already been eaten by the decision-to-execution delay. It was built and
tuned directly against today's data: on 2026-08-06, exactly 2 of the 12
filled trades (the two discussed as "entered too late in the zone, thin
remaining edge") would have been skipped by this gate, and no others —
it does not fire on proposals with a normal or even large gap between
decision price and live price, only on ones where the reward specifically
has been eaten relative to the risk still outstanding.

Because this changes what gets executed (not just what gets logged), treat
it like any other engineering change: watch `entry_reward_risk_eroded` skips
in `daily_trade_review.py`'s output for a while after deploying, and revisit
`MIN_REMAINING_REWARD_RISK_RATIO` if it turns out to be firing too often or
too rarely. Nothing about Qwen's own decision quality needed to change for
this — the review this came out of was clear that Qwen's reads were sound;
this only tightens the handoff from decision to execution.

## Update 2026-08-06 (evening): single-location consolidation + store-root rename

Two structural changes, both about eliminating places the code could
silently drift, not about trading logic:

**1. App-root consolidation.** The live runtime (previously split between
this app-root source tree and `C:\Users\HP\AppData\Local\QwenTradeReviewer\`)
is being collapsed into one location:
`D:\QuantLLMBot\apps\qwen_trade_software\backend\`. Going forward there is
exactly one copy of every backend file — no `source_patch` / `deployed_patch`
split. `migrate_qwen_reviewer_to_app_root.ps1` (in `D:\QuantLLMBot\`) moves
the runtime state (logs, the cache database, `review-tickets.json`),
rewrites `start-reviewer.ps1`, repoints the "QuantLLMBot - Qwen Reviewer"
scheduled task, and renames the old AppData folder to
`...QwenTradeReviewer.migrated_backup` (never deleted). It defaults to a dry
run; pass `-Execute` to actually apply it.

**2. Store-root made generic.** The `ResearchLab` folder is being retired —
the `store/` folder that `core_skill.md`, `sop.md`, and the prompt-section
loader depend on has been moved to `D:\QuantLLMBot\store` (app-root level,
no longer nested under `ResearchLab`). `market_context_cache.py`,
`reviewer.py`, and `trade_manager.py` no longer hardcode
`ResearchLab\store`; they now derive `DEFAULT_STORE_ROOT` as
`APP_DIR.parents[2] / "store"` (three levels up from `backend\`), overridable
via a renamed environment variable, `QUANT_STORE_ROOT` (was
`QUANT_RESEARCH_LAB`). `LAB_ROOT` / `lab_root` / `DEFAULT_LAB_ROOT` are gone
from all three files.

**Important ordering dependency.** `APP_DIR.parents[2]` only resolves to
`D:\QuantLLMBot\store` correctly if the running code actually lives at
`D:\QuantLLMBot\apps\qwen_trade_software\backend\` (three levels deep, as
above). If the scheduled task is still launching the *old* AppData copy when
it restarts, `parents[2]` resolves to `C:\Users\HP\AppData\Local` instead,
and the store won't be found. That's why the app-root consolidation
(`migrate_qwen_reviewer_to_app_root.ps1 -Execute`) has to run — or be
confirmed already run — *before* restarting, not after. Once it's run, the
scheduled task always launches from the app-root folder and this resolves
correctly on every future restart, including after `ResearchLab` is deleted.

## Update 2026-08-06 (night): management review interval 60s -> 30s, and a direction decision on trade management

Discussed the SL/TP gap from the earlier update tonight (the generic +/-5.0 bracket effectively
never gets replaced -- 0 "protect" actions out of 34 review cycles today). Considered making
Qwen's own reference SL/TP the entry-time bracket instead of the generic one. Explicitly
rejected: Qwen's own levels are often too tight to serve as the immediate entry-time stop, so
the entry-time bracket stays as-is. Direction going forward: the ongoing 60s (now 30s)
management-review loop -- not the entry moment -- is the intended place for Qwen's real levels
to take effect over the life of a trade. A richer per-review decision (explicit
tighten/widen instructions on the stop and target, not just hold/protect/close) was discussed
as a bigger step-2 item -- not built yet, needs its own design pass since it changes what Qwen
is asked, not just execution plumbing.

**What shipped now:** `reviewer.py`'s `INTERVAL_SECONDS` dropped from 60 to 30, overridable via
`QWEN_REVIEW_INTERVAL_SECONDS` so it can go to 15s on the new GPU machine later without another
code change -- confirm management-decision timing on the new hardware first rather than
assuming 15s is safe there too. Also corrected a stale comment above `AUTO_MANAGE_QWEN_OWNED`
that claimed the executor installs Qwen's validated levels at entry -- it doesn't; that's the
exact gap this update is about.

**Also noted, not yet acted on:** `review_positions()`'s Qwen calls and the entry-decision
Qwen calls both go through the same `model_generation_lock()` -- they're separate functions
but share one loaded model instance, so a management check and an entry decision contend for
the same lock if they land at the same moment. Not a bug, just a real constraint worth knowing
before assuming faster hardware alone removes all latency variance; running two independent
model instances (one per role) would need roughly double the VRAM.

**To pick this up:** unlike `paper_executor.py`, `reviewer.py` is one of `software_runtime.py`'s
supervised standalone processes (own PID in `software-runtime.log`), so killing it directly
picks up the new interval on the supervisor's automatic restart -- same self-healing pattern
as tonight's earlier restarts, no scheduled-task involvement needed.

## Update 2026-08-06 (later night): entry-decision and trade-management split into two processes

You asked for a real separation between entry (deciding whether to open a trade) and trade
management (deciding what to do with a trade once it's open) -- separate files, because the
two are "a different game" and will increasingly need separate knowledge bases and, down the
line, separate trained skills. This was the biggest structural change of the night, so it's
documented in full.

**New file layout:**

- `review_shared.py` (new) -- infrastructure genuinely needed by both sides: the Qwen/Ollama
  call (`ollama_generate`, `warm_model`), MT5 connection setup (`connect_mt5`), the
  review-tickets file both sides read/write, small dashboard-value normalizers
  (`normalize_confidence`, `normalize_text`, `normalize_invalidation`), the Qwen-ownership check
  (`is_qwen_owned`), dated log-file helpers, and two small new JSON helpers
  (`read_json_safe` / `write_json_atomic`) for the cross-process dashboard-state handoff below.
  Nothing trading-decision-specific lives here on purpose.
- `trade_management.py` (new) -- everything that happens *after* a Qwen position is open: the
  live MT5 position/deal polling, building management facts (trade path, structural levels,
  execution-monitor state), the hold/protect/close decision (deterministic confirmation guard
  first, Qwen call as fallback), and applying that decision's SL/TP change. Runs on its own
  loop, own interval (`QWEN_REVIEW_INTERVAL_SECONDS`, default 30s, same as tonight's earlier
  change), own log file (`trade-management.log`), own singleton port (48633).
- `reviewer.py` (trimmed) -- now only the entry-decision side: asking Qwen for a new setup when
  flat, recording the proposal, and the dashboard HTTP API (still on port 48632, still serving
  `/snapshot` in the same shape the GoldFlow frontend already expects). No longer holds any MT5
  connection at all -- it has nothing left that needs one. Own loop interval is now
  `QWEN_ENTRY_INTERVAL_SECONDS` (default 30s), kept as a separate env var from management's on
  purpose, so the two cadences can diverge later without conflating "check for a new setup"
  with "review an open trade."
- `software_runtime.py` (updated) -- added `trade_management` as a third supervised child
  process, started right after the reviewer dashboard health check passes.

**The one tricky part -- the in-memory dashboard state:** the old single process kept one
`DASHBOARD_STATE` dict in memory, written by both entry and management code paths and read by
both. Two separate processes can't share memory, so this became two JSON files:
`management-dashboard-state.json` (written every cycle by `trade_management.py` -- price,
positions, today's stats, chart levels, and its own `qwen_management` in-trade commentary) and
`entry-dashboard-state.json` (written by `reviewer.py` only when it produces a new deal sheet --
just its `qwen` entry thesis). `reviewer.py`'s dashboard API merges the two into the same
`/snapshot` shape as before: broker/position data always comes from the management file (only
that process has a live MT5 connection); the single `"qwen"` field shown in the UI is
management's in-trade commentary while a Qwen position is open, otherwise entry's most recent
thesis -- the same mutual exclusivity the old single-process version had by construction (entry
never generated a new deal sheet while a Qwen position was open), just implemented as a file
merge (`reviewer.build_snapshot()`) instead of one dict. Reads use a `read_json_safe` helper
that degrades to defaults on a missing or mid-write file rather than raising, so a slightly
stale read (up to one management cycle, ~30s) is the worst case -- never a crash.

**Confirmed not a safety regression:** the real single-position guard that stops Qwen from ever
opening a second position is a live, independent `mt5.positions_get()` check inside
`paper_runner.py`'s `has_open_qwen_position()` -- it does not read `reviewer.py`'s dashboard
state at all. That gate is unchanged by this split. The file-based state `reviewer.py` now reads
is only used for its own soft pre-checks (don't bother asking Qwen for a new setup if a position
already looks open) and for the UI -- a stale read there costs at most one extra, harmlessly
wasted Qwen call, never a double-entry.

**Still shared, not split:** both processes still call through the same `model_generation_lock()`
in `market_context_cache.py` and the same underlying Qwen/Ollama model instance -- splitting the
code into two processes is not the same as splitting the model. That stays a real constraint
(a management check and an entry decision still contend for one lock if they land at the same
moment) until/unless separate models are actually trained and hosted, which is explicitly future
work tied to the faster GPU machine, not part of this change.

**Verification done before delivery:** all five changed/new files (`review_shared.py`,
`trade_management.py`, `reviewer.py`, `software_runtime.py`, and the untouched `trade_manager.py`)
parse cleanly and pass `pyflakes` with no unused-import warnings. A sandboxed smoke test (stubbed
`MetaTrader5`/`msvcrt`, real `market_context_cache.py`/`trade_manager.py`) exercised the actual
file handoff end-to-end: `trade_management.update_dashboard()` writing a position, then
`reviewer.build_snapshot()` correctly picking management's commentary while that position is
open and falling back to entry's thesis once it reports flat again. This was not run against
live MT5/Ollama -- that only happens on the real restart.

**Restart requirement -- read this before restarting:** this is not a single-process kill.
`software_runtime.py` itself changed (it now supervises a third child), so the *whole* supervised
chain needs to restart, the same way as the very first restart tonight -- via the scheduled task
(`schtasks /Change` + `schtasks /Run`), not by killing an individual `.py` process. Killing just
`reviewer.py` or `paper_runner.py` would bring back the *old* single-process `reviewer.py` code
under the *old* supervisor that doesn't know about `trade_management.py` yet, since the
supervisor itself is what's being replaced here. Also note two new files appear under the backend
folder once this runs: `entry-dashboard-state.json` and `management-dashboard-state.json` -- if
either is ever deleted by mistake, both processes recreate it from defaults on their next cycle,
no data loss beyond the current in-memory-equivalent state.

## Update 2026-08-06 (late night): buy-bias evidence check, and M30 added to the watched-zone playbooks

**Safety branch first:** before touching anything, `pre-m30-level-entry-decision` was branched
off `dev` at the last-known-good commit (the LFS/`.gitignore` commit), so tonight's work can be
reverted to a known point with one `git checkout` if the M30 change below causes a problem live.

**Buy-bias check -- what the evidence actually shows.** You asked why the model leans buy. I read
`core_skill.md` and `sop.md` in full first: the doctrine is symmetric by construction (`[entry-sell]`
is literally "exact inverse" of `[entry-buy]`, `[coherence]` explicitly forbids a buy while calling
the location resistance) and the `entry_decision_schema`'s enum is `["buy","sell","conditional"]`
buy-first -- worth knowing since JSON-schema-constrained decoding at `temperature: 0` can, in
principle, break a near-tied preference toward whichever enum option is listed first. That's a real,
still-untested hypothesis, not yet a finding.

What the actual proposal logs show is less exotic: real Qwen decisions (`decision_wall_seconds is
not None`, filtering out the synthetic off-session/cache-not-ready placeholder rows) had zero buy
bias on Aug 3-4 and were effectively all-buy on Aug 5-6 -- which lines up with XAUUSD actually
rallying those two days. The bias tracks the trend, which is what the doctrine is designed to do.
The one genuine defect found: across 85 + 91 real decisions on Aug 5-6, the structured `bias` field
never once returned `"sell"`, but 13 of those records have a free-text summary that reads bearish
while the structured field still says `"buy"`/`"conditional"` -- a real field-consistency bug, logged
here so it isn't lost, but not yet fixed (needs its own look, separate from tonight's M30 work). The
temperature/enum-order hypothesis above is still open and not yet tested either.

**What you actually asked for tonight: 30-minute granularity on entry timing.** The root cause
of "by the time an H1 candle confirms, price already moved" is in `market_context_cache.py`'s
`run_once()`: the playbook object -- the actual watched-zone list `qwen_cached_entry` reads for
entry timing -- only rebuilds when `playbook_hash` (previously identical to `structural_hash`,
built from `subset_hash(("D1","H4","H1"))`) changes, i.e. at best once an hour. `build_levels()`
was already computing fresh M30 data every single cycle; it just wasn't being used for playbook
candidate selection.

**The fix, and why it's narrower than "add M30 everywhere":** `("D1","H4","H1")` shows up in
eleven places in `market_context_cache.py`, serving two genuinely different jobs --
(1) the D1/H4/H1 macro "market story" narrative that feeds `qwen_cache_warmup`'s
`timeframe_location` contract and `validate_warmup`'s exact-three-keys check, and (2) the
watched-zone/playbook candidate selection that actually times entries. Widening job (1) would
have made the warmup/narrative Qwen calls re-fire on every M30 close too -- more model load for a
layer that doesn't need it and whose prompt contract explicitly promises "exactly D1, H4, and H1."
So only job (2) changed:

- `run_once()`: `playbook_hash` is no longer `= structural_hash`. It's now its own
  `subset_hash(("D1","H4","H1","M30"))`, deliberately decoupled from `structural_hash`
  (unchanged at `("D1","H4","H1")`) so the narrative/warmup cadence is untouched.
- `build_playbooks()`: the candidate-level filter now includes `"M30"` (was D1/H4/H1 only), so
  the nearest-3-by-distance zones Qwen watches can now be M30 zones, not just daily/4h/1h ones.
  The playbook anchor moved from the H4 boundary (`"H4-...` id prefix, `expires_at=next_h4`) to
  the M30 boundary (`"M30-..."` prefix, `expires_at=next_m30`) -- the watch list can now visibly
  refresh up to every 30 minutes instead of every 4 hours.
- `gate_b()`'s integrity check (`expected_hashes["playbooks"]`) updated to match, so the derived
  cache doesn't start failing its own provenance check.
- `build_structure()`'s D1/H4/H1 narrative filter, `validate_warmup`'s exact-three-key check, and
  everything inside `_run_warmup`/`_challenge_payload` (the macro-story and cache-qualification
  layer) are all **unchanged** -- confirmed by re-reading every remaining occurrence of
  `("D1","H4","H1")` in the file line by line.
- `sop.md`'s `qwen_playbook_interpretation` doctrine (v1.0 -> v1.1) no longer tells Qwen every
  playbook record is H4-anchored, since some now are M30-anchored -- the wording change doesn't
  touch what the model is allowed to do with a record, only removes a now-inaccurate assumption.

**Verification done before delivery:** `ast.parse` on the changed file. A sandboxed smoke test
(stubbed `MetaTrader5`/`msvcrt`, a synthetic sqlite cache) ran `build_levels` / `build_structure`
/ `build_playbooks` / `gate_b` end-to-end and specifically proved the property this whole change
depends on: seeding a *second* M30 close (D1/H4/H1 untouched) left `structural_hash` identical but
changed `playbook_hash`, and the watched-zone set actually shifted to include the new M30 data --
while `build_structure`'s `timeframe_location` stayed exactly `{"D1","H4","H1"}` throughout. `gate_b`
passed both before and after. Not run against live MT5/Ollama.

**Restart requirement:** the whole supervised chain, not one process. `reviewer.py`,
`trade_management.py`, and `paper_runner.py` all `import` from `market_context_cache.py` directly
-- a stale in-memory copy of the old module in any one of them would compute the old
`("D1","H4","H1")` playbook hash while the rest of the chain expects the new one, which `gate_b`'s
own provenance check would then correctly flag as a mismatch and block entry decisions entirely.
Restart via the scheduled task, same as the two prior changes tonight, not by killing individual
`.py` processes.

**Not done tonight, intentionally left open:** the temperature=0/enum-order test for the buy bias,
and the bias field-consistency bug (13 cases where free text disagreed with the structured `bias`
field) -- both need their own dedicated look with fresh evidence, not folded into this change.
