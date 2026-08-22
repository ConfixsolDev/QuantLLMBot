"""SQLite event ledger and materialized structure projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()[:20]


class IntelligenceStore:
    """Append-only evidence with replaceable views that can be replayed."""

    def __init__(self, path: Path | str, busy_timeout_ms: int = 5000) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(f"PRAGMA busy_timeout={max(0, int(busy_timeout_ms))}")
        self.lock = threading.RLock()
        self._schema()

    def _schema(self) -> None:
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS intelligence_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time_utc TEXT NOT NULL,
                    evidence_id TEXT,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS intelligence_event_lookup
                    ON intelligence_events(symbol,timeframe,sequence);
                CREATE INDEX IF NOT EXISTS intelligence_event_time_lookup
                    ON intelligence_events(symbol,timeframe,event_time_utc,sequence);
                CREATE TABLE IF NOT EXISTS structure_projections (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    structure_epoch TEXT NOT NULL,
                    last_event_id TEXT,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(symbol,timeframe)
                );
                CREATE TABLE IF NOT EXISTS retrieval_audit (
                    request_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    requested_at_utc TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_projection_outbox (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    enqueued_at_utc TEXT NOT NULL,
                    projected_at_utc TEXT,
                    FOREIGN KEY(event_id) REFERENCES intelligence_events(event_id)
                );
                CREATE INDEX IF NOT EXISTS graph_outbox_pending
                    ON graph_projection_outbox(status,sequence);
                CREATE TABLE IF NOT EXISTS trade_journal (
                    proposal_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    result TEXT NOT NULL,
                    idea_summary TEXT,
                    idea_reason TEXT,
                    model TEXT,
                    confidence REAL,
                    structure_timeframe TEXT,
                    entry_time_utc TEXT,
                    exit_time_utc TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    volume REAL,
                    initial_stop REAL,
                    initial_target REAL,
                    geometry_source TEXT,
                    gross_pnl REAL,
                    costs REAL,
                    net_pnl REAL,
                    peak_pnl REAL,
                    maximum_drawdown REAL,
                    mfe_price REAL,
                    mae_price REAL,
                    giveback_price REAL,
                    secured_cash REAL NOT NULL DEFAULT 0,
                    secured_stop REAL,
                    secured_at_utc TEXT,
                    exit_reason TEXT,
                    attribution_source TEXT,
                    holding_seconds REAL,
                    loss_reasons_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    qwen_analysis_json TEXT,
                    qwen_analysis_status TEXT NOT NULL DEFAULT 'pending',
                    qwen_analyzed_at_utc TEXT,
                    qwen_analysis_model TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS trade_journal_exit_time
                    ON trade_journal(exit_time_utc);
                CREATE INDEX IF NOT EXISTS trade_journal_result
                    ON trade_journal(result,exit_time_utc);
            """)
            existing = {
                row["name"] for row in self.db.execute("PRAGMA table_info(trade_journal)")
            }
            migrations = {
                "qwen_analysis_json": "TEXT",
                "qwen_analysis_status": "TEXT NOT NULL DEFAULT 'pending'",
                "qwen_analyzed_at_utc": "TEXT",
                "qwen_analysis_model": "TEXT",
            }
            for column, declaration in migrations.items():
                if column not in existing:
                    self.db.execute(
                        f"ALTER TABLE trade_journal ADD COLUMN {column} {declaration}"
                    )

    def upsert_trade_journal(self, journal: dict) -> None:
        """Materialize one closed trade; replaying the same close is safe."""
        columns = (
            "proposal_id", "execution_id", "symbol", "side", "result",
            "idea_summary", "idea_reason", "model", "confidence",
            "structure_timeframe", "entry_time_utc", "exit_time_utc",
            "entry_price", "exit_price", "volume", "initial_stop",
            "initial_target", "geometry_source", "gross_pnl", "costs",
            "net_pnl", "peak_pnl", "maximum_drawdown", "mfe_price",
            "mae_price", "giveback_price", "secured_cash", "secured_stop",
            "secured_at_utc", "exit_reason", "attribution_source",
            "holding_seconds", "loss_reasons_json", "evidence_ids_json",
            "plan_json", "outcome_json", "source_hash", "created_at_utc",
            "updated_at_utc",
        )
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(
            f"{column}=excluded.{column}" for column in columns
            if column not in {"proposal_id", "created_at_utc"}
        )
        with self.lock, self.db:
            self.db.execute(
                f"INSERT INTO trade_journal ({','.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT(proposal_id) DO UPDATE SET {updates}",
                tuple(journal.get(column) for column in columns),
            )

    def trade_journals(self, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM trade_journal ORDER BY exit_time_utc DESC LIMIT ?",
            (max(1, min(int(limit), 10000)),),
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            for field in ("loss_reasons_json", "evidence_ids_json", "plan_json", "outcome_json"):
                item[field.removesuffix("_json")] = json.loads(item.pop(field))
            raw_analysis = item.pop("qwen_analysis_json", None)
            item["qwen_analysis"] = json.loads(raw_analysis) if raw_analysis else None
            output.append(item)
        return output

    def pending_trade_journals(self, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM trade_journal WHERE qwen_analysis_status IN ('pending','retry') "
            "ORDER BY exit_time_utc LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_trade_qwen_analysis(
        self, proposal_id: str, analysis: dict | None, status: str, model: str
    ) -> None:
        with self.lock, self.db:
            self.db.execute(
                "UPDATE trade_journal SET qwen_analysis_json=?,qwen_analysis_status=?,"
                "qwen_analyzed_at_utc=?,qwen_analysis_model=?,updated_at_utc=? "
                "WHERE proposal_id=?",
                (
                    canonical(analysis) if analysis is not None else None,
                    status,
                    datetime.now(timezone.utc).isoformat(),
                    model,
                    datetime.now(timezone.utc).isoformat(),
                    proposal_id,
                ),
            )

    def append_event(self, event: dict) -> bool:
        payload = event.get("payload") or {}
        with self.lock, self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO intelligence_events "
                "(event_id,symbol,timeframe,event_type,event_time_utc,evidence_id,"
                "payload_json,payload_hash,recorded_at_utc) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    event["event_id"], event["symbol"], event["timeframe"],
                    event["event_type"], event["event_time_utc"], event.get("evidence_id"),
                    canonical(payload), digest(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            inserted = cursor.rowcount == 1
            if inserted:
                self.db.execute(
                    "INSERT OR IGNORE INTO graph_projection_outbox "
                    "(event_id,status,attempts,enqueued_at_utc) VALUES (?,'pending',0,?)",
                    (event["event_id"], datetime.now(timezone.utc).isoformat()),
                )
            return inserted

    def append_events(self, events: list[dict]) -> int:
        """Append a large historical batch in one transaction."""
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        with self.lock, self.db:
            for event in events:
                payload = event.get("payload") or {}
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO intelligence_events "
                    "(event_id,symbol,timeframe,event_type,event_time_utc,evidence_id,"
                    "payload_json,payload_hash,recorded_at_utc) VALUES (?,?,?,?,?,?,?,?,?)",
                    (event["event_id"], event["symbol"], event["timeframe"],
                     event["event_type"], event["event_time_utc"], event.get("evidence_id"),
                     canonical(payload), digest(payload), now),
                )
                if cursor.rowcount != 1:
                    continue
                self.db.execute(
                    "INSERT OR IGNORE INTO graph_projection_outbox "
                    "(event_id,status,attempts,enqueued_at_utc) VALUES (?,'pending',0,?)",
                    (event["event_id"], now),
                )
                inserted += 1
        return inserted

    def enqueue_unprojected_graph_events(self) -> int:
        """Backfill the graph outbox from the immutable ledger, idempotently."""
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self.db:
            before = self.db.total_changes
            self.db.execute(
                "INSERT OR IGNORE INTO graph_projection_outbox "
                "(event_id,status,attempts,enqueued_at_utc) "
                "SELECT event_id,'pending',0,? FROM intelligence_events",
                (now,),
            )
            return self.db.total_changes - before

    def graph_outbox_batch(self, limit: int = 200, max_attempts: int = 8) -> list[dict]:
        """Return pending graph events in ledger order with their prior event ID."""
        priority = self.db.execute(
            """SELECT e.timeframe,
                      CASE
                        WHEN json_extract(e.payload_json,'$.mode')='posthoc_supervised' THEN 3
                        WHEN json_extract(e.payload_json,'$.rule_version')='market-structure-shadow-v3-deduped' THEN 2
                        WHEN json_extract(e.payload_json,'$.mode')='shadow_only' THEN 1
                        ELSE 0 END AS projection_priority
               FROM graph_projection_outbox o
               JOIN intelligence_events e ON e.event_id=o.event_id
               WHERE o.status='pending' AND o.attempts < ?
               GROUP BY e.timeframe,projection_priority
               ORDER BY projection_priority DESC,CASE e.timeframe
                          WHEN 'H4' THEN 0 WHEN 'D1' THEN 1 WHEN 'H1' THEN 2
                          WHEN 'M30' THEN 3 WHEN 'M15' THEN 4 WHEN 'M1' THEN 5
                          ELSE 6 END LIMIT 1""",
            (max(1, int(max_attempts)),),
        ).fetchone()
        if not priority:
            return []
        rows = self.db.execute(
            """
            SELECT o.sequence AS outbox_sequence,o.attempts,e.*
            FROM graph_projection_outbox o
            JOIN intelligence_events e ON e.event_id=o.event_id
            WHERE o.status='pending' AND o.attempts < ? AND e.timeframe=?
              AND (CASE
                     WHEN json_extract(e.payload_json,'$.mode')='posthoc_supervised' THEN 3
                     WHEN json_extract(e.payload_json,'$.rule_version')='market-structure-shadow-v3-deduped' THEN 2
                     WHEN json_extract(e.payload_json,'$.mode')='shadow_only' THEN 1
                     ELSE 0 END)=?
            ORDER BY e.symbol,e.event_time_utc,e.sequence LIMIT ?
            """,
            (max(1, int(max_attempts)), priority["timeframe"],
             priority["projection_priority"],
             max(1, min(int(limit), 10000))),
        ).fetchall()
        result = []
        previous_by_symbol: dict[str, str | None] = {}
        for row in rows:
            symbol = str(row["symbol"])
            if symbol not in previous_by_symbol:
                prior = self.db.execute(
                    """SELECT p.event_id FROM intelligence_events p
                       JOIN graph_projection_outbox po ON po.event_id=p.event_id
                       WHERE po.status='projected' AND p.symbol=? AND p.timeframe=?
                         AND (p.event_time_utc < ? OR
                              (p.event_time_utc=? AND p.sequence < ?))
                         AND (CASE
                           WHEN json_extract(p.payload_json,'$.mode')='posthoc_supervised' THEN 3
                           WHEN json_extract(p.payload_json,'$.rule_version')='market-structure-shadow-v3-deduped' THEN 2
                           WHEN json_extract(p.payload_json,'$.mode')='shadow_only' THEN 1
                           ELSE 0 END)=?
                       ORDER BY p.event_time_utc DESC,p.sequence DESC LIMIT 1""",
                    (symbol, priority["timeframe"], row["event_time_utc"],
                     row["event_time_utc"], row["sequence"],
                     priority["projection_priority"]),
                ).fetchone()
                previous_by_symbol[symbol] = prior["event_id"] if prior else None
            previous = previous_by_symbol[symbol]
            result.append({
                "outbox_sequence": row["outbox_sequence"],
                "sequence": row["sequence"],
                "event_id": row["event_id"],
                "symbol": symbol,
                "timeframe": row["timeframe"],
                "event_type": row["event_type"],
                "event_time_utc": row["event_time_utc"],
                "evidence_id": row["evidence_id"],
                "payload": json.loads(row["payload_json"]),
                "payload_hash": row["payload_hash"],
                "recorded_at_utc": row["recorded_at_utc"],
                # Selected rows are already ordered by symbol/time/sequence.
                # Linking inside the homogeneous projection stream avoids an
                # O(batch * ledger) correlated lookup during deep backfills.
                "previous_event_id": previous,
                "attempts": row["attempts"],
            })
            previous_by_symbol[symbol] = row["event_id"]
        return result

    def mark_graph_projected(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self.db:
            self.db.executemany(
                "UPDATE graph_projection_outbox SET status='projected',projected_at_utc=?,"
                "last_error=NULL WHERE event_id=?",
                [(now, event_id) for event_id in event_ids],
            )

    def mark_graph_failed(self, event_ids: list[str], error: str, max_attempts: int = 8) -> None:
        if not event_ids:
            return
        message = str(error)[:1000]
        with self.lock, self.db:
            self.db.executemany(
                "UPDATE graph_projection_outbox SET attempts=attempts+1,last_error=?,"
                "status=CASE WHEN attempts+1>=? THEN 'dead' ELSE 'pending' END "
                "WHERE event_id=?",
                [(message, max(1, int(max_attempts)), event_id) for event_id in event_ids],
            )

    def graph_outbox_stats(self) -> dict:
        rows = self.db.execute(
            "SELECT status,COUNT(*) AS count FROM graph_projection_outbox GROUP BY status"
        ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
        watermark = self.db.execute(
            "SELECT MAX(projected_at_utc) AS value FROM graph_projection_outbox "
            "WHERE status='projected'"
        ).fetchone()
        return {
            "pending": int(counts.get("pending", 0)),
            "projected": int(counts.get("projected", 0)),
            "dead": int(counts.get("dead", 0)),
            "last_projected_at_utc": watermark["value"] if watermark else None,
        }

    def events(self, symbol: str, timeframe: str | None = None, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        sql = "SELECT * FROM intelligence_events WHERE symbol=?"
        params: list[object] = [symbol]
        if timeframe:
            sql += " AND timeframe=?"
            params.append(timeframe)
        sql += " ORDER BY sequence DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute(sql, params).fetchall()
        return [
            {
                "event_id": row["event_id"], "symbol": row["symbol"],
                "timeframe": row["timeframe"], "event_type": row["event_type"],
                "event_time_utc": row["event_time_utc"],
                "evidence_id": row["evidence_id"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in reversed(rows)
        ]

    def put_projection(self, symbol: str, timeframe: str, state: dict, last_event_id: str | None) -> dict:
        epoch = f"structure-{symbol}-{timeframe}-{digest(state)}"
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO structure_projections VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(symbol,timeframe) DO UPDATE SET state_json=excluded.state_json,"
                "structure_epoch=excluded.structure_epoch,last_event_id=excluded.last_event_id,"
                "updated_at_utc=excluded.updated_at_utc",
                (symbol, timeframe, canonical(state), epoch, last_event_id, now),
            )
        return {**state, "structure_epoch": epoch, "updated_at_utc": now}

    def projection(self, symbol: str, timeframe: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM structure_projections WHERE symbol=? AND timeframe=?",
            (symbol, timeframe),
        ).fetchone()
        if not row:
            return None
        return {
            **json.loads(row["state_json"]),
            "structure_epoch": row["structure_epoch"],
            "last_event_id": row["last_event_id"],
            "updated_at_utc": row["updated_at_utc"],
        }

    def projections(self, symbol: str) -> dict[str, dict]:
        rows = self.db.execute(
            "SELECT timeframe FROM structure_projections WHERE symbol=?", (symbol,)
        ).fetchall()
        return {row["timeframe"]: self.projection(symbol, row["timeframe"]) for row in rows}

    def last_event_id(self, symbol: str, timeframe: str) -> str | None:
        row = self.db.execute(
            "SELECT last_event_id FROM structure_projections WHERE symbol=? AND timeframe=?",
            (symbol, timeframe),
        ).fetchone()
        return str(row["last_event_id"]) if row and row["last_event_id"] else None

    def record_retrieval(self, request_id: str, symbol: str, request: dict, result: dict, status: str) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO retrieval_audit VALUES (?,?,?,?,?,?)",
                (request_id, symbol, datetime.now(timezone.utc).isoformat(),
                 canonical(request), canonical(result), status),
            )

    def recent_retrievals(self, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM retrieval_audit ORDER BY requested_at_utc DESC LIMIT ?",
            (max(1, min(limit, 50)),),
        ).fetchall()
        return [{"request_id": r["request_id"], "symbol": r["symbol"],
                 "requested_at_utc": r["requested_at_utc"], "status": r["status"],
                 "request": json.loads(r["request_json"]),
                 "result": json.loads(r["result_json"])} for r in rows]

    def rebuild(self, reducer) -> int:
        with self.lock, self.db:
            self.db.execute("DELETE FROM structure_projections")
            # Backfill can discover an older candle after a newer one was
            # already recorded. Replay must follow market time, not arrival time.
            rows = self.db.execute(
                "SELECT * FROM intelligence_events ORDER BY event_time_utc,sequence"
            ).fetchall()
            states: dict[tuple[str, str], dict] = {}
            last_ids: dict[tuple[str, str], str] = {}
            for row in rows:
                event = {"event_id": row["event_id"], "symbol": row["symbol"],
                         "timeframe": row["timeframe"], "event_type": row["event_type"],
                         "event_time_utc": row["event_time_utc"],
                         "evidence_id": row["evidence_id"],
                         "payload": json.loads(row["payload_json"])}
                key = (row["symbol"], row["timeframe"])
                states[key] = reducer(states.get(key), event)
                last_ids[key] = row["event_id"]
            # A materialized projection stores only current state. Persisting it
            # after every historical event made large backfills needlessly slow.
            for key, state in states.items():
                self.put_projection(*key, state, last_ids[key])
            return len(rows)
