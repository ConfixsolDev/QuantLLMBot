# Neo4j requirements, configuration, and operations

This is the single operational reference for the QuantLLMBot Neo4j deployment.
The system design authority remains `../../XAUUSD_SYSTEM_ARCHITECTURE_V2.md`.

## Installed local deployment

- Neo4j Community: `2026.07.1`
- Neo4j home: `C:\Neo4j\neo4j-community-2026.07.1`
- Java: Azul Zulu JDK 21 at `C:\Program Files\Zulu\zulu-21`
- Bolt: `bolt://127.0.0.1:7687`
- Browser: `http://127.0.0.1:7474`
- Database/user: `neo4j` / `neo4j`
- Windows service: `neo4j`, automatic startup
- Runtime ownership: Windows service only; do not run `neo4j console` alongside it
- Python driver: `neo4j>=5.28,<7` in `backend/requirements.txt`

Both connectors listen only on loopback. Authentication is enabled. The password
is generated locally and stored in the current Windows user's environment; it is
not recorded in this repository or this document.

## Application configuration

The following user environment variables have been configured:

```text
QWEN_NEO4J_ENABLED=1
QWEN_NEO4J_URI=bolt://127.0.0.1:7687
QWEN_NEO4J_USER=neo4j
QWEN_NEO4J_PASSWORD=<local secret>
QWEN_NEO4J_DATABASE=neo4j
QWEN_GRAPH_SYMBOLS=XAUUSDr,DXY
```

Restart QuantLLMBot after changing these variables because an already-running
process does not inherit later environment changes.

To add instruments later, use the exact broker symbols, separated by commas:

```powershell
[Environment]::SetEnvironmentVariable(
  "QWEN_GRAPH_SYMBOLS", "XAUUSDr,DXY,EURUSD,GBPUSD,USDJPY", "User"
)
```

Python ingestion must still produce normalized market events for every added
symbol. Listing a symbol does not create its market-data feed.

## Runtime ownership and failure isolation

SQLite is the numerical source of truth. Neo4j is an optional, rebuildable graph
projection. Qwen remains the decision layer, and execution never depends
directly on a live graph query.

`backend/market_graph_worker.py` reads the transactional SQLite outbox, writes
idempotently to Neo4j, and publishes bounded local snapshots:

- `backend/cache/market-graph-health.json`
- `backend/cache/market-graph-context.json`

`backend/software_runtime.py` starts this worker when `QWEN_NEO4J_ENABLED=1`.
If Neo4j is unavailable, events remain queued for retry and trading continues
through the SQLite memory path.

## Graph contents

The projection uses `MarketEvent`, `Instrument`, `Timeframe`, `TimeBucket`,
`SessionPhase`, `MarketEpisode`, and `EvidenceRef` nodes. It connects chronology,
timeframe containment, session membership, episodes, decisions, executions, and
evidence without duplicating raw tick history. The worker creates its constraints
and indexes idempotently at startup.

Current deterministic levels are indexed as `MarketLevel` nodes and linked to
distinct `LevelObservation` snapshots. Their recurrence count therefore measures
separate cache epochs rather than worker polling cycles. `StructureSnapshot`
stores the latest location, auction state, evidence-quality confidence, and
evidence references for each timeframe. These appear under `market_levels` and
`market_structure` in `cache/market-graph-context.json` for fast Qwen retrieval.

Schema v2 enforces bitemporal retrieval using market `event_time` plus system
`recorded_at`. Historical level values are read from immutable observations,
not mutable current-level properties. H4 temporal buckets are explicitly tagged
`new_york_1700_dst`; UTC-aligned legacy H4 buckets must not coexist. A schema-v2
temporal rebuild requeues candle projections without deleting candle/event nodes.

## Historical candle policy and backfill

Run the idempotent maximum-history import from `backend`:

```powershell
C:\ProgramData\Miniconda3\python.exe market_history_backfill.py
```

The importer requests the maximum completed MT5 history currently exposed by
the terminal (up to 99,999 bars per request), retains tick volume, real volume,
and spread, and stores full native M1/M15/M30/H1/D1 candles for XAUUSD and DXY. H4 is replaced with a
DST-aware aggregation of H1 anchored to the Forex trading day at 17:00
`America/New_York`. The command is idempotent; the graph worker drains its
transactional outbox independently.

MT5's `Max bars in chart` setting controls obtainable M1 depth. Increasing it
requires an MT5 restart and should only be done outside live trading. Rerun the
command afterward to discover any additional broker history.

## Health and verification

Check the Windows service and ports:

```powershell
Get-Service neo4j
Get-NetTCPConnection -LocalPort 7687,7474 -State Listen
```

Run one projection/health cycle from `backend`:

```powershell
C:\ProgramData\Miniconda3\python.exe market_graph_worker.py --once
Get-Content cache\market-graph-health.json
```

A healthy result reports `status: ready`, with `pending: 0` and `dead: 0` after
the backlog is consumed. Neo4j Browser is at `http://127.0.0.1:7474`.

Run a database check without displaying the password:

```powershell
$jdk = "C:\Program Files\Zulu\zulu-21"
$env:JAVA_HOME = $jdk
$env:Path = "$jdk\bin;$env:Path"
$password = [Environment]::GetEnvironmentVariable("QWEN_NEO4J_PASSWORD", "User")
& "C:\Neo4j\neo4j-community-2026.07.1\bin\cypher-shell.bat" `
  -a bolt://127.0.0.1:7687 -u neo4j -p $password `
  "SHOW CONSTRAINTS; MATCH (e:MarketEvent) RETURN count(e);"
```

Logs are under `C:\Neo4j\neo4j-community-2026.07.1\logs` and
`backend/logs/market-graph-worker.log`.

## Start, stop, and recovery

The Windows service is the sole allowed Neo4j runtime owner. It is configured
for automatic startup and three failure restarts (after 5, 10, and 30 seconds).
From elevated PowerShell:

```powershell
Start-Service neo4j
Stop-Service neo4j
Restart-Service neo4j
```

If service control is unavailable, obtain administrator elevation and repair or
start the service. Do not use `neo4j console` as a fallback: a console process
competes for the same database lock and ports, prevents service recovery, and
creates ambiguous ownership. Verify `Get-Service neo4j`, ports 7474/7687, and
the authenticated graph count after every restart.

## Password rotation

Never put the password in source files, Markdown, command history, or Git. Rotate
it with Cypher while connected as `neo4j`, then update the user variable and
restart QuantLLMBot:

```cypher
ALTER CURRENT USER SET PASSWORD FROM 'old-secret' TO 'new-secret';
```

```powershell
[Environment]::SetEnvironmentVariable("QWEN_NEO4J_PASSWORD", "new-secret", "User")
```

## Backup, rebuild, and upgrade

Neo4j Community supports offline dump/load. Stop Neo4j before an offline dump
and store backups outside `NEO4J_HOME`. The graph can also be rebuilt from the
authoritative SQLite event ledger. Do not delete either store during live
trading.

Before upgrading: back up the database, review migration notes, stop/uninstall
the existing service, install the new distribution, update `NEO4J_HOME`, update
or reinstall the service, and repeat the health checks.

Official references:

- https://neo4j.com/docs/operations-manual/current/installation/windows/
- https://neo4j.com/docs/operations-manual/current/installation/requirements/
- https://neo4j.com/docs/operations-manual/current/backup-restore/
