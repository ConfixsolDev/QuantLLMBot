"""Print the latest durable vNext debug-service events."""

from __future__ import annotations

import argparse
import json
import os


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.limit <= 0 or args.limit > 100:
        raise ValueError("limit must be between 1 and 100")
    import psycopg
    dsn = os.environ.get("QWEN_TIMESCALE_DSN", "")
    if not dsn:
        raise ValueError("QWEN_TIMESCALE_DSN is required")
    with psycopg.connect(dsn, connect_timeout=3) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT event_type,observed_at_utc,payload_json FROM vnext_event_ledger "
            "WHERE event_type LIKE %s ORDER BY observed_at_utc DESC LIMIT %s",
            ("VNEXT_DEBUG_%", args.limit),
        )
        rows = cursor.fetchall()
    for event_type, observed, payload in rows:
        print(json.dumps({"event_type": event_type, "observed_at_utc": observed.isoformat(),
                          "payload": payload}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
