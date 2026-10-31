"""The trading journal: every Qwen decision and every trade, in TimescaleDB.

Tables (schema of the application, ``structure`` by default):

  decisions   one row per question to Qwen — even "wait" and invalid answers:
              time, strategy (id@version#hash), prompt hash + size, the
              candidates offered, the evidence map (E-id -> engine event id),
              model name + digest, latency, raw answer, verdict (take / wait /
              invalid), chosen candidate, confidence, citations, why, errors
  trades      one row per order: decision, strategy, candidate, side, lots,
              entry / stop / target, money risked, balance and risk % at entry,
              broker position id, exit price, gross / costs / net, R multiple
              (net / money risked), close reason, pnl_complete, mode
  refusals    intents the executor did not send, with the reason

``MemoryJournal`` keeps the same records in lists (replays and tests).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY, time TIMESTAMPTZ NOT NULL, strategy_ref TEXT NOT NULL,
    prompt_sha TEXT NOT NULL, prompt_bytes INTEGER NOT NULL, candidates JSONB NOT NULL,
    evidence_map JSONB NOT NULL, model TEXT, model_digest TEXT, latency_ms INTEGER,
    raw_answer TEXT, action TEXT NOT NULL, label TEXT, candidate_key TEXT, confidence INTEGER,
    cites JSONB, why TEXT, errors JSONB, engine_config_hash TEXT, mode TEXT);
CREATE INDEX IF NOT EXISTS decisions_time ON decisions (time DESC);
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY, decision_id TEXT, strategy_ref TEXT NOT NULL, candidate_key TEXT NOT NULL,
    side TEXT NOT NULL, lots DOUBLE PRECISION NOT NULL, entry DOUBLE PRECISION NOT NULL,
    stop DOUBLE PRECISION NOT NULL, target DOUBLE PRECISION NOT NULL, risk_money DOUBLE PRECISION NOT NULL,
    balance_before DOUBLE PRECISION, risk_pct DOUBLE PRECISION, position_id BIGINT,
    opened_at TIMESTAMPTZ NOT NULL, closed_at TIMESTAMPTZ, exit_price DOUBLE PRECISION,
    gross DOUBLE PRECISION, costs DOUBLE PRECISION, net DOUBLE PRECISION, r_multiple DOUBLE PRECISION,
    close_reason TEXT, close_note TEXT, pnl_complete BOOLEAN, mode TEXT, meta JSONB);
CREATE INDEX IF NOT EXISTS trades_opened ON trades (opened_at DESC);
CREATE TABLE IF NOT EXISTS refusals (
    intent_id TEXT NOT NULL, time TIMESTAMPTZ NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
    intent JSONB NOT NULL, PRIMARY KEY (intent_id, time));
"""


def _ts(t: int | None):
    return datetime.fromtimestamp(t, tz=timezone.utc) if t else None


class MemoryJournal:
    def __init__(self) -> None:
        self.decisions: list[dict] = []
        self.trades: dict[str, dict] = {}
        self.refusals: list[dict] = []

    def decision(self, rec: dict) -> None:
        self.decisions.append(rec)

    def refusal(self, intent, status: str, reason: str, now: int) -> None:
        self.refusals.append({"intent_id": intent.intent_id, "time": now, "status": status, "reason": reason,
                              "intent": intent.as_dict()})

    def trade_opened(self, t: dict) -> None:
        self.trades[t["id"]] = dict(t)

    def trade_closed(self, t: dict) -> None:
        self.trades[t["id"]] = dict(t)

    def net_today(self, now: int) -> float:
        day = now - now % 86400
        return sum(t.get("net") or 0.0 for t in self.trades.values() if (t.get("closed_at") or 0) >= day)


class DbJournal(MemoryJournal):
    """Same interface, written to PostgreSQL / TimescaleDB (psycopg connection, autocommit)."""

    def __init__(self, conn) -> None:
        super().__init__()
        self.conn = conn
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                conn.execute(stmt)

    def decision(self, rec: dict) -> None:
        super().decision(rec)
        self.conn.execute(
            "INSERT INTO decisions (id, time, strategy_ref, prompt_sha, prompt_bytes, candidates, evidence_map, "
            "model, model_digest, latency_ms, raw_answer, action, label, candidate_key, confidence, cites, why, "
            "errors, engine_config_hash, mode) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (rec["id"], _ts(rec["time"]), rec["strategy_ref"], rec["prompt_sha"], rec["prompt_bytes"],
             json.dumps(rec["candidates"]), json.dumps(rec["evidence_map"]), rec.get("model"),
             rec.get("model_digest"), rec.get("latency_ms"), rec.get("raw_answer"), rec["action"],
             rec.get("label"), rec.get("candidate_key"), rec.get("confidence"), json.dumps(rec.get("cites", [])),
             rec.get("why"), json.dumps(rec.get("errors", [])), rec.get("engine_config_hash"), rec.get("mode")))

    def refusal(self, intent, status: str, reason: str, now: int) -> None:
        super().refusal(intent, status, reason, now)
        self.conn.execute("INSERT INTO refusals (intent_id, time, status, reason, intent) VALUES (%s,%s,%s,%s,%s) "
                          "ON CONFLICT DO NOTHING",
                          (intent.intent_id, _ts(now), status, reason, json.dumps(intent.as_dict())))

    def trade_opened(self, t: dict) -> None:
        super().trade_opened(t)
        self.conn.execute(
            "INSERT INTO trades (id, decision_id, strategy_ref, candidate_key, side, lots, entry, stop, target, "
            "risk_money, balance_before, risk_pct, position_id, opened_at, mode, meta) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (t["id"], t.get("decision_id"), t["strategy_ref"], t["candidate_key"], t["side"], t["lots"], t["entry"],
             t["stop"], t["target"], t["risk_money"], t.get("balance_before"), t.get("risk_pct"),
             t.get("position_id"), _ts(t["opened_at"]), t.get("mode"), json.dumps(t.get("meta", {}))))

    def trade_closed(self, t: dict) -> None:
        super().trade_closed(t)
        self.conn.execute(
            "UPDATE trades SET closed_at=%s, exit_price=%s, gross=%s, costs=%s, net=%s, r_multiple=%s, "
            "close_reason=%s, close_note=%s, pnl_complete=%s WHERE id=%s",
            (_ts(t.get("closed_at")), t.get("exit_price"), t.get("gross"), t.get("costs"), t.get("net"),
             t.get("r_multiple"), t.get("close_reason"), t.get("close_note"), t.get("pnl_complete"), t["id"]))

    def net_today(self, now: int) -> float:
        day = _ts(now - now % 86400)
        row = self.conn.execute("SELECT COALESCE(SUM(net), 0) FROM trades WHERE closed_at >= %s", (day,)).fetchone()
        return float(row[0])


def now_utc() -> int:
    return int(time.time())
