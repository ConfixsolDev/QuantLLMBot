"""Direct-cutover acceptance for the V2 three-store runtime."""

from __future__ import annotations

import argparse
import os

from vnext.storage.persistence import from_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("QWEN_TIMESCALE_DSN", ""))
    parser.add_argument("--redis-url", default=os.environ.get("QWEN_REDIS_URL", ""))
    parser.add_argument("--neo4j-uri", default=os.environ.get("QWEN_NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--neo4j-user", default=os.environ.get("QWEN_NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.environ.get("QWEN_NEO4J_PASSWORD", ""))
    args = parser.parse_args()
    persistence = from_environment(dsn=args.dsn, redis_url=args.redis_url,
                                    neo4j_uri=args.neo4j_uri,
                                    neo4j_user=args.neo4j_user,
                                    neo4j_password=args.neo4j_password)
    try:
        persistence.ensure_ready()
        if not persistence.working_memory.client.ping():
            raise RuntimeError("Redis ping failed")
    finally:
        persistence.close()
    print("vnext-storage-acceptance-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
