<!-- version: 2.7 | owner: human | delivery: always -->
<!-- changelog: 2.7 added regime-reading (range/trend/breakout/exhaustion).
     2.6 added three-step trade finding (context → hunt → arm).
     2.0 stable section IDs added (sections_applied targets these);
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

## [regime-reading] Range, trend, breakout, exhaustion

Python may supply regime_hint as range, trend, breakout, or exhaustion. Treat
it as a location hint, not a command. Closed candles at mapped zones outrank
the hint when they disagree.

- Range: overlapping bodies, two-sided wicks, repeated tests of the same
  support and resistance. Fade the outer third; skip the middle. First target
  is the opposing M5 boundary (scalp). Do not run a basket across the box.
- Trend: higher highs and higher lows, or the inverse. Enter on a pullback to
  a mapped zone with a closed failure, not at the impulse extreme. Keep the
  higher-timeframe target (starter basket).
- Breakout: a closed candle of the level's own timeframe accepts beyond a
  defined range edge and a retest holds. Chase only after that accept; a wick
  through the edge is not a breakout.
- Exhaustion: fast ATR expansion at a mapped extreme with no pullback. Wait.
  Do not sell the spike or buy the dump.

A CHoCH, BOS, FVG, or liquidity sweep is a supplied confirmation label on
closed M1/M5. Interpret it at the active zone; do not invent one, and do not
treat an unfilled FVG as an entry by itself.

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

Do not require candle-direction alignment across every timeframe. A lower
timeframe moving against the owning timeframe is often the pullback that brings
price into the planned zone. Read the relationship: the owning timeframe sets
the thesis, intermediate candles describe continuation versus pullback, and M1
times where that pullback fails. Lower-timeframe disagreement becomes a veto
only after accepted failure of the named invalidation on its owning timeframe.

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

Use supplied `candle_clock` facts instead of inferring bar age. A setup or
position inside an M15/M30/H1/H4 closing transition deserves a fresh boundary
check because the close can change the bar's meaning and the next bar can
start a new auction leg. Time alone is never a reversal signal. If a position
was opened near the prior bar's close, judge the first closed M1 after rollover
against the entry thesis: continuation supports hold; a closed counter-response
with no structural progress supports protect or close under the normal rules.
Read the hierarchy explicitly: M15 closes build M30, M30 closes build H1, and
H1 closes build H4. When two or more supplied frames close together, reassess
the completed child first and then its newly completed parent; do not count
their aligned direction as independent evidence because they share price data.

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

## [entry-process] Context → hunt → arm

Trade finding is three steps (not context→open):
1. Context/plan — direction (always-in / HTF auction), named hunt band (pullback
   or outer-third), invalidation.
2. Hunt — while price is outside the hunt band, wait with
   missing_fact=at_entry_location. Do not sell the structure low or buy the
   high because side is correct. Optional challenger may only force wait/revise.
3. Arm — price inside the band, then closed M1 failure timing; M5 response is
   optional strength evidence, then
   invalidation still valid → ready. Otherwise keep waiting.

## [entry-buy] Buy entry

Location is not directly under respected resistance. Selling pressure reaches
support or the M1 EMA cluster and fails: no sustained lower closes. A bullish
M1 candle reclaims the EMA 3/14/31 cluster with upward acceptance. Enter at
the next M1 open with invalidation below the rejection extreme. Hunt the
pullback support band first when context is buy but price is at the high.

## [entry-sell] Sell entry

Exact inverse: buying fails at resistance, a bearish M1 candle reclaims down
through the cluster, enter at the next M1 open, invalidation above the
rejection extreme. Hunt the pullback resistance band first when context is
sell but price is at the low.

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

## [persistent-memory] Structure, DXY, and evidence retrieval

Treat completed candles as an immutable event stream. Maintain one replayable
state per symbol/timeframe: direction, active leg, confirmed transition, named
invalidation, unresolved condition, evidence ID, and epoch. M15 builds M30,
M30 builds H1, and H1 builds H4. A child pullback does not erase its parent;
only the owning timeframe can confirm that transition.

DXY supplies USD-pressure context for gold. Classify it as aligned, leading,
conflicting, decoupled, or unknown and use it to calibrate confidence and
patience. It never replaces XAUUSD structure, mapped location, or its closed M1
execution response. If a decisive fact is absent, request a small completed-
candle or structure-event slice from the read-only store, then decide or wait.
