---
name: supervise-market-structure-neo4j
description: Analyzes completed XAUUSD candles, audits and labels multi-timeframe market structure, supervises structure-proven zones, and safely backfills the rebuildable Neo4j market graph from newest coverage backward. Use for Neo4j market-structure backfills, BOS/CHoCH/MSS and swing labeling, M1 timing plus M15/M30/H1/H4/D1 zone validation, graph relations, coverage audits, or agent-supervised zone improvement in QuantLLMBot.
---

# Supervise Market Structure in Neo4j

Work in `E:/QuantLLMBot`. This skill improves analysis and traceability; it does not grant the agent trading or execution authority.

Neo4j is the trade manager's market explanation layer. It must turn immutable
market facts into a clear chronological account of what formed, what was
tested, what proved or invalidated a level, and what remains unresolved. It
does not invent truth: deterministic closed-candle evidence establishes facts,
the graph connects and retrieves them, and the trade manager interprets them.

## Authorities and boundaries

1. Read `AGENTS.md` first.
2. Use only `XAUUSD_SYSTEM_ARCHITECTURE_V2.md` for architecture. Improve it in place when an approved graph or runtime change alters architecture; never create a competing architecture document.
3. Read `store/core_skill.md` and `store/sop.md` before interpreting structure, levels, zones, acceptance, rejection, BOS, CHoCH, MSS, FVG, order blocks, or liquidity.
4. If work touches training, curriculum, data preparation, or model-job Python, read and use only `model_training/CURRICULUM_AND_DATA_PREP.md`; inspect and extend `model_training/python_utilities_for_models/` for any new model-job Python.
5. Keep live code under `apps/qwen_trade_software/`. Keep the Colab training pipeline under `scripts/`.
6. Preserve unrelated worktree changes. Inspect `git status --short` and relevant diffs before editing.
7. SQLite and immutable source evidence are authoritative. Neo4j is optional and rebuildable. Neo4j failure must not block collection, Qwen's SQLite baseline, execution, protection, or reconciliation.
8. Python computes deterministic facts. Qwen/agent analysis judges and proposes. The agent never manufactures candles, levels, fib anchors, BOS, or proof.
9. Use completed candles only for structural labels. A forming candle and a wick-only excursion are not structural proof.
10. Never reveal Neo4j credentials or place secrets in source, logs, reports, or commands shown to the user.

## Load the working contract

Read [REFERENCE.md](REFERENCE.md) before analyzing or changing this subsystem. Use its event vocabulary, proof rules, coverage contract, graph model, and verification gates.

Then inspect the current implementation rather than assuming it matches the reference:

- `apps/qwen_trade_software/backend/market_intelligence/`
- `apps/qwen_trade_software/backend/market_graph/`
- `apps/qwen_trade_software/backend/market_history_backfill.py`
- `apps/qwen_trade_software/backend/market_graph_worker.py`
- `apps/qwen_trade_software/backend/market_structure.py`
- `apps/qwen_trade_software/backend/structure_tracker.py`
- `apps/qwen_trade_software/backend/structural_event.py`
- `apps/qwen_trade_software/backend/swing_zones.py`
- `apps/qwen_trade_software/backend/zone_scorer.py`
- nearby tests, graph health/context snapshots, and worker logs

## Workflow

### 1. Establish scope and baseline

1. Record symbol, requested timeframes, requested history boundary, UTC time, source, session-calendar version, graph schema version, and whether the request authorizes graph writes.
2. Default structural target frames are `M15`, `M30`, `H1`, `H4`, and `D1`. Include `M1` when the task concerns execution timing, fast local profit collection, or microstructure supervision.
3. If no date boundary is supplied, audit all locally available coverage first. For a write run, continue backward until the broker/source is exhausted or a verified checkpoint boundary is reached; do not silently choose an arbitrary number of days.
4. Capture pre-run ledger counts, outbox counts, graph counts, earliest/latest event times by symbol/timeframe, dead-letter count, watermark, and projection lag.
5. Separate confirmed repository behavior from proposed improvements.

### 2. Audit coverage newest-to-oldest

1. Work backward in bounded day/page windows, but insert and replay each fetched batch in chronological order.
2. Exclude the forming candle. Do not declare the current partial trading day complete.
3. Build a coverage result per trading day and timeframe: expected window, observed first/last close, row count, duplicate IDs, missing intervals, source exhaustion, and status `complete|partial|closed_session|source_gap|unknown`.
4. Determine completeness from the versioned broker/session calendar and parent-child reconstruction, not a blind weekday candle count. Treat holidays, weekend closure, DST, and broker history limits explicitly.
5. Use the project convention for H4: New York 17:00 trading-day anchor with DST-aware aggregation from completed H1. Verify all constituents before calling an H4 candle complete.
6. Include completed D1 evidence. Never synthesize D1 from an incomplete trading day.
7. Checkpoint only after the SQLite ledger transaction commits. Resume idempotently from stable event IDs.
8. Never delete or replace legacy evidence during an audit. Any migration or cleanup requires an explicit plan, backup/rebuild path, tests, and approval.

### 3. Derive deterministic structure

For each timeframe independently, process oldest to newest:

1. Confirm swing highs/lows only after the configured right-wing candles close.
2. Label confirmed swings `HH`, `HL`, `LH`, or `LL` relative to the prior confirmed swing of the same kind on the same timeframe.
3. Represent levels as zones, normally the swing candle's body-to-wick band, with stable owning timeframe and source candle IDs.
4. Emit BOS only for an owning-timeframe close beyond the relevant protected zone in the established trend direction.
5. Emit CHoCH only for the first owning-timeframe close beyond the protected opposing swing zone against the established trend.
6. Emit MSS only when CHoCH also satisfies the existing instrument-specific displacement rule. Do not hardcode a new threshold inside the skill.
7. Label wick-through/close-back as a sweep or rejection candidate, not BOS.
8. Require subsequent hold/retest evidence before labeling acceptance when doctrine requires hold. Keep `event_time`, `confirmation_time`, and `knowledge_time` distinct.
9. Preserve hierarchy: M15 builds M30, M30 builds H1, H1 builds H4, and H4 builds D1. Coincident closes are one nested evidence episode, not independent votes.

### 4. Supervise zones without circular proof

1. A detector-created zone starts as `candidate`.
2. A zone becomes `structure_proven` only through a separate closed-candle event that cites both the zone ID and its evidence IDs. Zone existence cannot prove itself.
3. Track lifecycle with immutable events: `zone_created`, `zone_tested`, `zone_rejected`, `zone_accepted`, `zone_broken`, `zone_retested`, `zone_invalidated`, and `zone_stale`.
4. Keep zone quality separate from structural proof. Freshness, departure, base quality, test count, participation, higher-timeframe confluence, and room to the next opposing zone may score a proven zone but cannot create proof.
5. D1/H4/H1 primarily locate the auction; M30/M15 describe path and timing. Lower-timeframe evidence may refine a parent zone but cannot overwrite its owning-timeframe invalidation.
6. Agent findings are `proposed` assertions with model/agent version, rule version, evidence IDs, confidence, and rationale hash. Promote to `confirmed` only through deterministic validation or explicit human approval. Disagreement stays queryable.
7. M1 labels only M1-owned structure and entry/management timing. An M1 close may prove or break an M1 zone; it cannot invalidate or accept a higher-timeframe zone, and fast-profit intent does not relax the normal entry, spread, session, target-room, or protection gates.

### 5. Project safely to Neo4j

1. Append normalized events to the SQLite ledger and transactional outbox first. Qwen and the agent never issue arbitrary Cypher or write directly to Neo4j.
2. Use stable business IDs, uniqueness constraints, parameterized Cypher, bounded `UNWIND` batches, and idempotent `MERGE`.
3. Keep graph facts compact. Raw tick history, large OHLC arrays, prompts, responses, broker truth, and numerical ledgers remain outside Neo4j.
4. Preserve instrument isolation, timeframe ownership, evidence provenance, chronological succession, session membership, and shared time-bucket containment.
5. Do not add node labels, relationship types, constraints, indexes, or schema versions silently. Treat graph-schema changes as architecture changes: propose the V2 update, migration/rebuild path, tests, rollback, and request approval.
6. Run the graph worker outside the entry hot path. Retry only safely retryable failures; keep bounded dead letters and observable lag.

### 6. Verify before claiming completion

Run focused tests first, then the nearby market-intelligence/graph suite. Verify:

- no forming-candle labels and no look-ahead swings;
- deterministic replay produces identical IDs, labels, zones, and structure epochs;
- a second backfill inserts zero duplicates and leaves counts stable;
- coverage has no unexplained gaps for days labeled complete;
- BOS/CHoCH/MSS cite the broken zone, break candle, owning timeframe, and rule version;
- zone proof is non-circular and lifecycle order is valid;
- H4 DST boundaries and D1 completeness are correct;
- outbox reaches the expected watermark with zero unexplained dead letters;
- graph counts reconcile to the ledger and symbol/timeframe isolation holds;
- Neo4j outage leaves the authoritative pipeline and execution path healthy;
- bounded retrieval returns only evidence available as of the requested time.

Do not claim improved trading performance from graph completeness. Require shadow replay, an SQLite-only baseline, leakage-safe walk-forward evaluation, and out-of-sample evidence.

### 7. Publish bounded website read models

1. The website reads an atomically written local JSON snapshot; it never runs Cypher and never waits for Neo4j in an HTTP request.
2. Publish only bounded, scalar evidence: graph health/lag, latest structure state per timeframe, recent confirmed structure events, nearby active zones, lifecycle status, evidence IDs, and `as_of`/`knowledge_as_of` timestamps.
3. Keep three visibly distinct layers: `deterministic_evidence`, `agent_proposals`, and `trade_ideas`. A trade idea may cite graph evidence; graph evidence is not itself an entry signal.
4. Every structure card must show owning timeframe, status, detector/rule version, freshness, provenance, and `execution_authority=false` for shadow output.
5. Sort zones by relevance to current price, then cap rows and payload size. Show stale/unavailable state rather than falling back to unbounded retrieval.
6. Do not expose credentials, raw prompts, full candle arrays, or arbitrary graph traversal to the browser.

### 8. Compile and supervise Qwen market memory

1. Query raw graph facts only inside the worker, then discard the raw result. Publish the bounded packet through `market_graph/context_compiler.py`; never pass a graph dump to Qwen.
2. Preserve packet order: market clock/sessions, seven-timeframe XAUUSD temporal structure, three consolidated zone positions, structure/participation, five-line DXY cross-reference, then conflicts/missing facts/RAG availability.
3. Treat price zone as the memory anchor. Consolidate overlapping levels, retain the highest owning timeframe, keep per-timeframe invalidation, and count one nested movement as one episode.
4. Label tick volume as a participation proxy. Do not claim true buy/sell volume.
5. Use only the predefined neutral RAG request and response contracts in `market_graph/rag_protocol.py`. Retrieve supporting and contradicting evidence symmetrically; return `insufficient_evidence` when facts are missing. Qwen never receives Cypher.
6. Apply semantic-memory probation through `market_graph/semantic_memory.py`: seven calendar days, unique-episode counts, automatic retirement when contradictions equal/exceed support during probation, then human lock after survival. Session is not a match key.
7. Keep the complete packet `shadow_only` and out of Qwen prompts until V2 promotion gates pass. Qwen may receive compact shadow health; website observability may display the packet.
8. Measure packet bytes, freshness, missing facts, contradiction coverage, outbox lag, deterministic replay, and comparison with the SQLite-only baseline before proposing promotion.

## Change policy

- Apply narrow, reversible fixes that preserve the protected architecture when the user asked for implementation and focused tests prove them.
- Request approval before changing strategy rules, risk, prompts/doctrine, training labels, graph schema/indexes/topology, dependencies, services, credentials, model selection, or deployment.
- If current code and doctrine disagree, stop behavioral promotion, document exact evidence in the task response, and propose the smallest authority-consistent correction.

## Run report

Return a concise task update; do not create a separate architecture, training, or audit markdown file. Include scope, coverage boundary, completed/partial days by timeframe, label and zone counts, graph reconciliation, anomalies, agent proposals versus confirmed facts, files changed, tests run, unresolved risks, and the exact next safe action.
