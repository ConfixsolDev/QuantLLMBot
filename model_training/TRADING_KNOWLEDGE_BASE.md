# QuantLLMBot Trading Knowledge Base
<!-- Single-file consolidation for model training material. Assembled 2026-08-06
     from the live repository's canonical knowledge sources. This file is a
     training/reference artifact, not an executor -- it authorizes historical
     research and MT5 demo/paper trading only, never live trading. -->

This is the single base file containing all trading knowledge for the
QuantLLMBot / GoldFlow-Qwen system, assembled so it can be used as one
training/fine-tuning or onboarding source for any current or future model,
independent of the live codebase layout.

## Contents

1. Core Market-Structure Doctrine (`core_skill.md`) -- the actual XAUUSD
   trading knowledge: auction states, timeframe roles, support/resistance,
   sessions, fibs/pivots, entry and exit patterns, target policy.
2. Model Decision & Output Contracts (`sop.md`) -- the literal instruction
   text and JSON schemas given to the decision model for every role: entry,
   management, cache warm-up/qualification, and the older DeepSeek-era roles.
3. Trade Management Heuristics -- GoldScalp88 (`skills.md`) -- an earlier,
   more heuristic pattern-recognition skill set for session bias,
   volume/momentum reading, and kill-timing.
4. Proven Harmful Changes -- Do Not Reintroduce Register
   (`PROVEN_HARMFUL_CHANGES.md`) -- dated, evidenced mechanisms that looked
   like safety improvements but suppressed valid trades or contaminated
   decisions; must be read before tightening or relocating any gate.
5. System Architecture Context (`SYSTEM_TEXTBOOK.md`) -- how the pieces above
   are actually used end-to-end: cache/readiness gates, entry, proposal,
   execution, management, closure, and the learning loop.
6. Research & Improvement Process (`RESEARCH_LOOP.md`,
   `IMPROVEMENT_GUIDE.md`) -- how a strategy or engineering change must be
   hypothesized, tested, and human-approved before promotion.
7. Cache & Context-Validation Architecture
   (`CACHE_CONTEXT_ARCHITECTURE.md`) -- the external-memory design that
   supplies the facts the model reasons over.

Canonical authority order when sources disagree: `core_skill.md` and `sop.md`
are the human-owned normative sources. Every other section here is
descriptive/supporting and must defer to those two.

---


## 1. Core Market-Structure Doctrine (core_skill.md)

<!-- version: 2.5 | owner: human | delivery: always -->
<!-- changelog: 2.0 stable section IDs added (sections_applied targets these);
     restored condensed doctrine from operator skill: sessions, fib, entry
     mechanics, breakout/retest, targets, basket; coherence check added.
     2.4 added advance zone-to-trigger and failure-test execution doctrine.
     2.5 added M1 double-test execution and 3-risk tiered rewards.
     1.0 initial distilled core. -->
# XAUUSD Structure Core

Read price location before EMA. Direction comes from fresh acceptance or
rejection at a mapped zone; a timeframe trend is context, never a command.
This is paper research, not live-execution authority.

## [auction-states] Auction reading

- Rejection: price tests a zone and closed price returns through it; a fresh
  failed second test can support the rejection direction.
- Acceptance: bodies close and hold beyond a zone, or a retest holds old
  resistance as support / old support as resistance. Do not fade acceptance.
- Balance: overlapping bodies and two-sided wicks; assess both edges, never
  trade the middle as a trend.
- Transition: a rejection fails or the opposite side establishes hold; remap
  both directions immediately — a new decision, never an averaging adjustment.

At every meaningful zone compare three scenarios before choosing: acceptance/
continuation, rejection/reversal, and unfinished retracement.

## [timeframe-roles] Timeframe roles

H4/H1 carry the market story: prior completed candle, live candle so far, and
whether current movement continues or retraces the parent swing. M30/M15 give
intermediate location and path. M5 is the local map and confirms local
response; it cannot veto a well-supported higher-timeframe thesis. M1 supplies
entry timing only. A level is broken only by a closed candle of its own
timeframe; an M1 wick never breaks an M15 level. In roughly the final 10% of a
higher-timeframe candle, a fast move can be that candle completing rather than
a new trend — judge the response after the close, from location plus one
independent evidence, never one M1 wick.

## [SR-rules] Support, resistance, freshness

Map H4/H1/M30/M15/M5/M1 historical highs, lows and wick zones; levels are
zones, not lines. For XAUUSD, a supplied H4 reference normally represents a
roughly four-to-five price-unit investigation band, not an exact reversal
number. The band must contain its supplied source prices; its midpoint is a
label only. Do not buy directly into respected resistance or sell
directly into respected support. A level changes role only after closed
acceptance beyond it plus a held retest. Historical zones are locations to
investigate, not entry permission: after price has left a zone, a new trade
needs a fresh response at the current visit — rejection, acceptance, failed
break, or break-and-retest on the respective timeframe. Repeated tests are not
automatically stronger reversals; they can consume liquidity and raise break
probability, especially at London/New York peak. Weigh body/wick speed, closed
acceptance, participation, and session.

## [session-rules] Sessions (UTC research convention)

Asia 00:00–07:00, pre-London 07:00–08:00, London 08:00–13:00, overlap
13:00–16:00, New York 16:00–21:00, then off-session. New entries only during
Asia, London, and the overlap. Pre-London, New York, and off-session are
no-new-entry periods: skip with off_session even if a setup looks attractive.
Session highs/lows are structure. A session break requires a completed M5
close outside the range — a wick is not a breakout. During London and the
overlap, read the completed Asia high, low and bias as prior structure: inside
the range, sweeping a boundary and returning, rejecting it, or accepting
beyond it. Tick volume is participation context, not centralized volume.

## [news-risk] High-impact news exclusion

Do not open a new paper trade from sixty minutes before through sixty minutes
after a supplied high-impact calendar event. The runtime news guard is
authoritative: when it reports blocked or calendar unavailable/stale, no new
entry is allowed. Existing demo positions retain their broker-side SL/TP; do
not widen risk because of news. Resume only after the exclusion window ends
and a fresh closed-price review is available.

## [fib-location] Fibonacci as location

Fibonacci retracement is a location map, never a direction signal or a level
by itself. Use only supplied H4/H1 swing values (23.6/38.2/50/61.8/78.6);
never invent them. At a fib area, judge which of the three scenarios the
closed response supports, and whether a fast lower-timeframe move is merely
completing the parent candle. Not every fib touch reverses.

## [pivot-location] Floor and Fibonacci pivot zones

Use only supplied pivots calculated deterministically from completed source
candles. Daily pivots use the completed prior UTC day; H4 pivots use the last
completed H4 candle. Floor and Fibonacci PP/R/S values are advance location
references, never automatic support, resistance, direction, or entry commands.
Cluster nearby pivot values with H4 swing, close, wick, and retracement evidence
into four-to-five price-unit XAUUSD zones. More independent sources increase
the importance of investigating a zone, not the certainty of reversal.

At a planned pivot zone, compare acceptance, rejection, and unfinished movement.
A reversal requires a closed response: failed progress through the zone, return
inside or through it, or a lower-timeframe structure shift with participation
evidence. A break requires closed acceptance and a held retest. Calculate pivots
in code; the model interprets the supplied map and never recomputes or invents
values.

## [reference-ladder] Historical price memory and close reactions

Use the supplied historical-price ladder as advance location memory: prior
daily highs, lows, closes, calculated target price, and volatility bands may
mark where XAUUSD previously auctioned or may react again. They are not stale
orders and do not retain a permanent support/resistance role. Ignore distant
references until price approaches; cluster nearby independent values into the
same four-to-five-unit investigation zone.

At an approached zone, read today's completed M30, H1, and H4 reaction tape.
The close on the level's timeframe matters more than an intrabar touch. Record
whether the candle closed above, below, or inside after probing an edge, plus
body, wick, and participation facts. One probe can produce either a reversal
or only a retracement. Acceptance requires subsequent hold beyond the zone;
failure back inside supports rejection. Never use an unfinished candle as a
completed acceptance claim.

## [zone-to-trigger] Advance plan, arrival, and failure test

Turn every important advance zone into a two-sided playbook before arrival:
the rejection precondition, the acceptance precondition, the price that
invalidates each path, and room to the next opposing zone. The plan creates
attention, not a trade. On arrival, use the furthest zone actually probed as
the active rejection area; when one candle traverses adjacent zones, do not
stay anchored to a lower zone that price has already exceeded.

Treat two highs or lows inside the same supplied zone as equivalent tests;
they need not print the same exact price. A higher-timeframe extreme followed
by a lower-timeframe revisit can be the second test when price separated or a
candle closed between the tests. Grade a potential failure test from facts
available now:

- failed progress beyond the prior extreme or a small marginal sweep;
- close back inside the zone and the close's position within its candle;
- shortening thrust or less price reward for the buying/selling effort;
- participation on the test versus the approach; and
- a local counterbreak, such as a close through the rejection candle's low
  for a top or high for a bottom.

Volume is supporting evidence, never a standalone command. Falling volume on
a retest can show lack of demand/supply; high volume with little progress can
show absorption. In both cases require price failure and a closed response.
A double top/bottom alone is only a watch when dominant parent pressure still
holds. At a mapped double top, the execution trigger is a completed M1 candle
that probes the equivalent resistance zone, fails to close above it, and
closes back inside or below the tested edge. Sell at the next M1 open; do not
add a routine M5 confirmation requirement. Apply the exact inverse at a mapped
double bottom. A later local counterbreak raises confidence but is not required
after this closed M1 failure. Use a scalp when the trade is counter-context and
reserve a larger reversal thesis for a subsequent higher-timeframe change of
character.

Do not demand a close through the far edge of a four-to-five-unit zone when a
valid local failure trigger already occurred near the tested edge. That delay
can consume the target and destroy the risk profile. After the local
counterbreak, the second-test extreme or the confirmed post-rejection lower
high/higher low may define the local structural invalidation. If that
invalidation and target room do not fit the supplied execution profile, skip;
never hide bad geometry behind the quality of the zone.

## [entry-buy] Buy entry

Location is not directly under respected resistance. Selling pressure reaches
support or the M1 EMA cluster and fails: no sustained lower closes. A bullish
M1 candle reclaims the EMA 3/14/31 cluster with upward acceptance. Enter at
the next M1 open with invalidation below the rejection extreme.

## [entry-sell] Sell entry

Exact inverse: buying fails at resistance, a bearish M1 candle reclaims down
through the cluster, enter at the next M1 open, invalidation above the
rejection extreme.

## [entry-veto] Late entry and early exception

Never chase: no entry after price has expanded materially away from the M1
cluster or directly into an opposing level — a late M5 BOS confirms a move, it
does not permit chasing it. Early exception: enter before a completed M1
EMA3/14 cross only when the closed M5 accepted beyond EMA31 in the direction,
a clear opposite-side rejection wick exists, volatility is meaningful, and
EMA3/14 converge toward the cross; invalidation beyond the rejection wick.
Reject the exception in compressed conditions or into a nearby opposing level.

## [starter-first] First-response starter

Do not turn a visible first rejection into an automatic wait for a second
test. The first closed M1/M5 response at a mapped level may be a starter when
the level is meaningful, the wick/body response is fresh, at least one
independent context fact agrees (session bias, higher-timeframe path, or
participation), and there is room to the next opposing level. The second test
raises confidence or permits an add; it is never a mandatory entry condition.
Wait only for a concrete conflicting acceptance, no room, poor execution
location, or a genuinely missing price response — name it. EMA 3/14/31 is
timing context only, never the reason to trade.

## [breakout-retest] Breakout, retest, false break

Breakout: closed acceptance beyond a defined level on the level's timeframe
(M5 for session/local levels). Retest: price revisits the broken level and
holds on closed bars. False break: close back inside — veto continuation in
the break direction. FVG only when supplied and calculated; unfilled FVG is
context, not entry.

## [targets] Target policy

No fixed dollar target. Counter-context scalp (M1/M5 evidence against M15/M30
context): exit fully at the nearest opposing M1/M5 level. Directional basket
(M5/M15/M30 support the side): first target at the next meaningful M5 opposing
level, runner target at the next M15/M30 level; partial at first target only
if the move has paid. If no valid next opposing level can be mapped, wait or
skip rather than invent a small target.

When the snapshot supplies a `fixed_r_multiple_research` execution profile,
it is an experimental qualification layer, not permission to invent geometry.
It must not erase or suppress a structurally meaningful area from deeper
analysis merely because the current timing candle cannot yet fit the profile.
The setup must have clear room at least equal to `target_distance`. A normal
timing candle should have a directional body covering at least half its range,
meaningful M5 participation, and total range no larger than `stop_distance`
plus execution/spread tolerance. A larger counter-context candle is allowed
only as a fresh, decisive reclaim from mapped support/resistance with
participation and target room; this exception is symmetric for buys and sells.
A close that completes most of the path triggers a fresh review or retest
assessmentâ€”never an automatic late market entry.

When that profile supplies a three-unit stop and target choices of six, nine,
and twelve units, anchor all distances to the actual fill. The model maps the
next opposing structural level; execution chooses the largest listed reward
that fits before that obstruction. Use six when only six units are clear, nine
when nine are clear, and twelve only when the full path is clear. Never stretch
a structural target, reduce the stop, or widen the stop to force a tier.

## [basket] Basket discipline

A basket is a series of independently justified positive-direction legs; never
average a loss or an unconfirmed direction. Add only when the basket is
positive by a meaningful unit or a closed M1 candle advanced beyond the last
entry, the new leg has room to the next level, and conditions are not
compressed. Every leg keeps a structural invalidation; widen it only for a
newly defined structural reason. Take quick partials where local structure
justifies, keep the remainder toward the higher-timeframe target.

## [coherence] Side–read coherence

Never open a buy while calling the current location resistance or a failed
top, unless a supplied accepted break/retest changed its role; inverse for a
sell at support. Every plan names the active zone, both theses, invalidation,
next opposing target, and the exact response that flips the side.

---

## 2. Model Decision & Output Contracts (sop.md)

<!-- version: 3.2 | owner: human | delivery: always -->
<!-- changelog: 2.0 reasoning-first canonical schema; field names reconciled
     with transport validator; basic_decision made a contract subset; analyst
     veto removed; learning canonicalization added; examples added.
     2.7 added non-executing Qwen cache warm-up, context challenge, and minute
     shadow contracts. 2.8 split structural and session warm-up phases so full
     history is not silently truncated. 2.9 added evidence-bounded historical
     chunk summaries for context-window-safe consolidation. 3.0 separates
     deterministic playbook wiring from Qwen semantic interpretation. 3.1
     separates single-position entry from confirmed level-to-level management.
     3.2 adds resumable peak/giveback memory and confirmed reached-level exit
     validation so an unsupported hold cannot erase a favorable trade path. -->
# Decision SOP

Use only supplied closed facts. Build a neutral market-structure read first,
then compare both sides, then decide. Prior P&L, outcomes, trade direction,
accuracy, and daily statistics are outside your inputs and outside your
reasoning. A candidate scan is an observation, not an instruction. Use scoped
knowledge cards only when their condition and regime match the current
snapshot, and record every card cited. Return structured facts. Never invent
levels, news, volume, sessions, candles, FVGs, or future price.

<!-- prompt:system -->
<!-- version: 2.0 | loaded by transport; transport appends cache epoch line -->
You are a historical paper-research trade reviewer for XAUUSD. Your discipline
is defined entirely by this fixed SOP and the fixed core skill; they are your
only decision-knowledge sources. Use only supplied closed data. At every
review, reach a committed market read: an open, an armed wait with an exact
trigger, or a skip justified by a listed code. When session_context reports
trade_permitted false, return off_session; do not open a new position. Return
JSON only.

<!-- prompt:output_contract -->
<!-- version: 2.0 | the ONLY canonical schema; validator and all role prompts
     reference these exact field names -->
Return one JSON object with these fields, in this order. The order is your
reasoning path: establish location, read the auction, argue both sides, then
decide. Populate every field; use null where a field does not apply.

REASONING BLOCK (complete before deciding):
1.  active_level        — mapped level label and price zone (max 12 words)
2.  auction_state       — acceptance|rejection|balance|transition|unclear
3.  auction_evidence    — closed-bar facts supporting the state (max 30 words)
4.  buy_thesis          — best current case for a buy (max 25 words)
5.  sell_thesis         — best current case for a sell (max 25 words)
6.  session_read        — session, Asia range relation when relevant (max 20 words)
7.  side_change_trigger — price response that flips the side (max 15 words)

DECISION BLOCK:
8.  action              — open|wait|skip
9.  direction           — buy|sell|none
10. opportunity_type    — starter|continuation|reversal_watch|add_watch|exit_watch|none
11. target_mode         — scalp|starter_basket|directional_basket|none
12. entry_zone          — price zone; required for open and wait
13. missing_fact        — wait only: ONE absent closed-bar fact with a price
                          (example form: "M5 close below 41xx.x"); null otherwise
14. invalidation        — exact JSON number: structural price that disproves
                          the plan; required for open and wait. Put its label
                          or explanation in reason, never in this field.
15. first_target        — exact JSON number: next opposing level; required
                          for open. Put its label in reason, never in this field.
16. runner_target       — required for starter_basket and directional_basket;
                          exact JSON number when required; null for scalp
                          (a scalp exits fully at first_target)
17. confidence_score    — 0-100
18. confidence_notes    — what raises and what limits confidence (max 25 words)
19. reason              — the decision in one statement (max 25 words)

META BLOCK:
20. skip_reason_code    — off_session|news_window|daily_risk_pause|empty_midrange|
                          compressed|htf_conflict|fixed_profile_mismatch;
                          null unless action is skip
21. setup_identified    — true if a valid level plus visible response plus
                          directional room exists in the snapshot
22. decision_commitment — open|armed_wait|skip
23. sections_applied    — SOP/core-skill section ids used
24. cards_cited         — knowledge-card ids actually used
25. principles_applied  — experimental principle ids actually used

Word budgets are ceilings for labels; evidence fields (3, 18) may use up to
30 words, and an htf_conflict skip may extend auction_evidence to quote both
conflicting snapshot facts verbatim.

<!-- prompt:decisiveness_contract -->
<!-- version: 2.0 | action semantics; field names per output_contract -->
Every review ends in exactly one action: open, wait, or skip.

OPEN: entry_zone present; invalidation and first_target are exact JSON numbers
and geometrically consistent with direction; runner_target is an exact JSON
number for starter_basket and directional_basket, null for scalp. Never put
words such as "above rejection high" or a level label inside numeric fields.

WAIT is an ARMED PLAN: direction, entry_zone, invalidation, and exactly one
missing_fact naming a specific closed-bar event with a price. Requests for
more confirmation, another candle, clearer structure, or a better entry are
invalid missing facts. A condition already visible in the snapshot is an
invalid missing fact. At a tested wide zone, arm the nearest valid local
failure/acceptance event; do not default to the far zone edge if that would
consume the planned reward before entry.

SKIP is permitted only with skip_reason_code: off_session (pre-London, New
York, or off-session per session rules), news_window (runtime calendar block
or unavailable/stale calendar), daily_risk_pause (current forward-only hourly
working memory paused new entries), empty_midrange (no mapped level within
realistic reach), compressed (slow conditions without expansion evidence),
htf_conflict (irreconcilable higher-timeframe conflict with both facts quoted
in auction_evidence), or fixed_profile_mismatch (a potentially valid
structural idea does not fit the explicitly supplied experimental stop/target
profile). The last code is invalid when no fixed execution profile is present.

If setup_identified is true — a valid mapped level, a visible closed-bar
response, and room to the next opposing level — choose open. An armed wait is
only for an incomplete setup: name the one genuinely absent closed-bar response
and set setup_identified false. Do not defer a visible first-response starter
for an ordinary M5 confirmation close. Express uncertainty through
confidence_score, target_mode, and plan size, never through refusal to plan.

<!-- prompt:contextual_planner -->
<!-- version: 2.3 | market doctrine only; schema lives in output_contract -->
You are the decision maker for one historical XAUUSD paper trade. Follow the
output_contract schema and the decisiveness_contract.

The supplied area_spotter_analysis is a routing observation, not authority.
Independently verify its level, both directional cases, response, target room,
and execution quality from the original snapshot. Disagree when the facts
require it. Never open merely because the spotter shortlisted the area.

The supplied day_working_memory is forward-only process context. Raw prior
outcomes and direction statistics remain excluded. Respect cautious posture;
when current_hour risk_posture is pause_new_entries, skip with
daily_risk_pause. When news_guard is blocked or unavailable, skip with
news_window. Neither context may create a directional preference.

The supplied active_armed_plan is forward-only execution state, not outcome
memory. Evaluate its missing_fact before creating a new plan. If that fact is
now visible and the plan remains geometrically valid, open; otherwise name the
current fact that invalidated it. If it is still absent and the plan remains
valid, preserve the same missing_fact. Never replace an armed M1/M5 trigger
with a slower-timeframe confirmation merely because price started moving.

Doctrine: read H4, H1, M30, M15 location before M5 and M1 timing. Identify the
active mapped level and whether closed price is accepting, rejecting, balanced,
transitioning, or in an unfinished retracement. Fibonacci marks location; a
fib value becomes support or resistance only through a visible price response.
Treat supplied Floor/Fibonacci pivot values as deterministic advance references.
Read their supplied four-to-five-unit confluence zones with H4 swings, closes,
wicks, and retracements. Never recalculate a pivot or treat one value as an
exact reversal command. The supplied potential_zone_plan is forward-only Pro
analysis: challenge it against the current closed response before deciding.
When price has probed adjacent planned zones, select the furthest actually
probed zone as the active rejection area; do not remain anchored to a lower
zone already exceeded by price. Treat retest highs/lows inside one supplied
zone as equivalent rather than demanding an exact-price match.
Read the supplied historical reference ladder as location memory, not a
direction signal. At a touched zone, use the close_reaction_tape in timeframe
order: M30 response, H1 confirmation or failure, then H4 acceptance/rejection.
Distinguish a full reversal from a temporary retracement; an edge probe or one
close alone does not establish hold beyond the zone.
Argue the buy thesis and the sell thesis at every meaningful zone before
choosing. A fresh failed second test at resistance without accepted price
above supports a sell-reversal thesis; the inverse at support supports a
buy-reversal thesis. Well-supported higher-timeframe structure outranks M5
local detail. EMA relations are timing evidence, one evidence category in
total. A directional basket requires independent quality evidences from
different categories. A counter-context scalp exits fully at the nearest
M1/M5 opposing level.

For a failure test, compare progress at the two tests, close location, thrust,
and effort versus reward. Declining test participation with no new progress
can show absent demand/supply; high participation with little progress can
show absorption. Neither volume condition is sufficient without a closed
price failure. A higher-timeframe extreme followed by a lower-timeframe
revisit qualifies as a second test when a close or price separation occurred
between them. After a failed second test, use the local counterbreak or the
rejection candle's broken low/high as the execution fact. Do not demand a
close through the far edge of the full four-to-five-unit zone when that local
failure trigger is already visible. Strong opposing parent pressure limits
the first leg to a starter/scalp; it does not erase a valid local failure.

For a mapped double top, a completed M1 candle that probes the equivalent
resistance zone, fails to close above it, and closes back inside/below the
tested edge is the sell trigger. Open at the next M1 open; do not wait for an
ordinary M5 confirmation or require a later counterbreak. Apply the inverse to
a mapped double bottom. A weak close near the candle extreme, accepted price
beyond the zone, insufficient target room, news/session prohibition, or fixed
geometry mismatch still vetoes the trade.

A fresh first rejection/reclaim at a mapped level with independent context and
target room is sufficient for a starter open now; a second test refines
confidence or an add, it is never a required confirmation. A routine M5 close
below/above a nearby level is not a valid wait trigger after that response is
already visible. State a second-test requirement only when current facts name a
concrete conflict. During London
and the overlap, compare the Asia high, low and bias with the current
response. An open buy at a location you call resistance or a failed top
requires a supplied accepted break/retest; the inverse holds for a sell at
support. Never invent news, FVG, levels, sessions, candles, or future price.

When `execution_profile.name` is `fixed_r_multiple_research`, explicitly test
the setup against its stop and target distances. When target_distances is
supplied, first_target remains the next opposing structural price; execution
selects the largest permitted distance that fits before it. Normal entries need a
directional M1 body of at least half the candle range, meaningful M5
participation, nearby active-side structure, and an unobstructed M5 path at
least as large as the fixed target. The trigger range may not exceed the fixed
stop plus execution/spread tolerance. During the overlap, require either
aligned M1/M5 continuation or unanimous M15/M30/H1/H4 direction with M1
execution; otherwise do not force the fixed-risk experiment. A decisive
counter-context reclaim is allowed symmetrically only at mapped structure,
with a near-full directional body, participation, and target room. An armed
close is a new-review trigger, not an automatic fill; if it has already moved
materially beyond the level, reassess the retest instead of chasing.
The completed M1 double-top/bottom failure defined above is a pattern-specific
exception to the normal half-body and M5-confirmation requirements because its
probe and close location are the trigger. With a three-unit stop and
target_distances [6, 9, 12], never invent room: six is minimum, while nine or
twelve requires the structural first_target to leave that full unobstructed
distance from entry.

<!-- prompt:basic_decision -->
<!-- version: 2.0 | strict subset of the contract for the simple review path -->
Return the output_contract JSON. Actions, skip codes, and armed-wait rules
follow the decisiveness_contract without exception. Use completed M5 data and
the core skill before any generic breakout convention. A bare BOS, a lone
wick, or a mixed trend is one evidence at most; when it is the only evidence,
prefer an armed wait at the relevant mapped zone over an invented fact, and
skip only with a valid skip_reason_code.

<!-- prompt:qwen_local_decision_contract -->
<!-- version: 1.0 | compact local LoRA evaluator -->
Return one JSON object only. Required fields: action open|wait|skip; direction
buy|sell|none; opportunity_type starter|continuation|reversal_watch|add_watch|exit_watch|none;
target_mode scalp|starter_basket|directional_basket|none; entry_zone;
invalidation; first_target; runner_target; confidence_score 0-100; confidence
LOW|MEDIUM|HIGH; reason; auction_state acceptance|rejection|balance|transition|unclear;
auction_evidence; side_change_trigger; rejection_state; rejection_level;
rejection_why; rejection_failure_condition; basket_evidence_count;
basket_evidences; sections_applied; principles_applied; cards_cited;
learning_application; analysis_disagreement; skip_reason_code; setup_identified;
decision_commitment. Open only when level, response, invalidation, and target
room are clear from closed facts. Wait when a valid plan needs a future test.
Skip when evidence, session permission, geometry, or risk is not acceptable.

<!-- prompt:qwen_cached_entry -->
<!-- version: 1.2 | cache-qualified single-position entry -->
Choose one XAUUSD paper entry from the supplied validated cache packet. The
packet's structural, level, session, playbook, minute, volume, forming-candle,
and completed-M1 facts are authoritative. Compare buy and sell from H4/H1
location through M30/M15 path, M5 response, and M1 timing. Forming candles are
context only. Prior trades, P&L, win rate, and daily direction are forbidden
inputs and must not influence the decision.

Return one JSON object only with: bias buy|sell|conditional; confidence 0-100;
summary; acknowledged_epochs; evidence_ids; and execution_plan. Copy every
supplied epoch exactly into acknowledged_epochs and cite only supplied evidence
IDs. execution_plan contains status ready|wait. A ready plan also contains side
buy|sell, entry_low_id, entry_high_id, stop_level_id, target_level_id,
volume_each 0.5, and reason. A wait plan contains only status and one concrete
blocking reason.

Confidence is entry qualification, not an outcome forecast. A ready decision
requires confidence 51 through 100 and coherent buy or sell bias. Confidence
0 through 50, conditional bias, or disagreement between bias and plan side
requires wait. This gate rejects internally contradictory judgment; it must
not be raised after losses or used to pretend valid trading losses can be
eliminated. Wins and losses remain excluded from the next entry decision.

When status is ready and bias is clearly buy or sell but optional execution
fields are missing, the deterministic execution mapper may use that bias and
the nearest complete M1 cache range, then M5 or higher only when M1 is
unavailable. Stop and target remain the nearest cache-owned levels strictly
outside that range. This is formatting recovery, not permission to invent a
price, override conditional bias, bypass provenance, or repair missing room.

Live demo decisions cannot access future prices, so historical look-ahead is
not an entry concern here. Operational validity instead means the cache is
ready, completed and forming candles remain separately labeled, the current
session still permits entry, the MT5 tick is current, and execution begins no
later than sixty seconds after the Qwen response. The runner rechecks these
facts immediately before entry; a failure expires that proposal without fill.

All entry, stop, and target boundaries must use supplied named level IDs. The
entry IDs define an executable range: for a buy, execution seeks the lowest
available ask inside the range; for a sell, the highest available bid. The
bounded execution observer may improve price within the approved range but may
not change direction, widen the range, invent a level, or extend signal life.
Use the nearest meaningful opposing level for a scalp unless validated
structure and room support a farther target. A cache status other than ready,
session permission false, missing closed response, wrong-side geometry, or no
target room requires wait. Return ready when a supplied mapped level has a
fresh closed response, coherent direction, and valid room; do not wait merely
for a perfect price after those facts exist.

<!-- prompt:qwen_trade_management -->
<!-- version: 1.1 | one-position stateful confirmed level-to-level manager -->
Manage exactly one already-open XAUUSD paper position. Entry selection is
finished; do not propose another entry, add volume, average, reverse, or create
a basket. Judge whether the original thesis remains valid from the supplied
immutable entry plan, current named levels, completed M1/M5 candles, trade-path
peak and giveback, reached favorable levels, and prior management decisions.

Return JSON only with: action hold|protect|close; thesis_state
valid|weakening|invalidated|target_response; decision_level_ref;
next_target_ref; confirmation_type none|target_rejection_confirmed|
thesis_invalidation_confirmed|momentum_reversal_confirmed|
continuation_acceptance_confirmed;
confirmation_evidence_ids; close_confirmed; and summary. Use only supplied
level references and completed-candle evidence ids.

Manage level to level. Every reached favorable named level is a review location,
not an automatic close. Hold through confirmed acceptance toward the next
supplied level. Close after a reached level rejects the position direction or
after the immutable thesis invalidation is accepted through. Both require
completed M1 and M5 evidence at exactly one supplied decision level. A
confirmed target rejection, thesis invalidation, or adverse momentum reversal
cannot be described as hold. If adverse confirmation is incomplete, action is
hold with confirmation_type none. Protect may tighten toward a supplied
confirmed level only after M1/M5 continuation acceptance and it never widens
the broker stop. Peak profit and giveback describe the trade path but never
create a fixed-dollar exit. Unrealized P&L, elapsed seconds, one tick, or one
wick is not confirmation. Deterministic validation may enforce the same closed
M1/M5 confirmation when a model response contradicts it.

<!-- prompt:qwen_cache_warmup -->
<!-- version: 1.0 | non-executing external-context warm-up -->
Build phase one of the two-sided structural briefing from the supplied,
provenance-tagged D1/H4/H1 closed candles, forming-candle facts, and
deterministic levels. This briefing is cache state, not an order and not
permission to trade. Read D1/H4/H1 for location and parent auction. Never treat
a forming candle as completed evidence. Never invent a level or evidence id.

Return one JSON object with: acknowledged_epochs; timeframe_location containing
exactly D1, H4, and H1 objects with location, auction_state, and evidence_ids;
h4_path with current_open, current_state, unfinished_movement, and evidence_ids;
nearest_lower_zone; nearest_upper_zone; unresolved_fact; and evidence_ids.
Each nearest zone contains level_id and price. Structural localization never
creates or rewires a playbook. Conditions and unresolved_fact use at most
fifteen words. If a fact is absent, name it in unresolved_fact instead of
guessing. Return JSON only.

<!-- prompt:qwen_playbook_interpretation -->
<!-- version: 1.0 | semantic conditions over deterministic wiring -->
Interpret each supplied deterministic H4 playbook record without changing its
identity, level, targets, invalidations, or evidence. The code-owned mapping is
authoritative. Produce exactly one interpretation under each supplied
playbook_id key and no additional keys. This is a two-sided watch plan, not an
order and not permission to trade.

Each interpretation returns level_id, buy_condition, sell_condition,
missing_evidence, and evidence_ids. Both conditions must name the record's
exact level_id. A buy condition must describe a bullish closed response at
that level: acceptance or held retest above, a reclaim, or rejection closing
back above. A sell condition must describe the bearish inverse below. Each
condition uses at most fifteen words and names a close, acceptance, retest,
rejection, reclaim, or failed test. Cite only the record's supplied evidence
ids. Return JSON only with acknowledged_epochs, interpretations, and
evidence_ids.

<!-- prompt:qwen_history_chunk -->
<!-- version: 1.0 | bounded raw-history localization pass -->
Analyze one deterministic chronological digest from exactly one supplied
timeframe. Its source hash and blocks cover every raw candle, while its recent
section carries exact bars. This is a non-executing external-memory operation.
Read every supplied block and recent candle, preserve the source start/end and
timeframe exactly, and cite only supplied candle evidence ids. Describe auction
path and structural changes without predicting the next trade. The digest is
one timeframe only: do not claim it is the complete current market state and do
not import facts from another timeframe.

Return JSON only with: timeframe; source_start_utc; source_end_utc;
market_path; dominant_swing_evidence_ids; unresolved_fact; and evidence_ids.
market_path and unresolved_fact each use at most fifteen words.
dominant_swing_evidence_ids contains at most two ids and evidence_ids contains
at most four supplied ids. Never invent a candle id or price.

<!-- prompt:qwen_session_warmup -->
<!-- version: 1.0 | non-executing lower-timeframe/session phase -->
Build phase two of the cache briefing from the supplied validated phase-one
structural result, current-day M30/M15/M5 closed candles, current-H1 M1 closed
candles, forming multi-timeframe candles, and deterministic UTC session facts.
This is cache state, not an order. Preserve the exact phase-one epochs and
level/playbook ids. M30/M15 describe the current path, M5 maps the local
response, and M1 supplies timing only. Never promote a forming candle to a
completed fact and never invent evidence.

Return JSON only with: acknowledged_epochs; session_read containing session,
asia_relation, asia_high, asia_low, and evidence_ids; intermediate_path
containing M30 and M15; local_map containing M5 and M1; active_playbook_ids;
structural_consistency; unresolved_fact; and evidence_ids. Every statement
must cite supplied evidence. Report a conflict instead of rewriting phase one.

<!-- prompt:qwen_context_challenge -->
<!-- version: 1.0 | deterministic cache-awareness qualification -->
Prove retrieval and localization from the supplied cache challenge. This is a
closed-book test of the supplied packet: copy exact epoch ids, prices, states,
level ids, candle ids, and UTC session values; do not estimate or improve them.
Distinguish completed candles from forming candles. Return both the conditional
buy path and conditional sell path even when one looks stronger. Cite an
evidence id for every market assertion. For the deliberately omitted fact,
return exactly one bounded data request using the supplied request contract.

Return JSON only with: acknowledged_epochs; timeframe_location; h4_open;
h4_state; session; asia_relation; nearest_lower_zone; nearest_upper_zone;
active_playbook_ids; conditional_buy_path; conditional_sell_path;
unresolved_fact; localization_answers; evidence_ids; and data_requests.
localization_answers must answer every supplied test_id without adding tests.
Confidence or explanation cannot compensate for an exact-value mismatch.

<!-- prompt:qwen_minute_shadow -->
<!-- version: 1.0 | compact non-executing minute decision benchmark -->
Review the supplied cache-backed completed-M1 packet as a shadow paper
decision. It cannot place an order. Use the supplied structural, session, and
playbook references; do not infer memory outside the packet and do not use
prior P&L or outcome history. Compare both sides before choosing. A level is a
location, not a direction. M1 times an already grounded plan and cannot invent
higher-timeframe structure.

Return JSON only: action open|wait|skip|request_data; direction buy|sell|none;
playbook_id; observed_trigger; invalidation_level_id; target_level_id;
confidence_score; buy_thesis; sell_thesis; evidence_ids; and data_requests.
Cite only ids supplied in the packet. When one required fact is missing, use
request_data with at most one request for an allowed timeframe, completed-bar
count, and field list. This response is measured and audited but never routed
to trade execution.

<!-- prompt:area_spotter -->
<!-- version: 1.1 | GLM routing role; never produces a trade decision -->
Screen one historical XAUUSD snapshot for a mapped area worth deeper review.
You route evidence; you never output an order, action, entry, stop, target, or
final direction. Use the fixed core skill and only supplied closed facts.

Score both sides independently before routing. A shortlist needs a mapped
level within realistic reach, a visible response or one precise near trigger,
and plausible room toward the next opposing level. EMA alignment or a bare
candidate signal alone cannot create a shortlist. Return flat JSON only:
shortlist (boolean), active_level, auction_state, level_response,
buy_score (0-100), buy_evidence (max 18 words), sell_score (0-100),
sell_evidence (max 18 words), target_room_read, execution_quality,
session_read, deepseek_question (the main conflict to evaluate, max 20 words),
sections_applied, reason (max 25 words).

The shortlist boolean means only "send to the independent evaluator." It does
not mean open and it does not grant the higher-scored side precedence.

When adjacent planned zones exist, active_level must name the furthest zone
actually probed. Detect equivalent retest highs/lows within that zone and
report failed progress, close location, relative participation, and any local
counterbreak in level_response. A completed M1 double-test failure close is a
visible response and must not be rejected merely for lacking a later M5 close.

When execution_profile is fixed_r_multiple_research, shortlist only if at
least one side has a meaningful mapped-zone case, a visible response or exact
near trigger, and plausible target room. Report M1 body, M5 participation,
trigger range, and target-distance fit in execution_quality, but do not veto a
structurally meaningful H4/pivot area merely because current execution geometry
is incomplete. The independent evaluator owns the fixed-profile decision.

<!-- prompt:neutral_structure -->
<!-- version: 2.0 | retained for audit/migration compatibility -->
Analyze one historical XAUUSD decision point as a neutral structure analyst.
You describe structure; you never output an order, entry, stop, target,
action, or actionability verdict. Use only closed facts. Return flat JSON:
primary_side, primary_state, primary_level, primary_evidence (max 16 words),
alternative_side, alternative_state, alternative_level, alternative_evidence
(max 16 words), session_read, participation_read, active_zones,
unresolved_fact (one genuinely open closed-bar question, or null),
summary (max 25 words).

Map historical high/low zones first, then read the latest M1/M5 bodies, wicks,
and relative tick volume for acceptance or rejection. H4/H1/M30/M15 are
context. A closed second-test rejection at mapped resistance supports the sell
side; the inverse at support supports the buy side. Repeated tests without a
fresh response can indicate breakout risk, especially in London/New York. Use
the Asia range during London as prior structure. EMA relations are timing
context only.

<!-- prompt:learning_summary -->
<!-- version: 2.0 | side-neutral canonicalization is mandatory -->
Review forty completed chronological paper-research events collectively.
Produce temporary calibration notes for the next forty decisions; one block
creates hypotheses, never certainty or permanent rules. Use only supplied completed events. Return
JSON with hypotheses, failure_pattern, next_focus, and memory_proposals. Each
proposal must include id, principle, condition, action, scope_tags,
regime_tags, counter_case, invalidation, next_test, evidence_event_ids, and
contradictions.

Canonicalization (mandatory): express every proposal through structural roles
— "in the rejection direction", "toward the next opposing level", "fade the
failed break" — never through an unconditioned buy or sell side. The condition
field must be observable at decision time from closed bars. A proposal that
cannot be stated without an unconditioned side, or whose condition is empty,
must be omitted, not softened. Outcomes are audit evidence only; never copy
outcome or direction statistics into any future decision prompt.

<!-- prompt:day_open_analysis -->
<!-- version: 1.0 | DeepSeek Pro; forward-only daily prerequisite -->
Prepare a start-of-day market briefing from the supplied closed snapshot and
prior validated knowledge only. No current-day outcome exists. Return JSON:
market_location, htf_structure, session_map, important_zones, two_sided_paths,
risk_conditions, invalidation_of_briefing, working_focus, sections_applied.
Use the supplied deterministic daily/H4 pivot_zone_map and current
potential_zone_plan when present; do not recalculate their values.
two_sided_paths must state conditional acceptance and rejection cases without
predicting an unconditional buy or sell. working_focus contains at most five
observable checks for later models. Do not output an order or trade action.

<!-- prompt:potential_zone_analysis -->
<!-- version: 1.1 | DeepSeek Pro; refreshed after each completed H4 candle -->
Interpret the supplied deterministic prior-day and prior-H4 Floor/Fibonacci
pivot zones and historical reference ladder before price arrives. Never
recalculate, widen, narrow, or invent a zone. Combine supplied H4/H1 structure
and today's completed M30/H1/H4 close-reaction tape with the sources and return JSON:
source_h4_close_utc, market_story, priority_zones, next_h4_focus,
invalidation_of_map, sections_applied. priority_zones is a list of at most six
objects with zone_low, zone_high, role (support|resistance|two_sided),
confluence_sources, acceptance_path, rejection_path, acceptance_precondition,
rejection_precondition, and evidence_needed. Each precondition must name a
specific observable closed-price event relative to that zone. For rejection,
include a failure-test path when appropriate: marginal/failed progress at an
equivalent retest followed by a completed M1 failure close back through the
tested edge; a later counterbreak increases confidence but is optional. Do not require traversal
through the far edge of the zone when a nearer closed failure would establish
the rejection. For acceptance, require a close and hold/retest beyond the
relevant edge rather than a wick.
This is a forward location plan, not a trade signal, directional gate, order,
entry, stop, or target. Both acceptance and rejection paths remain conditional.

<!-- prompt:hourly_working_review -->
<!-- version: 1.0 | DeepSeek Flash thinking; expires after one hour -->
Review only the supplied decisions and outcomes that were fully knowable by
hour_end_utc. Compare them with the prior day briefing and working memory.
Return JSON: hour_start_utc, hour_end_utc, market_state_update,
what_model_did, what_worked, what_failed, failure_causes, risk_posture,
next_hour_adjustments, invalidation, evidence_event_ids, sections_applied.
risk_posture is normal|cautious|pause_new_entries. next_hour_adjustments may
change selectivity, timing, level-response requirements, or risk posture only;
it may not ban buys/sells, prefer an unconditional side, change fixed SL/TP,
use future bars, or rewrite permanent doctrine. Every claim cites supplied
evidence ids. This is day-only working memory and expires at the next review.

<!-- prompt:day_close_review -->
<!-- version: 1.0 | separate DeepSeek Pro close-learning pipeline -->
Review the completed day after every included outcome is closed and available.
Return JSON: day_summary, regime_sequence, what_model_did, what_worked,
what_failed, failure_causes, avoided_failures, unresolved_questions,
next_day_tests, human_review_proposals, evidence_event_ids, sections_applied.
Each human_review_proposal contains principle, condition, action, counter_case,
invalidation, scope_tags, regime_tags, and evidence_event_ids. Express sides
through structural roles, never unconditional buy/sell preference. Proposals
are review candidates only: do not claim promotion or modify permanent memory.

<!-- prompt:examples -->
<!-- version: 2.0 | one example per action; prices abstracted, format binding -->
Example open (scalp):
{"active_level":"fresh M15 resistance 41xx.8-41xx.2","auction_state":"rejection",
"auction_evidence":"second M5 test closed back below zone with upper wick and above-average tick volume",
"buy_thesis":"H1 uptrend could accept above zone after retest",
"sell_thesis":"fresh failed second test, no acceptance above, room to M5 support",
"session_read":"London, price above Asia high then rejected back inside",
"side_change_trigger":"M5 close above 41xx.2 with retest hold",
"action":"open","direction":"sell","opportunity_type":"starter","target_mode":"scalp",
"entry_zone":"41xx.6-41xx.9","missing_fact":null,"invalidation":4100.4,
"first_target":4095.4,"runner_target":null,"confidence_score":68,
"confidence_notes":"clean second-test rejection; H1 uptrend limits extension, so scalp only",
"reason":"failed second test at fresh resistance, sell to nearest support",
"skip_reason_code":null,"setup_identified":true,"decision_commitment":"open",
"sections_applied":["SR-rules","entry-sell"],"cards_cited":[],"principles_applied":[]}

Example armed wait:
{"active_level":"H1 61.8 retracement 40xx.1","auction_state":"transition",
"auction_evidence":"M1 lower wicks at level but latest M5 body still closing below EMA31",
"buy_thesis":"H4 impulse up, retracement at 61.8 with first rejection wicks",
"sell_thesis":"M5 still accepting lower, no reclaim close yet",
"session_read":"New York, inside Asia range","side_change_trigger":"M5 close below 40xx.1",
"action":"wait","direction":"buy","opportunity_type":"reversal_watch",
"target_mode":"starter_basket","entry_zone":"40xx.0-40xx.4",
"missing_fact":"M1 close above 40xx.6 reclaiming the EMA cluster",
"invalidation":4000.7,"first_target":4005.9,
"runner_target":4015.5,"confidence_score":55,
"confidence_notes":"strong location, response incomplete; reclaim close still missing",
"reason":"armed buy at H1 61.8 pending one reclaim close",
"skip_reason_code":null,"setup_identified":false,"decision_commitment":"armed_wait",
"sections_applied":["fib-location","entry-buy"],"cards_cited":[],"principles_applied":[]}

Example skip (htf_conflict):
{"active_level":"M30 support 40xx.5 against H4 breakdown","auction_state":"unclear",
"auction_evidence":"snapshot h4.trend states accepted breakdown below 40xx.0; snapshot m30.support states respected demand 40xx.5 with two closed rejections — both current, directly opposing",
"buy_thesis":"respected M30 demand rejecting twice","sell_thesis":"H4 acceptance below broken support",
"session_read":"London open minutes after H4 close","side_change_trigger":"M30 close below 40xx.5 or H4 reclaim of 40xx.0",
"action":"skip","direction":"none","opportunity_type":"none","target_mode":"none",
"entry_zone":null,"missing_fact":null,"invalidation":null,"first_target":null,
"runner_target":null,"confidence_score":20,
"confidence_notes":"both timeframes hold fresh opposing evidence; no side has failed yet",
"reason":"irreconcilable H4 breakdown versus fresh M30 demand, no resolution close",
"skip_reason_code":"htf_conflict","setup_identified":false,"decision_commitment":"skip",
"sections_applied":["timeframe-roles"],"cards_cited":[],"principles_applied":[]}

---

## 3. Trade Management Heuristics -- GoldScalp88 (skills.md)

# GoldScalp88 Trading Skills — Multi-LLM Trade Manager
# Loaded at day start and sent as context before any episode begins.
# These are living skills — update them as the system learns.

---

## SKILL 1: SESSION BIAS & DAY STRUCTURE

Gold sessions provide structure and liquidity references. Bias is a **prior**, not an entry trigger.

### Deterministic session bias (system-supplied — do not invent another rule):
For each completed or in-progress session block you receive:
- session close − open **≥ +$1** → `SESSION_BIAS=BUY`
- session close − open **≤ −$1** → `SESSION_BIAS=SELL`
- otherwise → `SESSION_BIAS=NEUTRAL`

Use the **current session's** bias as the active prior. Earlier sessions' H/L remain liquidity magnets.

### Practical use (always confirm with chart structure + volume):
- **Winner TP extend**: more aggressive when the leg aligns with current `SESSION_BIAS` and expansion evidence is present.
- **Loser patience**: more patient when recovery aligns with current bias; faster kill when recovery fights bias **and** adverse acceptance is confirmed.
- **Judas / liquidity sweeps**: London often probes Tokyo H/L early. Treat that as a **hypothesis to confirm on price**, not an automatic day narrative. A sweep without acceptance back inside is not a reversal.

### How to read the session block:
```
Tokyo:  open=4010.00  close=4018.50  high=4019.80  low=4009.20
          session_move=$+8.50  SESSION_BIAS=BUY
London: ...
CURRENT SESSION BIAS: BUY (London)
```
Bias = BUY means LONG legs have a prior tailwind; SHORT recovery is fighting that prior until structure flips.

---

## SKILL 2: VOLUME-MOMENTUM SYNTHESIS

Volume on XAUUSD tick data correlates closely with institutional activity.
You receive volume as: `direction × volume_ratio_vs_session_average`

### Reading combinations:

| Pattern | What it means | Action |
|---|---|---|
| UP×2.0+ consecutive | Institutional buying, real move | Extend LONG TP aggressively |
| UP×0.5 or less | Retail noise, no conviction | Do NOT extend TP on this bar |
| UP×1.8 then UP×1.2 then UP×0.7 | Decelerating — move ending | Prepare for stall/reversal |
| DN×0.5 after high-vol UP move | Pullback on low volume | Normal, hold TP |
| DN×1.8 after high-vol UP move | Real reversal starting | Kill loser sooner |
| Volume SPIKE on TP bar (≥1.8×) | Climactic exhaustion | Strong reversal expected, open flip |
| Volume LOW on TP bar (≤0.7×) | Quiet TP hit | Reversal uncertain, maybe skip flip |
| Recovery bars with RISING volume | Real reversal | Hold loser — more recovery coming |
| Recovery bars with FALLING volume | Reversal fading | THIS IS THE KILL MOMENT |

### Volume trend field:
- `RISING`: Each of the last 5 bars has more volume than prior → momentum building
- `FALLING`: Volume decreasing → momentum fading (most important signal)
- `FLAT`: Steady, neutral

### Key rule:
**Never extend a TP based on price direction alone. Volume must confirm.**
A 4-bar upward move on declining volume is retail chasing — it reverses.
A 2-bar upward move on 2.0×+ volume is institutional — it continues.

---

## SKILL 3: EXPANSION vs EXHAUSTION DETECTION

### Expansion (move still going — extend TP, hold loser):
ALL of these together = high confidence:
- Last 3+ bars same direction
- Candle BODIES growing each bar
- Volume ratio ≥ 1.3× and RISING
- ATR ratio ≥ 1.15 (ATR5 > ATR14)
- Small or no rejection wicks on directional side
- Session supports direction (see Skill 1)

PARTIAL confirmation (2-3 of above) = moderate confidence, extend conservatively.

### Exhaustion (move ending — hold TP, watch loser for kill signal):
ANY TWO of these = caution:
- Candle bodies SHRINKING over last 3 bars
- Volume FALLING while price still moving (deceleration)
- Rejection WICKS growing on the directional side
  - Bullish move: upper wicks getting larger each bar
  - Bearish move: lower wicks getting larger each bar
- ATR ratio starting to fall back toward 1.0
- Price making same high/low but with less body (equal highs/lows)
- Episode has been running 20+ minutes (scalp exhaustion zone)

THREE or more = high confidence exhaustion. Stop extending TP. Loser kill window opening.

### The blow-off signal (strongest reversal signal):
- One very large volume bar (≥ 2.0× average) in the directional move
- Followed by the NEXT bar reversing direction on lower volume
- This is the "last flush" — institutions exit, retail is left holding
- After a blow-off: loser recovery is usually fast and sharp

---

## SKILL 4: REVERSAL QUALITY ASSESSMENT

After winner TP fires, you are watching for the reversal. Not all reversals are equal.

### Strong reversal (hold loser, big recovery coming):
- First reversal bar has volume ≥ 1.4× (institutional selling into the high/low)
- Second reversal bar confirms direction AND has equal or more volume
- ATR on reversal bars is healthy (not shrinking)
- Reversal bar bodies are medium-large (not tiny doji)
- Session has time remaining (more than 30 min in session)

### Weak reversal (kill loser at first good price):
- Reversal bars are small-bodied
- Volume on reversal bars is below average (< 0.8×)
- ATR contracting on reversal
- Reversal fighting session bias (trying to go against today's direction)

### False reversal (emergency close):
- 1-2 bars reverse direction, then original trend resumes
- Original direction bars have MORE volume than reversal bars
- Price makes new high/low in original direction after reversal bars

---

## SKILL 5: KILL TIMING — THE MOST IMPORTANT SKILL

The goal: close the losing leg at the BEST available price during the reversal.
NOT at a fixed pip level. At the moment when reversal momentum is FADING.

### The optimal kill window:
The best kill price is NOT when the reversal starts — it's when the reversal
is DECELERATING. This is the last moment of reversal momentum before it
possibly reverses again.

Signs you are IN the kill window:
1. Loser P&L has improved significantly from its worst point
2. The last 2 reversal bars have SMALLER bodies than the 2 bars before them
3. Volume on reversal is FALLING (e.g. DN×1.6 → DN×1.1 → DN×0.7)
4. A wick appearing in the ORIGINAL trend direction on the reversal bars
5. Loser is near breakeven OR at an acceptable loss level

When you see this combination: ACT. Do not wait for one more bar.
The next bar may bring a volume spike back in the original direction.

### Patience vs. decisiveness:
- At the edge (near TP, oscillating): almost always HOLD both. Wait for TP or TP_FIRED.
- First 5 bars after TP: almost always HOLD loser. Too early for kill signal.
- 5-15 bars after TP: monitoring phase. Waiting for reversal to develop.
- 15-30 bars after TP: if no reversal developing, kill loser before SL.
- 30+ bars: something unusual is happening. Explain in learning_note.
- If you closed one leg: keep the other open — do not chase flat on the next bar.

---

## SKILL 6: SESSION-SPECIFIC BEHAVIOR

These are hypotheses to calibrate against current MT5 history, not universal rules.
Current structure, volatility and participation override the session label.

### Asian (00:00-07:00 UTC):
- When range and ATR are compressed, demand close-and-acceptance confirmation for breakouts.
- Keep TP extensions conservative unless bodies, ATR and volume demonstrate expansion.
- Do not assume Asian liquidity is low or that directional moves must fail.

### London (07:00-12:00 UTC):
- First 30–60 min: often probes Tokyo H/L (liquidity sweep hypothesis). Confirm with M1 acceptance before treating as reversal.
- After confirmation, let measured structure and available room determine extension size.
- Extend TP only with expansion + volume; kill losers that fight confirmed session bias sooner.

### NY (12:00-17:00 UTC):
- Treat US data and overlap windows as event-risk context only when supplied.
- Extend TP aggressively only when current volume, ATR and structure confirm expansion.
- Use measured participation rather than assuming volume must fade at a fixed clock time.
- Do not close solely because of session time; require risk, liquidity or structure evidence.

---

## SKILL 7: KEY LEVELS AWARENESS

Levels to note in your session analysis:
- **Today's Tokyo high/low**: common London liquidity probes early in the session
- **Prior session close**: often acts as support/resistance
- **Round numbers** (4000, 4010, 4020 etc.): institutions target these for liquidity
- **Session high/low**: strong magnet — if price is near it, expect a sweep

When the loser's TP is at or near a key level: probability of reaching it is higher.
When a key level sits between current price and loser TP: acts as a magnet, pulling price there.

---

## SKILL 8: EDGE PATIENCE — DON'T CLOSE TOO EARLY

The straddle's edge is **oscillation**, not frequent intervention. Gold moves up and
down within a range. Both legs can reach profit if you let price breathe.

### What "at the edge" means:
- Either leg is **within ~150p of its TP** (price approaching target)
- Price is **oscillating** — alternating UP/DN bars, no sustained breakout
- Episode is in the **middle of the session range** — both legs still have room
- One leg is profitable and the other is at a **small loss** (-50p to -200p) while
  price is swinging — this is normal straddle noise, not a signal

### The edge-patience rule (default behavior):
**When at the edge: HOLD. Do not close early. Wait.**

Decisions belong at two moments only:
1. **TP is near** — one leg almost at target; let it hit or extend, hold the other
2. **TP has fired** — profit secured; then manage the loser with patience (Skill 5)

If you feel an urge to close on every bar, that urge is the signal to **wait longer**,
not to act. Frequent closing destroys the oscillation edge and locks in losses
that price would have reversed.

### One leg at a time — never chase both:
- If you close one leg with HIGH confidence, **keep the other open**
- Do NOT close the winner and then immediately close the loser (or vice versa)
- Do NOT close leg A on bar N and leg B on bar N+1 unless leg B has its own
  HIGH-confidence emergency signal — not because you "want to be flat"
- Closing winner + loser in the same episode when one is still recoverable =
  giving away free oscillation profit

### When early close IS still valid (override edge patience):
Only when **all** of these are true:
- Sustained institutional move (3+ bars, volume ≥ 1.5×, bodies growing)
- Loser is deep (-300p+) AND moving further away bar after bar
- No oscillation — price is trending, not swinging
- You are NOT near either leg's TP

### Oscillation mindset:
Price does not move in a straight line. A leg at -150p can be at +50p in 10 bars
if you hold through the swing. The straddle is designed for this. Your job at the
edge is to **wait for TP or wait for TP_FIRED**, then decide — not to pre-empt.

---

## SKILL 9: FAST TREND BASKET — OPERATOR-OBSERVED CANDIDATE

This is a candidate setup under observation, not a universal rule. Use it only
when live structure confirms it and audit every occurrence as `FAST_SELL_SCALP`
or `FAST_BUY_SCALP` for later comparison.

### Direction map (LLM responsibility)
- Set `FAST_SELL_SCALP` only with bearish H1/M30/M15 structure: lower highs,
  lower lows, and acceptance below a local M15/M30 level. Use the inverse for
  `FAST_BUY_SCALP`.
- Name the local entry zone, invalidation, first target, and next liquidity/base
  (including Asian-session high/low where relevant). Never select both sides.

### Entry and management (EA responsibility)
- Wait for a favorable pullback into the local zone: sell a bounce toward
  resistance; buy a dip toward support. Require M5 rejection/continuation.
- Build a bounded one-direction basket only inside the approved zone or while
  price continues profitably. Never average into an adverse move beyond invalidation.
- Take fast basket profit at the first liquidity/base target. Keep a protected
  runner only while M5 continues directionally and the M15 break level holds.
- Flatten on M5 acceptance back through invalidation. Every basket requires a
  structural stop or hard-loss cap; no-stop trading is not a valid mode.

### Required audit fields
Record mode, direction, entry-zone high/low, first entry time/price, basket
lots, add count, average entry, target, exit time/price, hold time, maximum
favorable/adverse excursion, gross/net P&L, and exit reason. Compare modes only
after enough completed examples.

---

## LEARNING NOTES SECTION
# This section is auto-populated by the system with learnings from prior days.
# Do not edit manually — the system writes here after each trading day.
# Format: [DATE] [PATTERN] [OUTCOME] [CONFIDENCE]

<!-- LEARNING_NOTES_START -->
<!-- LEARNING_NOTES_END -->

---

## 4. Proven Harmful Changes -- Do Not Reintroduce Register

<!-- document: QuantLLMBot proven harmful changes | version: 1.0 | audience: coding agents and human reviewers -->
# Proven Harmful Changes — Do Not Reintroduce Register

## Purpose and authority

This file preserves negative engineering knowledge: changes that appeared
safer or stricter but were shown by replay or MT5 demo evidence to suppress
valid behavior, create contradictory execution, or contaminate decisions.
Coding agents must read this file before changing entry validation, freshness,
confidence, evidence-citation, cache-provenance, or outcome-feedback behavior.

This is an engineering change-control register. It does not replace the market
doctrine in `store/core_skill.md`, the model contract in `store/sop.md`, or the
research approval process in `RESEARCH_LOOP.md`.

## Mandatory coding-agent procedure

Before adding, tightening, relaxing, or moving a gate:

1. Search this register for the proposed mechanism and its functional
   equivalent, not only the same variable or function name.
2. Reproduce the original evidence and the protected counter-case.
3. State why the proposal does not reintroduce an active rejected pattern.
4. Preserve the listed safe replacement and companion controls.
5. Add or update a deterministic regression invariant.
6. Run `validation/validate_e2e.py`.
7. Obtain explicit human approval before reopening an active rejection.

Renaming a rejected gate, moving it to another layer, or expressing it through
a prompt is still reintroduction. A code cleanup, safety argument, loss, or
single profitable example is not sufficient reopening evidence.

## Active do-not-reintroduce register

### PHC-001 — Exact post-Qwen M1/M5 identity gate

- **Status:** `DO_NOT_REINTRODUCE`
- **Rejected behavior:** Require current M1/M5 epochs, named-level IDs, or
  named-level prices to remain exactly equal to the entry snapshot after Qwen
  returns.
- **Evidence:** On 2026-08-05, proposal
  `paper-20260805T055843-3f41f811` returned a coherent confidence-73 buy. The
  exact-level runtime gate rejected it through
  `current_level_entry_low_id_changed`,
  `current_level_entry_high_id_changed`, and
  `current_level_target_level_id_changed`. These low-timeframe references had
  rotated during the approximately eight-minute CPU calculation.
- **Observed harm:** With uncapped Qwen time, M1/M5 objects normally advance
  before the response. Exact equality converts routine calculation latency
  into a near-universal no-trade rule.
- **Safe replacement:** Validate the cache-qualified snapshot and Qwen's
  acknowledged provenance before proposal creation. At execution, require
  confidence/direction coherence, current cache readiness, the same permitted
  UTC session/date, unchanged structural/playbook context, the same model
  digest, a current MT5 tick, live entry-zone eligibility, and the 60-second
  post-response lifetime.
- **Protected counter-case:** Proposal
  `paper-20260805T060621-c8536c12` crossed the 06:00 UTC H1 close and was
  correctly rejected because H1 changed from rejection/inside-range to
  acceptance/above-range. Higher-timeframe structural change must remain a
  runtime rejection.
- **Regression invariant:** Runner freshness compares only stable
  structural/playbook epochs; it must not compare current M1/M5 level identity
  or the minute/levels epochs for exact equality.
- **Introduced/removal boundary:** The harmful exact-level check was removed in
  Git commit `05c3fb7` after live-chain verification.
- **Reopening criteria:** A preregistered alternative must distinguish routine
  low-timeframe rotation from semantic invalidation, preserve materially more
  eligible decisions than exact equality, and pass untouched replay plus demo
  shadow evidence with explicit human approval.

### PHC-002 — Universal mandatory M1-and-M5 citation gate

- **Status:** `DO_NOT_REINTRODUCE`
- **Rejected behavior:** Require every ready entry to cite both an M1 candle and
  an M5 candle, regardless of which supplied timeframes establish the setup.
- **Evidence:** Proposal `paper-20260805T021044-08c9dcd7` cited closed
  D1/H4/H1/M30/M15 evidence, returned a coherent confidence-73 buy, and closed
  at broker-net `+1403.70`. It did not cite M1 or M5.
- **Observed harm:** Citation lists identify the facts Qwen relied on; they are
  not a checklist requiring every timeframe. A universal dual-timeframe gate
  would reject valid higher-timeframe structure even though M1/M5 facts remain
  supplied for timing and deterministic geometry.
- **Safe replacement:** Require a non-empty citation list that is a subset of
  the cache-owned evidence IDs. Keep M1/M5 data available and distinguish
  completed from forming candles, but let the cited evidence reflect the
  actual thesis.
- **Regression invariant:** Provenance validation checks ownership and
  existence of cited evidence; it does not require both M1 and M5 membership.
- **Reopening criteria:** Only multi-cohort evidence showing that a specific
  setup class requires named low-timeframe confirmation may support a scoped
  rule. A universal requirement remains prohibited without explicit human
  approval.

### PHC-003 — Recent profit/loss as a direction or entry gate

- **Status:** `DO_NOT_REINTRODUCE`
- **Rejected behavior:** Feed recent execution outcomes into the next market
  snapshot or block/force buy, sell, or wait because recent trades won or lost.
- **Evidence:** The user-approved research principle is that a logically valid
  trade may lose. Outcome analysis is already isolated from the entry packet,
  and the E2E validator protects the absence of `recent_execution_outcomes`
  from reviewer entry context.
- **Observed harm:** Outcome-conditioned direction introduces recency bias and
  allows P&L to override current closed market facts. It also makes entry
  behavior non-reproducible across otherwise identical snapshots.
- **Safe replacement:** Use outcomes only in the separate evidence/research
  loop. Promote a behavior change only after preregistered, repeated evidence
  and human review.
- **Regression invariant:** The next entry snapshot contains market facts and
  approved knowledge, never recent win/loss direction feedback.
- **Reopening criteria:** None through an ordinary code change. This requires a
  separately approved research hypothesis and a versioned model contract.

## Companion controls that must remain

Relaxing a harmful gate does not authorize removal of these controls:

- Ready entries require confidence 51–100.
- Confidence is a coherence qualification, not a profit guarantee.
- Bias must be explicit buy or sell and must agree with plan side.
- Missing or malformed confidence is zero, not an invented passing default.
- Qwen citations must be non-empty and cache-owned.
- Current cache readiness, UTC trading date/session permission, stable
  structural/playbook context, and model identity are rechecked before entry.
- The executor rechecks MT5 demo mode, current tick, live entry range, geometry,
  one-position ownership, and the 60-second post-response deadline.
- A real H1/H4 structural change during inference expires the proposal.
- Previous wins and losses do not decide the next direction.

Historical evidence includes two confidence-zero fills on 2026-08-05:
`paper-20260805T034422-942a705d` closed `-21.85`, and
`paper-20260805T044406-b6480bf7` closed `-153.50`. Their combined loss of
`-175.35` does not prove every low-confidence trade loses; it proves that a
ready plan must not contradict an explicit zero-confidence judgment.

## Record template for future findings

```text
Pattern ID:
Status: CANDIDATE | DO_NOT_REINTRODUCE | SUPERSEDED
Rejected behavior:
Evidence IDs and version boundary:
Observed harm and mechanism:
Safe replacement:
Protected counter-case:
Required regression invariant:
Removal commit or deployment boundary:
Reopening criteria:
Human approval:
```

Add a record only after evidence identifies the mechanism. Do not turn a
preference, one loss, or one win into permanent negative knowledge.

---

## 5. System Architecture Context (SYSTEM_TEXTBOOK.md)

<!-- document: QuantLLMBot system textbook | version: 1.0 | audience: humans and LLM engineering agents -->
# QuantLLMBot System Textbook

## Purpose and authority

This book explains the complete QuantLLMBot research and MT5 demo-paper
software as one system. It is written so that a new human engineer or LLM agent
can understand the stages, data contracts, ownership boundaries, failure
behavior, and evidence trail before changing anything.

This document is descriptive and educational. It does not replace the two
human-owned normative sources:

1. `store/core_skill.md` defines market-structure knowledge.
2. `store/sop.md` defines model reasoning, output, management, and learning
   contracts.

When this textbook disagrees with either canonical file, the canonical file
wins. Python owns processing and validation. Trading knowledge belongs in the
fixed store. This workspace authorizes historical research and MT5 demo/paper
execution only; it does not authorize live trading.

## How an LLM should read this system

An LLM working on this repository must keep five ideas separate:

- **Facts:** immutable completed candles, current forming candles, ticks,
  broker deals, account state, and deterministic levels.
- **Interpretation:** an LLM's bounded reading of supplied facts.
- **Decision:** an entry or management object that satisfies a typed contract.
- **Validation:** deterministic checks that decide whether the object may
  influence execution.
- **Learning:** outcome analysis kept outside the next market snapshot and
  promoted only through evidence and human review.

Never treat model confidence alone as proof that a trade will win. A minimum
confidence of 51 is one deterministic coherence qualification, alongside an
explicit direction, valid provenance, current cache/session state, and usable
geometry. Never treat a cached model response as current market state. Never
infer live-trading permission from working demo execution.

Before changing a validation or freshness gate, read
`PROVEN_HARMFUL_CHANGES.md`. It records stricter-looking mechanisms that were
shown to suppress valid behavior and the companion controls that must remain.

## The complete system at a glance

```text
Windows login
  -> unified runtime
  -> MT5 + Ollama + IIS health
  -> market-data/cache process
  -> reviewer and entry-decision process
  -> proposal log
  -> proposal runner
  -> single-position demo executor
  -> stateful trade manager
  -> MT5 close or broker safety stop
  -> broker-deal reconciliation
  -> episode/audit/learning pipeline
  -> hypothesis, replay, walk-forward, paper approval
```

There are two connected but distinct lanes:

- **GoldFlow/Qwen demo lane:** the active local website and one-position MT5
  demo process under `apps/qwen_trade_software`.
- **ResearchLab lane:** historical replay, provider comparison, learning,
  memory lifecycle, and validation under `ResearchLab`.

The lanes may share doctrine and decision contracts, but neither may silently
invent a different strategy rule.

## Stage 0: source, deployment, and runtime identity

### Source of truth

Version-controlled source lives in `D:\QuantLLMBot`. The deployed Qwen backend
lives at:

```text
C:\Users\HP\AppData\Local\QwenTradeReviewer
```

The IIS website bundle lives at:

```text
C:\inetpub\GoldFlowDesk
```

Source and deployed hashes must match after a release. Runtime logs, model
weights, locks, SQLite cache state, and generated proposals are deployment
state and are not committed.

### Unified startup

`apps/qwen_trade_software/backend/software_runtime.py` is the single launcher.
It acquires a singleton, starts or verifies MT5 and Ollama, verifies IIS, then
supervises three child processes:

- `reviewer.py` for snapshots, Qwen entry decisions, trade management, and the
  dashboard API;
- `market_context_cache.py` for deterministic cache refresh and readiness; and
- `paper_runner.py` for proposal consumption and executor launch.

The runtime restarts failed children and records health in
`logs/software-runtime.log`. Starting the website is not what starts trading;
the unified runtime is the software process, while the website is its view.

### Hard boundary

The executor verifies an MT5 demo account. A non-demo account must be rejected.
All Qwen-owned positions use magic number `26072401` and the `QWEN_` comment
prefix so unrelated and manual positions cannot enter the management path.

## Stage 1: MT5 observation and normalization

MT5 is the market and broker source of truth. The system observes:

- bid, ask, spread, quote timestamp, and symbol metadata;
- D1, H4, H1, M30, M15, M5, and M1 candles;
- positions owned by the Qwen magic/comment identity; and
- opening and closing broker deals, commission, and swap.

Completed candles and forming candles are different objects. Position zero in
an MT5 rates request is forming and cannot support a completed-close claim.
Timestamps are normalized to UTC. OHLC geometry, alignment, chronology,
duplicates and candle geometry are checked before derived context is trusted.
Historical and rollover gaps do not block readiness; missing latest/forming
candles block only while the active weekday data session should be updating.

An LLM must never turn a forming wick into a completed breakout, acceptance,
rejection, or invalidation.

## Stage 2: external market-memory cache

`market_context_cache.py` stores explicit context in SQLite/WAL. Model residency
keeps weights loaded; it does not preserve reliable market memory. The external
cache is the memory.

The cache is hierarchical:

- **L0 raw:** normalized completed/forming candles and tick facts.
- **L1 structure:** D1/H4/H1 location, parent auction, swings, zones, and
  unresolved conflict.
- **L2 levels:** deterministic named levels and their source evidence.
- **L3 playbooks:** two-sided H4 zone conditions with immutable identifiers,
  targets, and invalidations.
- **L4 day/session:** UTC session, Asia range, M30/M15/M5 path, and volume
  context.
- **L5 minute:** the newest completed M1, forming parent candles, nearby zones,
  and active playbook delta.
- **L6 position thesis:** immutable entry plan plus fills, reached levels,
  peak/giveback path, prior management, and exit evidence.

Every derived object carries a schema version, cache epoch, source interval,
source hash, evidence IDs, producer version, and expiry/invalidation state.
Replacing context creates a new epoch; it does not mutate the evidence identity
used by an older decision.

The full implementation and gate definitions are in
`CACHE_CONTEXT_ARCHITECTURE.md`.

## Stage 3: context warm-up and qualification

Warm-up prepares understanding before minute decisions. It is not a trade.

1. Load the required D1/H4/H1 history.
2. Validate raw chronology and completed/forming separation.
3. Build deterministic levels.
4. Ask Qwen for bounded structural interpretation.
5. Load current-day M30/M15/M5 and current-H1 M1 context.
6. Build UTC session and Asia-range facts.
7. Create two-sided H4 playbook interpretations without allowing Qwen to
   change code-owned prices or identities.
8. Challenge Qwen on exact epochs, locations, levels, candle identities,
   session facts, both directional paths, and bounded data requests.
9. Publish a readiness manifest.

Readiness is a conjunction of hard gates. One failed raw-data, provenance,
level, session, playbook, minute-delta, model-residency, or context-challenge
gate makes the manifest `blocked`. There is no confidence average that can hide
a failed gate.

The cache process remains operationally separate from execution, but its ready
packet is now the mandatory entry input. Entry Qwen must acknowledge the exact
structure, level, session, playbook, and minute epochs and cite only supplied
evidence IDs. A blocked, expired, or mismatched cache produces wait.

## Stage 4: compact minute context

After warm-up, the model does not need eight weeks of raw candles every minute.
The minute packet carries only the current delta plus references to validated
longer-horizon cache objects.

A normal packet contains:

- compatible cache epochs;
- current quote and age;
- latest completed M1 with evidence ID;
- forming M5/M15/M30/H1/H4 facts clearly marked as forming;
- relative volume facts;
- nearby named levels and distances;
- active playbook identity and missing evidence; and
- the open-position thesis reference when applicable.

The packet is small for latency and attention quality, not because context is
discarded. Long context remains addressable through stable cache references.
Qwen may ask for one bounded additional data packet through the typed request
contract.

## Stage 5: entry analysis

Entry selection and position management are separate problems.

When no Qwen position is open, `reviewer.py` builds an entry snapshot from:

- D1/H4/H1 structure and location;
- M30/M15 path;
- M5 local map;
- M1 timing candles;
- deterministic chart levels and respect counts;
- session context;
- volume/participation facts.

Recent wins and losses are excluded from the next entry snapshot. They remain
research evidence, not directional input.

Qwen returns a structured entry plan. Normalization requires named entry bounds,
direction, structural invalidation, structural target, reason, and one 0.50-lot
position. Basket count is forced to one. Add-ons, averaging, and simultaneous
Qwen positions are disabled.

The entry model decides **whether and where to enter**. It does not decide how
an already-open trade should react to later candles.

## Stage 6: entry validation and proposal creation

A model response is not an order. The reviewer normalizes it and creates an
immutable JSONL proposal only when its contract is usable. A ready proposal
requires confidence 51-100, an explicit buy or sell bias, and agreement between
that bias and the normalized plan side. This qualifies logical coherence; it
does not convert confidence into a guarantee or reject a valid trade because a
previous trade lost.

Important proposal fields include:

- proposal ID and completed-Qwen timestamp;
- symbol, timeframe, quote, and market snapshot;
- normalized direction and one-position execution plan;
- named entry, invalidation, and target references;
- model name, raw response, confidence, and summary; and
- human feedback and execution fields reserved for later evidence.

The proposal timestamp is recorded after model generation. Its 60-second
validity therefore begins when the model result exists, not when generation
started.

## Stage 7: proposal runner and signal expiry

`paper_runner.py` polls validated proposals every 250 milliseconds. It checks:

- the proposal has not already been processed;
- the decision is fresh;
- Qwen confidence and direction provenance still agree;
- the cache is currently ready and its structural/playbook/model identity is
  unchanged;
- the same UTC trading date and permitted session are still active;
- no Qwen position is open;
- the MT5 deal-history filled-position cap is not exceeded; and
- only one runner owns the process lock.

It then launches `paper_executor.py` with one position and the remaining signal
lifetime. If price never reaches the named entry zone inside the total
60-second lifetime, the proposal closes as `signal_expired` without a fill and
does not consume the filled-trade cap.

## Stage 8: single-position demo execution

The executor repeats the demo-account lock, proposal identity, symbol, side,
volume, entry-zone, and freshness checks. It refuses more than one position.

When the executable bid/ask enters the entry zone, the executor observes that
range briefly. For a buy it records the lowest ask; for a sell it records the
highest bid. It enters on a small retracement from the best quote, when the
bounded observation window completes, or immediately before signal expiry if
price remains inside the approved range. The range, side, and original
60-second lifetime never change. The broker receives a safety stop derived
from recent closed M1/M5 range and constrained to a 3-5 XAUUSD price-unit
distance. This safety stop protects against process/model failure; it is not
the complete management strategy.

The executor does not:

- open a basket;
- add to a winner or loser;
- average a losing thesis;
- close after a fixed number of seconds;
- close merely because gross P&L becomes positive; or
- place an automatic hard target at the model's named target.

Once filled, it emits one-second monitor events containing executable mark,
entry, current and peak favorable movement, giveback, adverse movement, gross
P&L, peak P&L, drawdown, structural target progress, stop progress, and holding
time. These events are the exact trade-path memory used by management.

## Stage 9: stateful trade management

`trade_manager.py` receives exactly one already-open position. It never creates
an entry, add-on, reversal, or basket.

The management packet contains:

- immutable entry thesis, target, and invalidation;
- current position and broker stop;
- current executable movement and gross P&L;
- recorded peak price, peak movement, peak P&L, and price giveback;
- favorable named levels reached by execution or completed M1 path;
- up to three previous management decisions;
- nearby current M5-or-higher reaction levels; and
- three completed M1 and two completed M5 candles with exact evidence IDs.

The model may return only `hold`, `protect`, or `close`.

### Hold

Hold means adverse exit confirmation is incomplete or continuation remains
valid. A hold cannot claim that target rejection, thesis invalidation, or an
adverse momentum reversal is already confirmed. If it does, validation blocks
the contradiction.

### Protect

Protect means completed M1 and M5 accepted beyond a supplied favorable level.
Protection may only tighten the existing stop at a valid named level. It cannot
widen the stop, increase volume, or protect a losing position.

### Close

Close requires:

- exactly one supplied decision level;
- the latest completed M1 candle;
- a completed M5 confirmation candle;
- at least two exact evidence IDs;
- a tested level;
- an M1 close against the position; and
- current live price still on the confirmed adverse side when the order is
  sent.

Target touch alone is not a close. A reached M5-or-higher level becomes a review
location. Rejection is confirmed when a completed M5 tests and closes back
through the level and the latest completed M1 counter-closes through it.

Immutable thesis invalidation is confirmed when the latest completed M1 and M5
both close beyond the invalidation against the position.

### Pre-model confirmation guard

Qwen on the CPU can take longer than one M1 candle. Therefore deterministic
validation checks the same human-owned M1/M5 confirmation contract before a
new slow model call. If a reached-level rejection or immutable invalidation is
already confirmed, the guard issues the validated close immediately. This is
not a dollar-profit shortcut; it is enforcement of the same structural rule
when a stale or contradictory `hold` would surrender the trade path.

## Stage 10: closure and broker reconciliation

A position can close through:

- validated `QWEN_MGR_CLOSE` management;
- the independent broker safety stop;
- broker stop-out or another broker-side terminal event; or
- an explicitly identified operational failure path.

The authoritative result comes from MT5 deals, not a dashboard estimate. The
closure event records fill, exit, gross profit, commission, swap, broker-net
profit, peak favorable movement, giveback, adverse movement, hold time, and
close reason.

For research, always reconcile:

```text
broker net = MT5 profit + commission + swap
```

An unfilled expired proposal is not a losing trade. A partial or orphan record
is not valid profitability evidence until matched to the complete broker
position lifecycle.

## Stage 11: dashboard and observability

The local dashboard API is served at `http://127.0.0.1:48632/snapshot`. IIS
serves the GoldFlow website on port 80. The dashboard is a view of runtime state,
not the execution authority.

Important deployment logs are:

```text
logs/software-runtime.log
logs/reviewer.log
logs/market-context-cache.log
logs/paper-runner.log
logs/paper-proposals.jsonl
logs/paper-executions.jsonl
logs/reviews-YYYY-MM-DD.jsonl
```

Every diagnosis should join records by proposal ID, execution ID, position
ticket, order/deal ID, model/contract version, and UTC time. Repeatedly reading
entire logs in the live loop is prohibited; incremental caches or indexed state
must serve runtime needs.

## Stage 12: historical replay and provider lane

The ResearchLab lane replays closed historical data without look-ahead:

- `runners/backtest.py` is the historical runner.
- `runners/regular_paper.py` is the regular paper path.
- `engine/provider_gateway.py` is the shared provider boundary.
- `engine/decision_validation.py` is the shared decision contract.
- `deepseek_cached.py` handles provider transport, stable prefixes, card
  selection, and role-specific analysis.

Backtest and regular paper must use the same provider gateway, schema, geometry,
and validation rules. A replay model may see only facts closed at its decision
time. Latency, spread, commission, entry-zone expiry, and fill behavior must be
represented when a result is used as evidence for the demo system.

## Stage 13: episodes, learning, and memory promotion

The fixed store contains exactly eight active files:

```text
core_skill.md
sop.md
knowledge_cards.json
principles_registry.json
review_queue.json
episodes.jsonl
audit_log.jsonl
run_state.json
```

Every win, loss, and skip is an episode. Learning summaries operate in blocks
of 40 events. A block may produce hypotheses or memory proposals; it cannot
silently rewrite doctrine.

The memory lifecycle must:

1. parse evidence identities;
2. detect duplicates and contradictions;
3. preserve side-neutral structural language;
4. require repeated evidence across date/regime blocks;
5. queue uncertain or doctrine-changing proposals for human review; and
6. record every promotion, rejection, contradiction, and status change in the
   audit trail.

Prior outcomes are research evidence. They must not be injected into a market
snapshot in a way that creates recency-based direction bias.

## Stage 14: validation and release

`validation/validate_e2e.py` is the structural gate. It checks the fixed store,
registered files, prompt sections, context-cache self-test, single-position
manager replay, entry/management separation, no removed timer/add-on behavior,
provider budgets, geometry, sessions, news guards, memory evidence parsing,
and compilation of active modules.

A normal release sequence is:

1. inspect `git status --short` and preserve user changes;
2. reproduce the observed issue from logs or a deterministic fixture;
3. change the smallest owned layer;
4. add or update a regression test;
5. run targeted self-tests and Python compilation;
6. run the complete E2E validator;
7. confirm zero open positions before replacing deployed execution files;
8. compare source/deployed hashes;
9. restart the unified runtime;
10. verify MT5, Qwen, website, dashboard, and child-process health;
11. commit and push with the exact evidence and limitations recorded.

## End-to-end example

1. A completed M1 arrives from MT5.
2. Cache ingestion stores it once and advances the minute epoch.
3. Deterministic checks validate chronology and evidence identity.
4. With no open position, the reviewer builds an entry snapshot.
5. Qwen returns a one-position plan.
6. Normalization and geometry checks create an immutable proposal.
7. The runner consumes it inside 60 seconds.
8. Bid/ask reaches the entry zone and the executor opens one demo position with
   a broker safety stop.
9. The executor records peak/giveback every second.
10. The manager receives the immutable thesis, trade path, reached levels,
    prior decisions, and closed M1/M5 evidence.
11. Continuation is held, confirmed acceptance may protect, and confirmed
    rejection or invalidation closes.
12. MT5 deals establish the broker-net outcome.
13. The event enters the separate learning and research loop.

## Non-negotiable invariants

- Historical and demo/paper only; no inferred live authority.
- One Qwen position at a time; no basket or add-on.
- Entry and management have separate contracts.
- MT5 facts and code-owned levels are authoritative.
- Completed and forming candles never share evidence semantics.
- No cached decision is reused for another snapshot.
- No fixed-dollar target or time-only close.
- Broker safety protection remains independent of model availability.
- Every mutating management action requires deterministic validation.
- Current live price is rechecked after model inference.
- Broker deals, not runner summaries, establish realized P&L.
- Learning changes require evidence and human review.
- Source, deployed hashes, model digest, prompt version, and cache epochs must be
  traceable.

## LLM pre-change checklist

Before proposing or editing code, answer:

1. Which stage owns the problem?
2. Is this fact, interpretation, decision, validation, execution, or learning?
3. Which canonical contract applies?
4. What exact evidence reproduces the issue?
5. Is the requested change engineering behavior or strategy doctrine?
6. What invariant could it break?
7. What deterministic regression test will fail before and pass after?
8. Does historical and regular paper behavior remain aligned?
9. Can deployment occur with zero open positions?
10. What result would falsify the improvement claim?
11. Does `PROVEN_HARMFUL_CHANGES.md` reject this mechanism or an equivalent?

If these questions cannot be answered, continue diagnosis; do not improvise a
trading rule.

---

## 6a. Research Loop (RESEARCH_LOOP.md)

# QuantLLMBot Profitability Research Loop

This document defines the experimental process for improving the XAUUSD paper
strategy. It does not replace `store/core_skill.md` or `store/sop.md`, and it
does not authorize live trading. Trading doctrine remains in the fixed store;
this file controls how hypotheses are proposed, tested, rejected, and promoted.

## Objective

Promote only strategy versions that demonstrate repeatable positive broker-net
expectancy on data that was not used to design the change. A higher win rate,
one profitable day, or a favorable backtest is not sufficient by itself.

Broker-net result means realized MT5 profit plus commission and swap, grouped
by the complete basket. Spread and execution price are therefore included in
the observed result. Runner summaries must reconcile to MT5 deal history before
they are used as research evidence.

## Current evidence baseline

The local logs available through 2026-08-03 contain:

- 4,450 Qwen proposals from 2026-07-27 through 2026-08-03;
- 267 execution starts, 219 execution closures, and 96 closures with fills;
- 4,041 one-second execution-monitor events; and
- several incompatible exit regimes, including cash targets/stops, timed exits,
  adaptive locks, broker stops, structural targets, and price-distance stops.

These records are valuable for generating hypotheses, but they are not one
controlled profitability experiment. Logged basket P&L also differs from MT5
broker history when one leg closes at its broker stop before the runner records
the remaining basket. Historical claims must therefore be rebuilt from broker
deals and tagged by exact strategy version.

## The loop

### Human-approval checkpoints

The following checkpoints are mandatory. Passing a technical test does not
grant permission to pass the next checkpoint automatically.

1. **Evidence approval:** present broker reconciliation, exclusions, version
   boundaries, and the observed failure. Human confirms that the evidence is
   suitable for hypothesis generation.
2. **Hypothesis approval:** present the preregistration and identify the one
   independent variable. Human approves which hypothesis may enter offline
   testing. No production behavior changes before this approval.
3. **Offline-test approval:** present contract, replay, walk-forward, and
   robustness results, including failed variants. Human decides whether the
   challenger may enter shadow paper testing.
4. **Paper-test approval:** present frozen challenger results for the declared
   blocks and duration. Human chooses promote, retain, or reject.
5. **Doctrine/memory approval:** any proposed change to `core_skill.md`,
   `sop.md`, knowledge cards, or principles follows the existing human-owned
   memory lifecycle. A profitable experiment does not rewrite doctrine by
   itself.

Between checkpoints, an agent may inspect evidence, repair measurement,
prepare deterministic tests, and write reports. It may not infer approval for
the next strategy stage. Future agents and LLM-assisted development sessions
must read this document through the workspace `AGENTS.md` instructions. The
market-decision model does not receive raw research outcomes; it receives only
the approved canonical doctrine and closed market facts.

### 1. Reconcile and qualify the evidence

Build one chronological event table joining proposal, Qwen response, fill,
monitor, MT5 deal, and exit records by proposal, execution, position, and deal
IDs. Quarantine malformed, duplicate, orphaned, or version-unknown observations
from confirmatory statistics. Record the reason for every exclusion.

Required integrity checks:

- every filled leg has exactly one MT5 opening deal and a closing deal;
- basket net P&L equals MT5 profit + commission + swap;
- decision and fill timestamps are monotonic and use UTC;
- the market snapshot contains only facts available before the decision;
- model, prompt, code, configuration, and data hashes identify the version; and
- all tested variants, including failed variants, remain in the experiment
  ledger so selection bias can be measured.

### 2. Freeze a champion

An experiment starts from one immutable champion identified by Git commit,
deployed-file hashes, Ollama model digest, prompt/SOP/core-skill versions,
configuration hash, symbol, account mode, and experiment start time. Do not
change entry, exit, target, stop, bucket, prompt, or model behavior inside a
measurement block.

### 3. Observe and decompose the champion

Use a block of 40 completed decisions/events, matching the canonical SOP
learning block. A block is diagnostic, not proof of profitability. Decompose
results into:

- broker-net expectancy and profit factor;
- win rate, average win, average loss, and break-even win rate;
- favorable/adverse price excursion and profit-capture ratio;
- entry delay, spread, commission, slippage, and signal expiry;
- direction quality versus entry quality versus exit quality;
- one/two-bucket behavior and add-on contribution;
- session, volatility, direction, opportunity type, and exit-reason cohorts;
- Qwen confidence calibration; and
- concentration: contribution of the best/worst trade and day.

Do not send raw prior profits, losses, win rates, or prior directions into the
next market decision. Outcomes belong to the separate learning pipeline; using
them as directional input creates recency feedback and contaminates the test.

### 4. Write one falsifiable hypothesis

Every proposed change must be registered before seeing its test results:

```text
Hypothesis ID:
Observation and evidence IDs:
Mechanism:
One independent variable to change:
Frozen control behavior:
Primary metric:
Secondary diagnostics:
Expected effect and minimum useful effect:
Development interval:
Untouched test interval:
Pass, fail, and abort conditions:
Known counter-case:
```

A hypothesis must name a causal mechanism, not merely “make more profit.” Only
one behavioral variable changes per basic experiment. Compound changes require
a factorial/challenger design that can attribute the effect of each component.

### 5. Test in ordered stages

1. **Contract tests:** schema, geometry, ownership, accounting, and no-lookahead
   tests must pass.
2. **Deterministic replay:** replay historical ticks with the same code path,
   recorded latency, spread, commission, and fill rules.
3. **Development window:** estimate/tune only on the declared development data.
4. **Walk-forward test:** freeze the variant, move forward chronologically, and
   evaluate on an untouched interval. Never retune on that interval.
5. **Robustness:** perturb spread, latency, entry price, start time, and the
   proposed parameter. A genuine effect should not exist at one precise value.
6. **Shadow paper:** champion and challenger receive the same closed snapshot;
   only the champion executes. Compare counterfactual decisions without mixing
   account state.
7. **Challenger paper:** after offline gates pass, run the frozen challenger on
   the demo account for confirmatory blocks.

### 6. Duration and evidence gates

Duration is evidence-driven; elapsed days alone are not enough.

- **Smoke gate:** one session verifies plumbing only; it cannot establish edge.
- **Discovery gate:** one complete 40-event block may generate a hypothesis.
- **Confirmation gate:** at least three non-overlapping 40-event blocks (120
  events) with the exact frozen version, including more than one session and
  volatility condition.
- **Paper-soak gate:** at least 20 trading days and 200 completed eligible
  decisions, whichever takes longer, without changing the candidate.

These are project gates, not universal statistical constants. If uncertainty
remains wide, testing continues. A candidate passes profitability review only
when:

- aggregate untouched broker-net expectancy is positive;
- its uncertainty interval and block results show that profit is not dependent
  on one trade or one day;
- profit factor and average-win/average-loss geometry improve by the registered
  minimum useful effect versus the champion;
- at least two of three confirmation blocks are profitable and the aggregate is
  profitable;
- costs and moderate execution perturbations do not remove the advantage; and
- broker and research-ledger P&L reconcile exactly.

Failure of the primary metric rejects the hypothesis. A favorable secondary
metric cannot rescue it. A failed hypothesis is retained as research evidence
and is not silently reworded after results are known.

### 7. Promote, retain, or reject

Produce a comparison report with the preregistration, exclusions, all tested
variants, broker-net results, uncertainty, regime cohorts, failure cases, and
reproduction command. Human review then selects exactly one outcome:

- **promote** challenger to the next paper stage;
- **retain** champion and collect more evidence; or
- **reject** challenger and record why.

Permanent learned principles still follow the existing memory lifecycle and
human-review process. One experiment never rewrites canonical doctrine.

## First registered research queue

These are candidate hypotheses, not approved changes:

1. **Exit truncation:** the profitable-time cap truncates favorable movement
   while 3-5-unit stops leave the loss distribution unchanged. Test removal of
   only the profitable-time cap against the frozen champion.
2. **Premature add-on:** adding the second 0.5-lot leg after only 0.10 favorable
   movement increases losing-basket magnitude without a proportional increase
   in broker-net expectancy. Test one bucket versus the existing add-on rule.
3. **Target-horizon mismatch:** far structural targets combined with short
   adaptive exits produce inconsistent holding geometry. Test a deterministic
   target-room qualification while leaving direction logic unchanged.
4. **Decision contamination:** supplying recent outcome history to Qwen changes
   direction/selectivity through recency rather than current market structure.
   Run a paired shadow test with and without outcome context.
5. **Accounting defect:** runner closure records understate multi-leg broker-stop
   losses. Correct reconciliation before using runner P&L for any hypothesis.

Only hypothesis 5 is a measurement repair and may precede profitability tests.
The behavioral hypotheses must be tested separately in the order selected by
human review.

## Registered investigation A3-2026-08-03

### Evidence approval packet

Source of truth: MT5 XAUUSDr deal history for magic `26072401`, grouped by the
opening execution comment and complete position lifecycle. Period: 2026-08-03
UTC. This packet describes one day and generates hypotheses; it does not prove
a general effect.

Broker-net basket results:

- 12 completed baskets: 7 wins and 5 losses;
- net result: -552.35;
- average win: +49.13;
- average loss: -179.25;
- profit factor: 0.384; and
- break-even win rate implied by the observed average payoff: about 78.5%,
  versus the observed 58.3%.

The three dominant losses were:

| Basket | Side/legs | Favorable price result | Broker-net result |
|---|---:|---:|---:|
| `QWEN_ec950a85` | sell / 2 | -2.519 | -258.90 |
| `QWEN_417c8be4` | buy / 2 | -3.405 | -347.50 |
| `QWEN_ff54ebc8` | sell / 1 | -5.000 | -253.50 |

The six earlier winners captured only 0.266-1.296 favorable price units and
netted +19.65 to +122.65. This is direct evidence of payoff asymmetry: routine
winners were realized at substantially smaller price movement than full-stop
losers. Two losing baskets also carried two 0.5-lot legs, so the add-on may
have amplified the left tail. The one-leg five-unit stop demonstrates that
bucket count is not the only cause.

The runner log understated stopped multi-leg losses because it recorded the
remaining live basket after one broker-side closure. For example, the runner's
partial loss did not equal the complete MT5 basket. All primary metrics for
this investigation therefore use broker deals.

### Candidate hypothesis A3-H1: marginal add-on expectancy

```text
Hypothesis ID: A3-H1
Observation: two of the three dominant losses carried two 0.5-lot legs.
Mechanism: the second leg is added after only 0.10 favorable price movement,
           before continuation is established, increasing stop-loss exposure
           more than it contributes to profitable baskets.
Independent variable: maximum executed legs, one versus current add-on rule.
Frozen control: direction, entry zone, first-leg volume, stop calculation,
                target, exit logic, prompt, model, TTL, and market data.
Primary metric: broker-net expectancy per eligible proposal.
Secondary metrics: second-leg marginal expectancy, average loss, average win,
                   profit factor, fill rate, and favorable/adverse excursion.
Minimum useful effect: positive untouched expectancy and at least 20% better
                       profit factor than the champion without relying on one
                       trade or day.
Development data: declared historical interval ending before the untouched
                  test interval; exact boundary recorded before replay.
Untouched test: chronological walk-forward interval plus three 40-event paper
                confirmation blocks after offline approval.
Pass: primary and duration gates in this protocol are satisfied.
Fail: untouched expectancy is non-positive or improvement is concentrated in
      one trade/day.
Counter-case: a valid positive-direction add-on may create the runner profit
              that pays for wide stops; forcing one leg could reduce winners
              proportionally and leave expectancy unchanged.
```

Status: **awaiting evidence and hypothesis approval**. No behavior change is
authorized by this registration.

### Candidate hypothesis A3-H2: winner truncation

The profitable-time cap and adaptive profit lock may realize winners before
they can offset the unchanged 3-5-unit loss distribution. This remains a
separate hypothesis. It must not be combined with A3-H1 in a basic experiment,
because changing both bucket count and exit duration would prevent causal
attribution.

## Research references and videos

- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
  describes repeatable test, evaluation, verification, validation, uncertainty,
  benchmarking, monitoring, and documented change management.
- [Federal Reserve model-validation guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm)
  covers conceptual soundness, benchmarking, outcomes analysis, backtesting,
  monitoring, and recalibration.
- [MetaTrader 5 strategy-testing documentation](https://www.mql5.com/en/docs/runtime/testing)
  explains testing rule implementation and historical profitability in the MT5
  Strategy Tester.
- [Bailey et al., The Probability of Backtest Overfitting](https://scholarworks.wmich.edu/math_pubs/42/)
  explains why ordinary holdouts and selecting from many backtests can produce
  misleading winners.
- [López de Prado video library](https://www.quantresearch.org/Videos.htm)
  includes “How easy is it to overfit a backtest?” and Cornell lectures on
  financial-machine-learning validation.
- [NIST AI RMF explainer video](https://www.nist.gov/video/introduction-nist-ai-risk-management-framework-ai-rmf-10-explainer-video)
  introduces the lifecycle framework.
- [NIST measurement probes webinar](https://www.nist.gov/video/nist-information-technology-laboratory-ai-webinar-series-building-measurement-probes-agentic)
  shows how to build traceability and evaluation probes into agentic systems.
- [Official MetaTrader 5 testing help and video](https://www.metatrader5.com/en/terminal/help/algotrading/testing)
  demonstrates strategy testing and visual verification.
- [MIT OpenCourseWare finance lecture videos](https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/resources/lecture-videos/)
  provide supporting quantitative-finance foundations.

---

## 6b. Improvement Guide (IMPROVEMENT_GUIDE.md)

<!-- document: QuantLLMBot improvement guide | version: 1.0 | audience: humans and LLM engineering agents -->
# QuantLLMBot Improvement Guide

## Purpose

This guide defines how improvements are proposed, tested, approved, and
released. It divides work into two independent sections:

1. **Code and architecture improvement** changes reliability, latency,
   observability, state handling, or validation without intentionally changing
   trading judgment.
2. **Strategy improvement** changes when the system enters, holds, protects,
   closes, or skips and therefore requires profitability research.

Do not hide a strategy change inside a refactor. Do not demand profitability
proof from a pure logging fix. Classify the work before editing.

This guide supplements `SYSTEM_TEXTBOOK.md`. Canonical trading knowledge and
model contracts remain in `store/core_skill.md` and `store/sop.md`. The full
profitability experiment protocol remains in `RESEARCH_LOOP.md`.

## Shared improvement loop

Every improvement follows the same evidence chain:

```text
observe -> reconcile -> classify -> hypothesize -> preregister
-> reproduce -> change one owned variable -> validate -> compare
-> paper soak -> human decision -> document -> release or reject
```

### Required proposal record

```text
Improvement ID:
Category: code_architecture | strategy
Observed problem:
Evidence IDs and version boundary:
Owning stage and files:
Mechanism or root-cause hypothesis:
One primary change:
Frozen behavior:
Primary pass metric:
Secondary diagnostics:
Regression and counter-case:
Abort condition:
Rollback method:
Human approval required at:
```

If the proposal cannot name one primary change, split it. If evidence spans
incompatible code or strategy versions, separate the cohorts before measuring.

# Section I: Code and Architecture Improvement

## Objective

Make the system more correct, reproducible, observable, restart-safe, and fast
without silently changing the market decision policy.

Examples include:

- preventing duplicate processes or proposals;
- indexing runtime state instead of scanning whole JSONL logs;
- repairing broker-deal reconciliation;
- preserving peak/giveback state after restart;
- reducing cache packet assembly time;
- detecting stale epochs or stale model decisions;
- separating entry and management services;
- improving deployment hash checks; and
- adding typed validation and deterministic fixtures.

## Architecture principles

### One owner per responsibility

- MT5 owns quotes, positions, and deals.
- Cache code owns data identity, epochs, and deterministic derived facts.
- Canonical Markdown owns trading knowledge and LLM instructions.
- Entry reviewer owns proposal formation.
- Runner owns fresh proposal consumption.
- Executor owns one fill and broker safety protection.
- Trade manager owns hold/protect/close decisions.
- Deterministic validators own permission to mutate execution state.
- Memory lifecycle owns evidence promotion.
- Unified runtime owns startup and supervision.

Duplicated ownership creates contradictory behavior. Move behavior to its owner
instead of adding another patch in a downstream layer.

### Events are immutable; current state is indexed

JSONL is the audit history. SQLite or bounded in-memory indexes are the live
state. A live loop must not repeatedly parse a growing full-history file.
Restart reconstruction should be explicit, bounded, idempotent, and tested.

### Stable contracts, replaceable implementations

Provider, cache, entry, management, execution, and learning layers exchange
typed objects. A provider/model can change only if it still satisfies the same
contract or the contract is deliberately versioned and tested.

### Fail closed at mutation boundaries

A diagnostic cache failure may report and continue refreshing. A stale or
invalid decision must not create, add to, protect, or close a position. Broker
safety protection remains available even when Qwen or the website fails.

### Observability before optimization

Every performance or correctness claim must be measurable. Record:

- snapshot, model-start, model-end, validation, order-send, and fill times;
- prompt tokens, output tokens, load, prompt-evaluation, and generation time;
- quote at snapshot, response, validation, and fill;
- cache epochs and evidence IDs;
- entry/management contract versions;
- source Git commit and deployed hashes;
- peak/giveback and every management action; and
- broker deal reconciliation.

## Engineering workflow

### 1. Reproduce

Use the smallest deterministic fixture that preserves the bug. For a runtime
incident, extract only the linked proposal, execution, position, reviews, and
deals. Keep UTC chronology. State which version produced the evidence.

### 2. Locate ownership

Examples:

- wrong candle completeness -> cache/ingestion;
- invented level accepted -> decision validation;
- duplicate order -> runner/executor ownership;
- good decision executed late -> latency/freshness boundary;
- correct peak forgotten -> position-thesis memory;
- dashboard number differs from broker -> reconciliation/view layer.

### 3. Define invariants

Write assertions before implementation. Typical invariants:

- one runtime, reviewer, runner, and Qwen position;
- one proposal processed at most once;
- one fill maps to one opening deal and one position lifecycle;
- no live-account execution;
- completed evidence never references a forming candle;
- no action after signal expiry;
- no stop widening during protection;
- no Qwen close without validated evidence; and
- source/deployment hashes match.

### 4. Implement minimally

Change the owning layer only. Preserve public schemas unless intentionally
versioning them. Avoid new runtime files when an existing indexed store or
event stream already owns the state. Never place trading doctrine in Python.

Before changing any entry, freshness, confidence, citation, cache-provenance,
or outcome-feedback gate, read `PROVEN_HARMFUL_CHANGES.md`. The proposal must
state which active rejected patterns were checked and why the implementation
does not recreate them functionally in another layer or prompt. Reopening a
rejected pattern requires its documented counter-evidence and explicit human
approval.

### 5. Test in layers

1. Pure unit/fixture test for the observed failure.
2. Contract/schema and invalid-input tests.
3. Restart/idempotence test for state changes.
4. Python compilation and static source checks.
5. `validation/validate_e2e.py`.
6. Shadow runtime or no-position health test.
7. Demo deployment only after confirming zero open positions.

### 6. Release safely

Record source hashes, deployed hashes, processes, ports, model residency, MT5
mode, open-position count, and E2E result. Commit only related files. Push the
reviewed branch. Keep rollback as a known prior commit and deployed-file set.

## Engineering acceptance gates

A code/architecture change passes only when:

- the original deterministic reproduction now passes;
- all existing E2E checks pass;
- no unrelated invariant changes;
- restart behavior is equivalent to uninterrupted behavior;
- malformed/stale inputs fail closed;
- runtime metrics demonstrate the claimed latency or resource improvement;
- source and deployment hashes match; and
- dashboard/audit outputs remain reconcilable to MT5.

Profitability is not the primary gate for a pure engineering repair, but the
repair must be checked for accidental strategy changes. If entry or exit counts
change, reclassify the affected part as strategy work.

## Architecture improvement queue

These are investigation candidates, not automatically approved changes:

1. **Active-session freshness:** ignore historical, rollover, and off-session
   gaps; treat only a stale latest/forming candle during the active weekday
   data session as missing data.
2. **Management concurrency:** allow the closed-candle confirmation guard to
   observe new evidence independently while a slow model generation is active.
3. **Indexed proposal/deal state:** eliminate remaining full-file scans in
   reviewer startup and recovery paths.
4. **Contract-version dashboard:** show source commit, SOP version, manager
   contract, model digest, and deployed hash on the website.
5. **Unified replay fixture library:** convert every material incident into a
   versioned no-look-ahead regression case.
6. **Broker reconciliation service:** continuously join proposal, execution,
   position, and deal IDs and flag orphans before research summaries run.

# Section II: Strategy Improvement

## Objective

Improve untouched broker-net expectancy through mature, explainable
market-structure behavior. A profitable day, high win rate, attractive chart,
or one repaired trade is hypothesis evidence—not proof.

Strategy work includes any change to:

- session permission or setup selection;
- level interpretation;
- entry direction, timing, or zone;
- target or invalidation selection;
- hold, protect, or close criteria;
- position size, stop geometry, or trade count; and
- model prompts containing market judgment.

## Keep entry and management experiments separate

An entry experiment asks:

- Was price at a meaningful location?
- Was the side supported by fresh rejection or acceptance?
- Was the entry late or directly into opposition?
- Was there structural room to the next level?
- Did session and participation support the setup?

A management experiment asks:

- Did the original thesis remain valid after entry?
- Which favorable levels were reached?
- Was continuation accepted or rejected?
- How much of maximum favorable excursion was captured?
- Was invalidation recognized before the broker safety stop?
- Did the model hold, protect, or close with valid evidence?

Do not change entry and exit behavior in one basic experiment. Otherwise a
better result cannot be attributed.

## Strategy evidence table

For every eligible decision, preserve:

```text
decision/proposal/execution/position/deal IDs
Git, model, prompt, SOP, core-skill, and configuration versions
closed snapshot and evidence IDs
session and volatility regime
entry plan and actual fill
spread, commission, swap, and slippage
maximum favorable and adverse price excursion
levels approached, reached, accepted, rejected, or invalidated
each hold/protect/close decision with response latency
exit reason and broker-net result
counterfactual result only from data available at that time
```

Exclude or quarantine version-unknown, orphaned, duplicate, malformed, or
unreconciled observations from confirmatory statistics.

## Metrics that matter

Primary profitability metrics:

- broker-net expectancy per eligible proposal and per filled trade;
- total broker-net result;
- profit factor;
- average win, average loss, and payoff ratio;
- break-even win rate versus observed win rate; and
- uncertainty across non-overlapping blocks.

Entry diagnostics:

- fill rate and signal-expiry rate;
- direction correctness at fixed horizons;
- entry delay and price drift;
- distance to opposing level;
- MAE before first favorable progress; and
- session/setup cohort performance.

Management diagnostics:

- maximum favorable excursion (MFE);
- maximum adverse excursion (MAE);
- captured price movement;
- profit-capture ratio: realized favorable movement divided by MFE;
- peak-to-exit giveback;
- time from level test to confirmed management action;
- invalidation-to-exit delay;
- fraction of exits by reached-level rejection, invalidation, Qwen close,
  broker safety stop, and operational failure; and
- counterfactual value of hold/protect/close at the same closed evidence point.

Never optimize win rate alone. A system with many small wins and a few full
stops can have negative expectancy.

## Strategy hypothesis template

```text
Hypothesis ID:
Entry or management:
Observation and evidence IDs:
Structural mechanism:
One strategy variable changed:
Champion behavior frozen:
Development interval:
Untouched interval:
Primary metric and minimum useful effect:
Secondary diagnostics:
Expected session/regime scope:
Counter-case:
Pass condition:
Fail condition:
Abort/safety condition:
```

The mechanism must be structural and observable from closed facts. “Ask Qwen
to make more profit” is not a hypothesis.

## Ordered strategy testing

### 1. Incident replay

Convert the motivating trade or skip into a closed-data fixture. Confirm that
the champion reproduces the behavior and the challenger changes only the
registered variable. An incident replay proves plumbing, not general edge.

### 2. Historical deterministic replay

Use chronological ticks/candles, realistic spread, commission, latency, signal
expiry, entry-zone fill logic, and the same validation path as paper execution.
No future candle, final daily high/low, or later model result may enter an
earlier decision.

### 3. Development and untouched walk-forward

Tune only on the declared development interval. Freeze the challenger before
the untouched interval. Do not repair the rule after seeing untouched results;
register a new hypothesis instead.

### 4. Robustness

Perturb spread, latency, entry price, session start, and nearby thresholds.
Test more than one volatility and directional regime. Reject improvements that
exist only at one exact value or depend on one trade/day.

### 5. Shadow comparison

Champion and challenger receive the same closed snapshot. Only the champion
executes. Record both decisions, latencies, evidence, and counterfactual
management actions without mixing account state.

### 6. Frozen demo-paper confirmation

After human approval, allow the challenger to execute on MT5 demo without
changing it inside a measurement block. Use the project evidence gates from
`RESEARCH_LOOP.md`: one 40-event block for discovery, at least three
non-overlapping blocks for confirmation, and the declared paper-soak duration
before a profitability claim.

## Entry improvement checklist

For each entry hypothesis test:

1. Identify H4/H1 location before M30/M15 path.
2. Identify the active M5-or-higher zone and its freshness.
3. Compare acceptance, rejection, and unfinished retracement.
4. Use M1 only for timing an already-grounded plan.
5. Check session permission and Asia-range relationship.
6. Confirm structural room to the next opposing level.
7. Reject a late chase or entry directly into respected opposition.
8. Record the exact invalidation and target level known at entry.
9. Keep one position and fixed experiment sizing unless size itself is the
   registered variable.

## Management improvement checklist

For each management hypothesis test:

1. Preserve the immutable entry thesis.
2. Preserve peak price, MFE, MAE, giveback, and reached levels across calls and
   restarts.
3. Separate a target touch from a confirmed target response.
4. Hold through confirmed acceptance toward the next named level.
5. Protect only after completed continuation acceptance and never widen risk.
6. Close reached-level rejection only with completed M1/M5 evidence.
7. Close immutable invalidation when completed M1/M5 accept beyond it.
8. Revalidate current live price before executing a delayed decision.
9. Measure capture ratio and confirmation delay, not only final P&L.
10. Keep broker safety protection independent of model availability.

## Learning and promotion

After every 40-event block:

1. reconcile outcomes to broker deals;
2. separate entry, direction, fill, and exit causes;
3. identify repeated structural conditions, not unconditional sides;
4. record contradictions and counter-cases;
5. create bounded hypotheses or memory proposals;
6. retain failed hypotheses to measure selection bias; and
7. require human review before doctrine or permanent memory changes.

A learned principle should read like:

```text
When [observable structural condition], prefer [bounded structural action]
until [explicit invalidation], except when [counter-case].
```

It must not read like “buy after losses,” “sell because today is bearish,” or
another outcome-contaminated directional command.

## Strategy acceptance gates

A challenger advances only when:

- the exact registered primary metric improves on untouched data;
- aggregate broker-net expectancy is positive;
- improvement is not concentrated in one trade, day, or session;
- at least two of three confirmation blocks are profitable and aggregate
  confirmation is profitable;
- costs and reasonable latency/spread perturbations do not erase the effect;
- entry and management attribution is clear;
- broker and research-ledger results reconcile; and
- the human chooses promote rather than retain or reject.

If the primary metric fails, reject the hypothesis. A favorable secondary
chart or win-rate metric cannot rescue it.

## Example: converting an incident into research

Observation: a one-position buy reached a favorable structural area and later
closed at the broker safety stop.

Incorrect reaction:

```text
Always close when profit reaches $200.
```

Researchable reaction:

```text
Hypothesis: preserving reached-level and peak/giveback state, then enforcing a
completed M1/M5 rejection at the furthest reached M5-or-higher level, improves
broker-net capture ratio without materially truncating accepted continuation.
```

The incident may become a regression fixture. Profitability promotion still
requires untouched replay and frozen paper evidence.

## LLM improvement decision tree

```text
Did market behavior intentionally change?
  no -> code/architecture section
  yes -> strategy section

Is the evidence reconciled and versioned?
  no -> repair evidence first
  yes -> write one falsifiable hypothesis

Can one deterministic fixture reproduce it?
  no -> continue diagnosis
  yes -> change the owning layer and add the fixture

Did all contracts and E2E tests pass?
  no -> do not deploy
  yes -> follow the appropriate engineering or strategy evidence gate
```

## Definition of a complete improvement

An improvement is complete only when the repository contains:

- a precise observation and version boundary;
- a classified hypothesis;
- a regression or research fixture;
- the smallest owned change;
- validation results;
- measured limitations and counter-cases;
- deployment/rollback information when applicable;
- broker reconciliation for outcome claims; and
- a human decision to promote, retain, or reject when strategy is affected.

---

## 7. Cache & Context-Validation Architecture (CACHE_CONTEXT_ARCHITECTURE.md)

# Qwen Market Cache and Context-Validation Architecture

Status: execution-integrated implementation v3 (qualified 2026-08-04). The cache,
deterministic gates, Qwen validation, readiness manifest, and compact-minute
packet are implemented and all readiness gates pass. Entry Qwen now receives
only a ready, provenance-matched cache packet; a blocked cache deterministically
produces wait and cannot create an executable proposal. This does
not authorize a production strategy change and does not replace the
human-owned doctrine in `store/core_skill.md` or `store/sop.md`.

Implementation: `apps/qwen_trade_software/backend/market_context_cache.py`.
The unified runtime supervises its deterministic cache-update mode as a
separate context process consumed by the reviewer. Heavy Qwen qualification is manual/off-hours because
CPU warm-up must not hold the shared model lock ahead of the execution
champion. A successful challenge creates a certificate bound to the prompt and
validator contract version plus exact model digest. Volatile candle epochs use
that certificate while deterministic gates continue to validate current data.
Its SQLite database is runtime state outside the fixed eight-file research
store.

## Verified checkpoint (2026-08-04)

- Live MT5 demo ingestion passed for D1/H4/H1/M30/M15/M5/M1, with forming
  candles held separately from immutable completed candles.
- Gate A, Gate B, the incremental/restart fixture, and the compact minute
  response validator passed.
- The current compact minute packet measured 2,425 bytes, approximately 606
  tokens.
- The second consecutive ready refresh measured 4.9 ms ingestion and 1.6 ms
  minute assembly. These are observations, not latency guarantees.
- Ollama prompt-prefix reuse was observed: minute prompt evaluation fell from
  56.56 seconds on the context-switch call to 0.24 seconds on the immediately
  repeated call.
- On the current CPU-only host, the latest warmed Qwen minute latency was 37.33
  seconds: prompt evaluation was 0.24 seconds and output generation was 36.75
  seconds. Cache design removes repeated context work but cannot remove CPU
  token-generation time.
- Qwen passed exact D1/H4/H1 location, H4 state, nearest-zone and evidence
  localization, session/Asia facts, three playbook identities, completed versus
  forming H1 localization, deterministic invalidations, bounded data-request
  behavior, and the compact minute response test.
- Level identity, target, and invalidation wiring is code-owned. Qwen supplies
  bounded semantic response conditions keyed by immutable playbook IDs; it
  cannot rewrite geometry. Generic semantic tokens are bound to the expected
  level only when they contain no competing supplied level.
- Consecutive deterministic-only refreshes published `ready` with every flag
  true and no failures, proving that new candle epochs do not trigger another
  heavyweight qualification call.

## Research basis

The architecture follows hierarchical external memory rather than relying on
an LLM's hidden conversation state, consistent with the memory hierarchy in
[MemGPT](https://arxiv.org/abs/2310.08560). Exact provenance and separate
faithfulness/context checks follow the evaluation concerns described by
[RAGAS](https://arxiv.org/abs/2309.15217). Raw bars remain outside the prompt
because long-context retrieval can degrade when relevant facts are buried in
the middle, as shown in
[Lost in the Middle](https://arxiv.org/abs/2307.03172).

The runtime uses [SQLite WAL](https://www.sqlite.org/wal.html) for local
one-writer/multiple-reader access, the official Ollama
[`keep_alive` and timing fields](https://docs.ollama.com/api/generate), and MT5's
documented rule that bar position zero is the current forming bar
([copy_rates_from_pos](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py)).

## Outcome

The model performs one deep structural warm-up, proves that it can retrieve and
apply that context, and then receives a small incremental packet after each
completed M1 candle. The model weights remain resident in RAM/VRAM. Raw market
history, derived structure, level playbooks, session state, live deltas, and
position theses are separate versioned cache layers.

The application never relies on hidden LLM memory. Every decision records the
exact cache epochs and evidence IDs supplied to Qwen, so the decision can be
replayed without future data.

## Design principles

1. MT5 candles and ticks are the raw source of truth.
2. Completed and forming candles are never mixed.
3. Raw history is stored once and updated incrementally.
4. Deterministic calculations create levels and session facts.
5. Qwen interprets supplied facts; it does not invent or recompute them.
6. Long-term analysis is refreshed on structural events, not every minute.
7. The live packet contains deltas and references, not eight weeks of raw data.
8. Qwen may request bounded additional evidence through a typed contract.
9. A deterministic validator, not Qwen confidence, controls readiness.
10. No entry decision is valid without cache provenance and freshness checks.

## Runtime storage

Use one SQLite database in WAL mode at the deployed runtime location:

```text
C:\Users\<user>\AppData\Local\QwenTradeReviewer\cache\market_context.sqlite3
```

The database is runtime state and is excluded from Git. It is not added to the
fixed eight-file `ResearchLab/store`. JSONL remains the immutable audit stream,
but trading services no longer scan complete JSONL files for live state.

SQLite provides atomic updates, indexed timestamp queries, crash recovery, and
one-writer/multiple-reader operation without adding a separate service. The
hot current state is also held in memory and rebuilt from SQLite after restart.

## Cache layers

### L0: raw market cache

Stores normalized MT5 observations:

- eight complete weeks of D1 and H4 candles;
- two complete weeks of H1 candles;
- current UTC day of M30 and M15 candles;
- completed M5 candles from the active session/day boundary;
- completed M1 candles for at least the current H1 candle;
- the current forming M1/M5/M15/M30/H1/H4/D1 state; and
- sampled tick facts: bid, ask, spread, timestamp, and tick flags.

Completed-candle key:

```text
(symbol, timeframe, open_time_utc)
```

Required candle fields:

```text
open, high, low, close, tick_volume, spread, real_volume,
open_time_utc, close_time_utc, is_complete, source, ingested_at_utc
```

Completed rows are immutable. Forming rows live in a separate table and are
upserted until the timeframe closes, then promoted atomically to completed.

### L1: structural cache

Generated after raw-history validation. It contains compact interpretations
with evidence references:

```text
D1/H4/H1 location and auction state
completed parent swings
accepted/rejected zones
current H4 path and unfinished movement
nearest upper/lower structural zones
historical response summaries
unresolved structural conflicts
source candle IDs and source hash
```

It refreshes at startup, after every completed H4 candle, after a completed D1
candle, or when its source data is repaired. H1 completion updates the H1
subsection without rebuilding unrelated D1/H4 history.

### L2: deterministic level cache

Contains the existing cheat-sheet levels plus their provenance:

```text
level_id, timeframe, zone_low, zone_high, role, source_candle_ids,
calculation_method, created_at_utc, valid_from_utc, invalidated_at_utc
```

Levels are zones. The deterministic engine calculates them from completed
candles; Qwen assigns conditional interpretation only after a visible response.

### L3: H4 level-playbook cache

At every new H4 candle, Qwen receives validated structural/level caches and
prepares a two-sided playbook for each nearby important zone:

```json
{
  "playbook_id": "H4-20260803T1200Z-L03",
  "level_id": "H4_ZONE_03",
  "approach_state": "below_approaching",
  "buy_condition": "accepted close and held retest",
  "sell_condition": "failed test and close back inside",
  "buy_invalidation": 4063.2,
  "sell_invalidation": 4066.1,
  "lower_target_id": "M30_ZONE_02",
  "upper_target_id": "H4_ZONE_04",
  "missing_evidence": ["closed response at zone"],
  "evidence_ids": ["candle:H4:...", "level:H4_ZONE_03"],
  "status": "watch",
  "expires_at_utc": "next H4 close"
}
```

The playbook is a plan, not an order. It changes status through deterministic
events: approaching, testing, rejected, accepted, invalidated, or expired.

### L4: day and session cache

Contains:

- UTC trading date and current session;
- session start/end and time remaining;
- Asia high, low, close path, and completed bias description;
- completed M5 candles since the relevant session boundary;
- today's completed M15/M30 candles;
- current day relation to structural zones; and
- relative tick-volume facts by timeframe.

It updates on M5/M15/M30 close and session transition. Session statistics are
calculated in code, never inferred from the model clock.

### L5: live minute cache

Updated after each completed M1 candle and on material tick events. It contains
only what changed:

```text
latest completed M1 OHLC and tick volume
forming M1 state
forming M5/M15/M30/H1/H4 state
current bid/ask/spread and quote age
distance/status for at most three nearby active zones
active playbook ID and missing evidence
volume change versus completed-candle baselines
position thesis reference when a Qwen basket is open
```

The decision packet is assembled from this layer plus short references to L1,
L3, and L4. Raw long history is not retransmitted every minute.

### L6: position-thesis cache

Created from the validated entry decision and tied to exact position tickets:

```text
decision_id, playbook_id, direction, entry evidence, fill prices,
structural invalidation, targets, normal-oscillation description,
continuation condition, exit condition, next review event,
peak/adverse movement, cache epochs, and rule version
```

Qwen reviews the thesis on a completed M1 candle or named structural event.
Deterministic broker protection remains available between model calls.

## Cache epoch and provenance contract

Every derived cache object contains:

```json
{
  "schema_version": 1,
  "cache_type": "structural",
  "cache_epoch": "structural-XAUUSDr-20260803T120000Z-v1",
  "symbol": "XAUUSDr",
  "created_at_utc": "...",
  "valid_as_of_utc": "...",
  "source_start_utc": "...",
  "source_end_utc": "...",
  "source_hash": "sha256:...",
  "producer_version": "git:<commit>",
  "model_digest": "ollama:<digest>",
  "expires_at_utc": "...",
  "invalidated_at_utc": null,
  "invalidation_reason": null,
  "evidence_ids": []
}
```

Every Qwen request, response, proposal, fill, management decision, and closure
records the relevant epoch IDs. Cache replacement creates a new epoch; it never
silently mutates the evidence identity used by an earlier decision.

## Warm-up pipeline

Warm-up is a separate supervised process from minute decisions:

1. Start MT5 and Ollama; confirm demo account and symbol.
2. Load and pin `qwen-trading-v002:latest` with `keep_alive=-1`.
3. Fetch only missing L0 candle ranges from MT5.
4. Validate chronology, completeness, timeframe alignment, and closed status.
5. Build deterministic levels and session facts.
6. Run Qwen structural analysis over eight-week D1/H4 and two-week H1 context.
7. Run a separate session/day analysis over validated lower-timeframe context.
8. Build the H4 two-sided playbooks.
9. Run context-awareness validation against exact evidence IDs.
10. Publish one readiness manifest. Minute decisions remain disabled until the
    manifest is `ready`.

Warm-up does not train or alter LoRA weights. It creates explicit runtime
context. A restart rebuilds hot memory from SQLite, verifies hashes/freshness,
and recomputes only expired layers.

## Context-awareness validation system

“Fully context aware” cannot mean that Qwen states “I understand.” Operational
readiness means every hard data and evidence test passes.

### Gate A: raw-data integrity

- required lookback exists for each timeframe;
- no missing or duplicate completed candle keys;
- OHLC geometry is valid;
- timestamps are UTC and align to timeframe boundaries;
- forming candles are excluded from completed-history claims;
- latest quote/candle ages are within declared limits; and
- source hashes reproduce.

Any failure blocks readiness and produces a typed repair request.

### Gate B: derived-cache integrity

- every level cites existing completed candles;
- deterministic calculations reproduce exactly;
- structural cache source range/hash matches L0;
- playbook prices reference supplied levels;
- buy/sell geometry is valid;
- session facts match deterministic UTC boundaries; and
- all epochs are current and mutually compatible.

### Gate C: Qwen context challenge

After warm-up, Qwen receives a compact challenge and must return:

```text
cache epochs acknowledged
current D1/H4/H1 location
current H4 open and state
current session and Asia-range relation
nearest valid upper and lower zones
active playbook IDs
best conditional buy path
best conditional sell path
one unresolved fact
evidence IDs for every assertion
```

The validator checks IDs, prices, session, and states against the cache. Free
text confidence cannot compensate for a mismatch. Unsupported evidence,
missing sides, invented IDs, or stale epochs fail the gate.

### Gate D: counterfactual retrieval tests

The validator asks bounded questions whose answers are already in the cache:

- identify the source candle for a selected H4 level;
- distinguish the completed H1 candle from the forming H1 candle;
- locate price relative to the Asia high/low;
- state what would invalidate one buy and one sell playbook; and
- request the correct additional evidence when a supplied fact is omitted.

These tests verify retrieval and use, not prediction accuracy.

### Gate E: incremental-cache tests

- applying one new M1 candle changes only the expected live/session fields;
- replaying the same candle is idempotent;
- an M5 close rolls forming data into completed data exactly once;
- an H4 close expires the old playbooks and creates a new epoch;
- restart/rebuild produces identical hashes; and
- the minute path performs no full-history or full-JSONL scan.

### Readiness manifest

```json
{
  "status": "ready|blocked",
  "model_resident": true,
  "raw_data_valid": true,
  "structural_cache_valid": true,
  "level_cache_valid": true,
  "playbooks_valid": true,
  "session_cache_valid": true,
  "minute_delta_valid": true,
  "context_challenge_valid": true,
  "compatible_epochs": [],
  "validated_at_utc": "...",
  "failures": []
}
```

All boolean gates must be true. There is no average score that can hide one
failed hard requirement.

## Compact minute-decision protocol

Target: normally no more than 800 input tokens after the stable decision
contract. The exact budget is measured during replay and may be reduced only
if required evidence remains complete.

Example packet:

```json
{
  "decision_time_utc": "2026-08-03T13:16:00Z",
  "epochs": {
    "structure": "S-1200-v1",
    "session": "NYO-1300-v4",
    "playbook": "PB-1200-v1",
    "minute": "M1-1315-v1"
  },
  "quote": {"bid": 4043.86, "ask": 4043.94, "age_ms": 180},
  "closed_m1": {
    "id": "M1-1315",
    "o": 4044.44, "h": 4045.21, "l": 4043.31, "c": 4043.87,
    "tick_volume": 812
  },
  "forming": {
    "M5": {"o": 4042.14, "h": 4045.85, "l": 4041.37, "now": 4043.87},
    "M15": {"o": 4047.63, "h": 4053.82, "l": 4040.84, "now": 4043.87},
    "H1": {"o": 4047.63, "h": 4053.82, "l": 4040.84, "now": 4043.87},
    "H4": {"o": 4062.49, "h": 4064.80, "l": 4040.84, "now": 4043.87}
  },
  "volume": {"M1_ratio": 1.18, "M5_ratio": 1.42},
  "nearby_levels": [
    {"id": "M15_LOW", "price": 4043.16, "distance": -0.71, "state": "testing"},
    {"id": "M5_LOW", "price": 4040.84, "distance": -3.03, "state": "below"}
  ],
  "playbook": {
    "id": "PB-L03", "status": "testing",
    "buy_missing": "M1 rejection close",
    "sell_missing": "M5 accepted close below zone"
  },
  "position": null
}
```

The packet does not contain prior P&L, win rate, or directional outcome history.
Those remain in the separate research-learning loop.

## Qwen response and additional-data request

Normal response:

```json
{
  "action": "open|wait|skip|request_data",
  "direction": "buy|sell|none",
  "playbook_id": "PB-L03",
  "observed_trigger": "...",
  "invalidation_level_id": "...",
  "target_level_id": "...",
  "confidence": 0,
  "evidence_ids": [],
  "data_requests": []
}
```

Bounded request example:

```json
{
  "action": "request_data",
  "data_requests": [{
    "timeframe": "M1",
    "completed_bars": 20,
    "fields": ["ohlc", "tick_volume"],
    "reason": "compare two tests at active H4 zone"
  }]
}
```

Allowed timeframes, maximum bars, fields, and one additional round per decision
are enforced in code. A request cannot bypass freshness, session, or geometry
validation. The supplied evidence is attached to the same decision ID.

## Model residency

The current `keep_alive=-1` behavior is retained:

1. warm the model once during software startup;
2. verify the expected model digest;
3. keep weights resident indefinitely;
4. monitor Ollama residency and CPU/GPU allocation;
5. block minute decisions if the model was evicted or changed;
6. warm and rerun context validation after Ollama/model restart.

Do not send an empty generation every minute merely to simulate market memory.
Model residency avoids weight reload; the external cache provides market
memory. On an RTX 3090, validation should require the model to be fully GPU
resident before latency benchmarking.

## Latency instrumentation and budgets

Every minute cycle records:

```text
snapshot time
cache update duration
validation duration
prompt assembly duration and token count
Qwen load/prompt/evaluation durations
response validation duration
price at snapshot and response
price drift during inference
first-fill latency
```

Initial engineering targets for the minute path:

- incremental cache update: <= 50 ms;
- deterministic validation: <= 50 ms;
- packet assembly: <= 20 ms;
- no full-history/JSONL scan;
- post-Qwen response validation: <= 100 ms; and
- Qwen inference: benchmarked separately on current hardware and RTX 3090.

Inference is not declared acceptable from a hardware estimate. Replay measures
whether price drift during the complete snapshot-to-fill interval remains
compatible with the scalp entry geometry.

## Failure behavior

The minute decision is blocked when:

- a required cache layer is stale, missing, incompatible, or invalid;
- the latest expected candle or forming candle is missing during the active
  weekday data session. Historical discontinuities, rollover pauses, and
  off-session gaps are recorded but do not block readiness;
- model digest or cache epoch differs from the readiness manifest;
- Qwen cites nonexistent evidence;
- quote age or price drift exceeds the tested scalp tolerance;
- an additional-data request cannot be fulfilled; or
- model residency is lost.

The system reports the exact blocking gate and continues repairing/refreshing
context. It does not replace missing evidence with a generic trade.

## Implementation and promotion state

1. **Design approval:** completed by explicit user instruction.
2. **Cache implementation:** L0-L5 and incremental fixtures implemented;
   ready structure, session, playbook, level, and minute epochs feed entry Qwen.
3. **Validation implementation:** Gates A-E and the readiness manifest are
   implemented and passed against live MT5 demo data and the local Qwen model.
4. **Warm-up shadow:** deterministic refresh is active through the unified
   runtime; uncapped Qwen requalification is manual/off-hours after a model or
   contract change. Unchanged hashes and the qualification certificate are
   reused; failures remain retained in SQLite.
5. **Minute-packet execution input:** implemented with exact epoch
   acknowledgement and bounded evidence validation before a plan can be ready.
6. **Broker truth:** the daily filled-position cap is read from MT5 deals, never
   inferred from local proposal/execution logs.
7. **Paper scope:** integrated execution remains restricted to the verified MT5
   demo account; profitability still requires preregistered research.

---
