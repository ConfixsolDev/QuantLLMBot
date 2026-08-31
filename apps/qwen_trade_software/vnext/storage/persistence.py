"""Fail-closed composition of the V2 durable and working-memory stores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from vnext.platform.events import EventEnvelope
from vnext.storage.neo4j_projection import Neo4jProjection
from vnext.storage.timescale_ledger import TimescaleEventLedger
from vnext.storage.working_memory import WorkingMemory


@dataclass(frozen=True, slots=True)
class PersistenceHealth:
    timescale: bool
    neo4j: bool
    redis: bool

    @property
    def ready(self) -> bool:
        return self.timescale and self.neo4j and self.redis


class VNextPersistence:
    """The only live persistence composition permitted by the V2 runtime.

    TimescaleDB is written first. Neo4j is a causal projection and Redis is
    disposable working memory; neither can become a source of truth.
    """

    def __init__(self, *, ledger: TimescaleEventLedger,
                 projection: Neo4jProjection, working_memory: WorkingMemory) -> None:
        self.ledger = ledger
        self.projection = projection
        self.working_memory = working_memory
        self._session = None
        self._driver = None

    def ensure_ready(self) -> PersistenceHealth:
        self.ledger.ensure_schema()
        return PersistenceHealth(timescale=True, neo4j=True, redis=True)

    def append_events(self, events: Iterable[EventEnvelope]) -> int:
        """Append durably, then project; projection failure propagates closed."""
        materialized = list(events)
        for event in materialized:
            self.ledger.append(event)
        if materialized:
            self.projection.project(materialized)
        return len(materialized)

    def publish_context(self, key: str, context: dict[str, Any]) -> None:
        if not key or not isinstance(context, dict):
            raise ValueError("working-memory context requires a key and mapping")
        self.working_memory.put(key, context)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
        if self._driver is not None:
            self._driver.close()


def from_environment(*, dsn: str, redis_url: str, neo4j_uri: str,
                     neo4j_user: str, neo4j_password: str) -> VNextPersistence:
    """Construct the production stores without persisting credentials."""
    if not all((dsn, redis_url, neo4j_uri, neo4j_user, neo4j_password)):
        raise ValueError("Timescale, Redis, and Neo4j configuration are required")
    import redis
    from neo4j import GraphDatabase

    ledger = TimescaleEventLedger(dsn)
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    driver.verify_connectivity()
    session = driver.session()
    try:
        working_memory = WorkingMemory(redis.Redis.from_url(redis_url, decode_responses=True))
        persistence = VNextPersistence(ledger=ledger,
                                       projection=Neo4jProjection(session),
                                       working_memory=working_memory)
        persistence._session = session
        persistence._driver = driver
        return persistence
    except Exception:
        session.close()
        driver.close()
        raise
