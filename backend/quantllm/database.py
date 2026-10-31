"""PostgreSQL / TimescaleDB storage for M1 history and structure events.

Schema (default ``structure``; created on first start, nothing else touched)
--------------------------------------------------------------------------
m1_candles     symbol, time (bar OPEN, UTC), open, high, low, close, tick_volume
               primary key (symbol, time). A TimescaleDB hypertable when the
               extension is installed; a plain table otherwise.
events         every structure event of the current engine run: id, symbol,
               kind, tf, time, available_at, config_hash, data (jsonb).
               Rebuilt on every start from the replayed history, so it always
               matches the running engine and config.
service_state  small key/value facts (last start, config hash, ...).

Only CLOSED M1 bars are ever written. Higher timeframes are not stored: the
engine rebuilds them from M1 exactly the same way every time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, Iterator

from structure_engine.bars import Bar


def _ts(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


class Database:
    def __init__(self, dsn: str, schema: str) -> None:
        if not dsn:
            raise RuntimeError("No database connection: set QUANTLLM_DB_DSN (or QWEN_TIMESCALE_DSN)")
        import psycopg                                  # pip install "psycopg[binary]"
        self.psycopg = psycopg
        self._dsn = dsn
        self.schema = schema
        self.conn = psycopg.connect(dsn, autocommit=True, connect_timeout=10)
        self.timescale = False
        self._create()

    def _create(self) -> None:
        c = self.conn
        c.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
        c.execute(f'SET search_path TO "{self.schema}", public')
        try:
            c.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            self.timescale = True
        except Exception:
            self.timescale = False                      # plain PostgreSQL is fine too
        c.execute("""CREATE TABLE IF NOT EXISTS m1_candles (
            symbol TEXT NOT NULL, time TIMESTAMPTZ NOT NULL,
            open DOUBLE PRECISION NOT NULL, high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL, close DOUBLE PRECISION NOT NULL,
            tick_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (symbol, time))""")
        if self.timescale:
            try:
                c.execute("SELECT create_hypertable('m1_candles', 'time', if_not_exists => TRUE, migrate_data => TRUE)")
            except Exception:
                pass
        c.execute("""CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, symbol TEXT NOT NULL, kind TEXT NOT NULL, tf TEXT NOT NULL,
            time TIMESTAMPTZ NOT NULL, available_at TIMESTAMPTZ NOT NULL,
            config_hash TEXT NOT NULL, data JSONB NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS events_symbol_available ON events (symbol, available_at)")
        c.execute("CREATE INDEX IF NOT EXISTS events_symbol_kind ON events (symbol, kind)")
        c.execute("""CREATE TABLE IF NOT EXISTS service_state (
            key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")

    # ------------------------------------------------------------------ candles
    def insert_candles(self, symbol: str, bars: Iterable[Bar]) -> int:
        """Insert closed M1 bars; existing ones are kept (idempotent). Returns rows added."""
        rows = [(symbol, _ts(b.time), b.open, b.high, b.low, b.close, b.volume) for b in bars]
        if not rows:
            return 0
        with self.conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE IF NOT EXISTS _m1_in (LIKE m1_candles INCLUDING DEFAULTS) ON COMMIT PRESERVE ROWS")
            cur.execute("TRUNCATE _m1_in")
            with cur.copy("COPY _m1_in (symbol, time, open, high, low, close, tick_volume) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
            cur.execute("INSERT INTO m1_candles SELECT * FROM _m1_in ON CONFLICT (symbol, time) DO NOTHING")
            return cur.rowcount

    def last_candle_time(self, symbol: str) -> int | None:
        row = self.conn.execute("SELECT max(time) FROM m1_candles WHERE symbol = %s", (symbol,)).fetchone()
        return int(row[0].timestamp()) if row and row[0] else None

    def candle_count(self, symbol: str) -> int:
        return self.conn.execute("SELECT count(*) FROM m1_candles WHERE symbol = %s", (symbol,)).fetchone()[0]

    def iter_candles(self, symbol: str, start: int | None = None, batch: int = 20000) -> Iterator[Bar]:
        """Closed M1 bars in time order (streamed; safe for years of data)."""
        sql = "SELECT time, open, high, low, close, tick_volume FROM m1_candles WHERE symbol = %s"
        args: list = [symbol]
        if start is not None:
            sql += " AND time >= %s"
            args.append(_ts(start))
        sql += " ORDER BY time"
        with self._stream_cursor() as cur:
            cur.execute(sql, args)
            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break
                for t, o, h, l, c, v in rows:
                    yield Bar(int(t.timestamp()), o, h, l, c, v)

    def _stream_cursor(self):
        # A server-side (named) cursor streams rows without loading years of
        # bars into memory; it needs a transaction, so use its own connection.
        conn = self.psycopg.connect(self._dsn, autocommit=False)
        conn.execute(f'SET search_path TO "{self.schema}", public')
        cur = conn.cursor(name="m1_stream")

        class _Ctx:
            def __enter__(self_inner):
                return cur

            def __exit__(self_inner, *exc):
                cur.close()
                conn.rollback()
                conn.close()
        return _Ctx()

    # ------------------------------------------------------------------ events
    def clear_events(self, symbol: str) -> None:
        self.conn.execute("DELETE FROM events WHERE symbol = %s", (symbol,))

    def insert_events(self, symbol: str, events) -> None:
        rows = [(e.id, symbol, e.kind, e.tf, _ts(e.time), _ts(e.available_at), e.config_hash,
                 json.dumps(e.data)) for e in events]
        if not rows:
            return
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO events (id, symbol, kind, tf, time, available_at, config_hash, data) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (id) DO NOTHING", rows)

    def event_count(self, symbol: str) -> int:
        return self.conn.execute("SELECT count(*) FROM events WHERE symbol = %s", (symbol,)).fetchone()[0]

    # ------------------------------------------------------------------ state
    def set_state(self, key: str, value) -> None:
        self.conn.execute("INSERT INTO service_state (key, value, updated_at) VALUES (%s, %s::jsonb, now()) "
                          "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                          (key, json.dumps(value)))

    def get_state(self, key: str):
        row = self.conn.execute("SELECT value FROM service_state WHERE key = %s", (key,)).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.conn.close()
