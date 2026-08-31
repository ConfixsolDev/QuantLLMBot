"""Executable fail-closed gate for a future V2 live restart.

This command only validates infrastructure and broker truth. It never submits,
modifies, or closes an order and it writes no routine files.
"""

from __future__ import annotations

import json
import os

from vnext.execution.mt5 import MT5BrokerClient
from vnext.recovery.preflight import run_preflight
from vnext.storage.persistence import from_environment


def main() -> int:
    dsn = os.environ.get("QWEN_TIMESCALE_DSN", "")
    redis_url = os.environ.get("QWEN_REDIS_URL", "")
    neo4j_uri = os.environ.get("QWEN_NEO4J_URI", "bolt://127.0.0.1:7687")
    neo4j_user = os.environ.get("QWEN_NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("QWEN_NEO4J_PASSWORD", "")
    pair = os.environ.get("QWEN_VNEXT_PAIR", "XAUUSDr")
    raw_positions = os.environ.get("QWEN_VNEXT_LEDGER_POSITIONS", "[]")
    try:
        ledger_positions = json.loads(raw_positions)
    except json.JSONDecodeError as exc:
        raise RuntimeError("QWEN_VNEXT_LEDGER_POSITIONS must be valid JSON") from exc
    if not isinstance(ledger_positions, list) or not all(isinstance(row, dict) for row in ledger_positions):
        raise RuntimeError("QWEN_VNEXT_LEDGER_POSITIONS must be a JSON list of objects")

    import MetaTrader5 as mt5
    persistence = from_environment(dsn=dsn, redis_url=redis_url, neo4j_uri=neo4j_uri,
                                    neo4j_user=neo4j_user, neo4j_password=neo4j_password)
    try:
        if not mt5.initialize():
            raise RuntimeError("MT5 initialize failed")
        broker = MT5BrokerClient(mt5, magic=1)
        result = run_preflight(persistence=persistence, broker=broker,
                               ledger_positions=ledger_positions, redis_rebuilt=True)
        if not result.allowed:
            raise RuntimeError("V2 cutover preflight rejected: " + ",".join(result.plan.reasons))
    finally:
        mt5.shutdown()
        persistence.close()
    print("vnext-cutover-preflight-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
