# Market-Structure Graph Reference

This reference is subordinate to `XAUUSD_SYSTEM_ARCHITECTURE_V2.md`, `store/core_skill.md`, and `store/sop.md`. If they differ, follow the repository authorities and report the mismatch.

## 1. Evidence and knowledge-time contract

Every derived record needs:

- `event_id`: stable, deterministic, instrument-neutral business ID
- `symbol` and `timeframe`
- `event_type`
- `event_time_utc`: when the market event occurred
- `confirmation_time_utc`: close time of the last candle needed to confirm it
- `knowledge_time_utc`: when the pipeline could first know it without look-ahead
- `evidence_id` and bounded `used_evidence_ids`
- `detector`, `detector_version`, `rule_version`, and `schema_version`
- `payload_hash` and source provenance
- `status`: `proposed|confirmed|rejected|superseded`

For a fractal swing, the swing candle time is not its knowledge time. Knowledge begins only after the configured right wing closes. Backtests and retrieval must filter on `knowledge_time_utc <= as_of`.

## 2. Canonical structure vocabulary

| Event | Minimum closed-candle evidence | Meaning |
|---|---|---|
| `swing_high_confirmed` | Swing high plus required closed right wing | Candidate resistance zone |
| `swing_low_confirmed` | Swing low plus required closed right wing | Candidate support zone |
| `HH` / `LH` | Compare with prior confirmed high on same timeframe | High-sequence label |
| `HL` / `LL` | Compare with prior confirmed low on same timeframe | Low-sequence label |
| `bos_confirmed` | Owning-timeframe close beyond protected zone with trend | Continuation evidence |
| `choch_confirmed` | First owning-timeframe close beyond opposing protected zone | Potential transition |
| `mss_confirmed` | CHoCH plus configured displacement | Stronger transition evidence |
| `liquidity_sweep` | Wick beyond zone and close back without accepted break | Rejection/liquidity evidence |
| `zone_accepted` | Closed break plus doctrine-required hold/retest | Auction acceptance |
| `zone_rejected` | Probe and closed return through/inside the zone | Auction rejection |

Use the existing repository detector vocabulary when writing code. If normalized graph names differ, store the source name and normalization rule. BOS confirms continuation; it is not a standalone entry trigger. CHoCH/MSS at a mapped zone are stronger reversal evidence but still do not replace location and the runtime entry gate.

## 3. Zone contract

A structure zone should carry:

- stable `zone_id` derived from symbol, owning timeframe, zone kind, source candle/evidence, and rule version;
- `zone_low`, `zone_high`, and optional body/wick edges;
- `kind`: support, resistance, supply, demand, prior high/low, swing high/low, FVG, order block, pivot, or fib location;
- owning timeframe and source evidence IDs;
- formation, confirmation, first-test, last-test, invalidation, and expiry times when known;
- lifecycle status and version;
- independent proof-event IDs;
- test count, freshness, departure, base quality, participation, parent confluence, opposing-zone room, and score version;
- provenance for deterministic, agent-proposed, external-shadow, or human-confirmed assertions.

Never collapse a zone to exact-price equality. Never let a child-timeframe wick invalidate a parent zone. Never upgrade score merely because an agent described the setup persuasively.

### Proof relation

Use this logical pattern:

```text
source candles -> swing/level event -> candidate zone
later closed candle(s) -> BOS/CHoCH/MSS/acceptance/rejection event
proof event -> PROVES or INVALIDATES -> candidate zone
agent analysis -> PROPOSES -> assertion -> CITES -> evidence
deterministic validator or human -> CONFIRMS/REJECTS -> assertion
```

The current V2 graph can represent these as compact `MarketEvent` nodes plus evidence and episode links. Dedicated `StructureZone`, `StructureAssertion`, or semantic proof relationships are a schema extension and require approval plus an in-place V2 revision before implementation.

## 4. Timeframe ownership

- `D1`, `H4`, `H1`: parent auction and location map.
- `M30`, `M15`: path, transition, and execution context.
- `M1`: local timing, failure tests, fast-move progress, and protection evidence only.
- Parent chain: `M15 -> M30 -> H1 -> H4 -> D1`.
- Runtime containment remains `M1 -> M5 -> M15`; an M1 label never inherits M5/M15 authority merely because those candles share data.
- A child may refine a zone or reveal the pullback path; it does not vote away the parent thesis.
- A break is judged by the zone's owning timeframe.
- Store shared deterministic time buckets for containment. Do not create every possible candle-to-parent-candle edge.

## 5. Coverage and backfill contract

### Direction of work

Fetch newest-to-oldest so recent coverage becomes useful first. Within every fetched page, normalize and append oldest-to-newest so chronology and reducer replay remain deterministic.

### Day completeness

For each symbol, timeframe, and calendar version, record:

```text
trading_day_id
window_start_utc / window_end_utc
expected_intervals / observed_intervals
first_close_utc / last_close_utc
duplicate_count / missing_intervals
source_exhausted
status = complete|partial|closed_session|source_gap|unknown
```

Do not infer completeness from `96/48/24/6/1` alone. Those are useful sanity expectations for a fully open 24-hour day, not proof in the presence of weekends, holidays, DST, broker maintenance, late starts, or source limits.

### Stop conditions

A maximum-history run stops only when one of these is recorded:

1. the broker/source returns no older completed data and confirms exhaustion;
2. the user-specified earliest boundary is fully reconciled;
3. a reproducible source gap blocks progress; report it without calling the day complete;
4. the user stops the run.

Checkpoint the oldest reconciled boundary separately for each symbol/timeframe. Never use one timeframe's boundary as proof that another is complete.

## 6. Neo4j projection model

### Existing V2-compatible core

Nodes:

- `MarketEvent`
- `Instrument`
- `Timeframe`
- `TimeBucket`
- `SessionPhase`
- `MarketEpisode`
- `EvidenceRef`

Relationships:

- `FOR_INSTRUMENT`
- `ON_TIMEFRAME`
- `OCCURRED_IN`
- `PART_OF`
- `OCCURRED_DURING`
- `NEXT_EVENT`
- `EVIDENCED_BY`
- `USED_EVIDENCE`
- `PART_OF_EPISODE`

Structure and zone lifecycle can first be added as normalized `MarketEvent.event_type` values with compact scalar facts. This keeps the graph rebuildable from the SQLite ledger and avoids premature schema expansion.

### Candidate extension, approval required

If repeated queries prove event-only traversal insufficient, propose:

- `StructureZone {id, symbol, timeframe, kind, low, high, rule_version}`
- `StructureAssertion {id, status, source_kind, confidence, rationale_hash}`
- `CREATED_ZONE`, `TESTED_ZONE`, `PROVES`, `INVALIDATES`, `REFINES`, `PROPOSES`, `CITES`, `CONFIRMS`, `REJECTS`

Write the target queries first. Demonstrate why the existing event model cannot answer them within the latency and packet-size budget. Then update V2 in place, bump schema version, add constraints, create a rebuild migration, and test rollback.

### Stable IDs

Prefer content-addressed or natural composite IDs. Examples:

```text
candle:{symbol}:{timeframe}:{convention}:{open_time}
zone:{symbol}:{timeframe}:{kind}:{source_evidence_id}:{rule_version}
structure:{symbol}:{timeframe}:{event_type}:{broken_zone_id}:{confirmation_time}:{rule_version}
assertion:{analysis_run_id}:{claim_hash}
```

Never use a Neo4j internal node ID as an external identifier.

## 7. Required graph questions

The model should be justified by queries that answer:

1. Which active D1/H4/H1 zones surround price as of time T?
2. Which M30/M15 structure events tested, proved, refined, or invalidated each zone?
3. What exact completed candles support a BOS, CHoCH, MSS, acceptance, or rejection label?
4. Was the evidence knowable as of decision time?
5. How did the zone lifecycle change chronologically?
6. Where did agent analysis disagree with deterministic labels or human review?
7. Which proven zones remained fresh, produced rejection/acceptance, and had room to the next opposing zone?
8. Can the packet be reproduced from immutable evidence without Neo4j?

Bound all production retrieval by symbol, timeframe set, `as_of`, event count, and payload size. Qwen receives a local snapshot, not arbitrary Cypher access.

### Website read-model contract

Publish one local snapshot with this logical shape:

```text
status=shadow_ready / mode=shadow_only / execution_authority=false
packet_version / packet_bytes / packet_budget_bytes / within_packet_budget
as_of_utc / known_as_of_utc / age_seconds
projection: pending / projected / dead / lag
market_clock_and_sessions
xauusd_all_timeframe_temporal_structure[D1,H4,H1,M30,M15,M5,M1]
active_zone_positions:
  current_or_approaching_focus
  nearest_proven_support
  nearest_proven_resistance
structure_and_volume_participation
dxy_cross_reference.lines[5]
conflicts_missing_and_rag.optional_neo4j_rag_evidence
zone_relevant_semantic_memory[0..1]
```

All arrays are bounded. Zones include stable IDs, consolidated price bands,
owning/contributing timeframes, proof status, evidence IDs, and neutral history.
Shadow records always carry `execution_authority=false`. The browser labels
them as evidence and never infers an order, side, stop, or target from the
graph alone.

### RAG request vocabulary

Only these question IDs are valid: `ZONE_HISTORY`,
`RESOLVE_TIMEFRAME_CONFLICT`, `ACCEPTANCE_REJECTION_PROOF`,
`SIMILAR_MARKET_EPISODES`, `DXY_CROSS_REFERENCE`, and
`SESSION_STRUCTURE_HISTORY`. Responses must contain factual answer, supporting
evidence, contradicting evidence, unresolved facts, evidence IDs/timestamps,
freshness, truncation, and `execution_authority=false`; never recommendations
or confidence adjustment.

## 8. Neo4j implementation research

The design choices above follow current official Neo4j guidance:

- Start from intended queries and model domain entities plus specific, directional relationships: https://neo4j.com/docs/getting-started/data-modeling/tutorial-data-modeling/
- Write queries first and model time/range access deliberately: https://neo4j.com/docs/getting-started/data-modeling/modeling-tips/
- Use uniqueness constraints with `MERGE`; `MERGE` alone does not guarantee node uniqueness under concurrent writes: https://neo4j.com/docs/cypher-manual/current/clauses/merge/
- Use built-in temporal values for UTC event properties: https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/
- Choose indexes from real predicates and measure them; composite property order affects planning and excess indexes slow writes: https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/using-indexes/
- Use parameterized managed transactions for multi-query atomic work; transaction callbacks may retry and therefore must be idempotent: https://neo4j.com/docs/python-manual/current/transactions/

## 9. Verification fixtures

At minimum cover:

- bullish and bearish HH/HL/LH/LL sequences;
- equal highs/lows and tolerance behavior;
- wick sweep versus close-confirmed break;
- BOS in trend, CHoCH against trend, and MSS with/without displacement;
- right-edge swing confirmation and no-look-ahead replay;
- overlapping/nested M15-M30-H1-H4-D1 closes;
- New York H4 anchors across both DST transitions;
- holiday, weekend, partial-day, and broker-gap coverage;
- duplicate pages, process restart, retry, dead letter, and full replay;
- same timestamps across symbols without cross-instrument edges;
- evidence revised by rule-version change without rewriting history;
- Neo4j unavailable while SQLite collection and trading remain functional.

## 10. Promotion criteria

Promote agent-supervised zone information toward Qwen context only after:

1. deterministic reproducibility and zero look-ahead leakage;
2. graph/ledger reconciliation and idempotent rebuild;
3. explicit provenance and queryable disagreements;
4. bounded context size and acceptable lag;
5. shadow replay against the SQLite-only baseline;
6. walk-forward and out-of-sample improvement without degraded safety;
7. approved V2/code/doctrine changes where applicable.
