"""Thin Neo4j adapter; all Cypher is owned here, never by Qwen."""

from __future__ import annotations

from datetime import datetime, timezone

SCHEMA_QUERIES = (
    "CREATE CONSTRAINT market_event_id IF NOT EXISTS FOR (n:MarketEvent) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT instrument_symbol IF NOT EXISTS FOR (n:Instrument) REQUIRE n.symbol IS UNIQUE",
    "CREATE CONSTRAINT timeframe_name IF NOT EXISTS FOR (n:Timeframe) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT time_bucket_id IF NOT EXISTS FOR (n:TimeBucket) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT session_phase_id IF NOT EXISTS FOR (n:SessionPhase) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT market_episode_id IF NOT EXISTS FOR (n:MarketEpisode) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT evidence_ref_id IF NOT EXISTS FOR (n:EvidenceRef) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT market_level_key IF NOT EXISTS FOR (n:MarketLevel) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT level_observation_id IF NOT EXISTS FOR (n:LevelObservation) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT structure_snapshot_id IF NOT EXISTS FOR (n:StructureSnapshot) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT intraday_story_id IF NOT EXISTS FOR (n:IntradayStory) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT intraday_swing_id IF NOT EXISTS FOR (n:IntradaySwing) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT intraday_level_read_id IF NOT EXISTS FOR (n:IntradayLevelRead) REQUIRE n.id IS UNIQUE",
    "CREATE INDEX market_event_lookup IF NOT EXISTS FOR (n:MarketEvent) ON (n.symbol,n.timeframe,n.event_time)",
    "CREATE INDEX market_event_evidence IF NOT EXISTS FOR (n:MarketEvent) ON (n.evidence_id)",
)

UPSERT_EVENTS = """
UNWIND $rows AS row
MERGE (instrument:Instrument {symbol: row.symbol})
MERGE (timeframe:Timeframe {name: row.timeframe})
MERGE (event:MarketEvent {id: row.event_id})
SET event.symbol=row.symbol,event.timeframe=row.timeframe,event.event_type=row.event_type,
    event.event_time=datetime(row.event_time),event.recorded_at=datetime(row.recorded_at),
    event.evidence_id=row.evidence_id,event.payload_hash=row.payload_hash,
    event.schema_version=row.schema_version,event += row.facts
MERGE (event)-[:FOR_INSTRUMENT]->(instrument)
MERGE (event)-[:ON_TIMEFRAME]->(timeframe)
MERGE (session:SessionPhase {id: row.session.id})
SET session.name=row.session.name,session.phase=row.session.phase,
    session.calendar_version=row.session.calendar_version,
    session.starts_at=datetime(row.session.starts_at),session.ends_at=datetime(row.session.ends_at)
MERGE (event)-[:OCCURRED_DURING]->(session)
FOREACH (_ IN CASE WHEN row.episode_id IS NULL THEN [] ELSE [1] END |
    MERGE (episode:MarketEpisode {id: row.episode_id})
    ON CREATE SET episode.opened_at=datetime(row.event_time),episode.symbol=row.symbol,
                  episode.schema_version=row.schema_version
    SET episode.opened_at=CASE WHEN datetime(row.event_time)<episode.opened_at
                               THEN datetime(row.event_time) ELSE episode.opened_at END,
        episode.last_event_at=CASE WHEN episode.last_event_at IS NULL OR
                                        datetime(row.event_time)>episode.last_event_at
                                   THEN datetime(row.event_time) ELSE episode.last_event_at END
    SET episode.status=coalesce(row.episode_status,episode.status),
        episode.closed_at=CASE WHEN row.episode_status='closed'
                               THEN datetime(row.event_time) ELSE episode.closed_at END
    MERGE (event)-[:PART_OF_EPISODE]->(episode)
)
FOREACH (_ IN CASE WHEN row.evidence_id IS NULL THEN [] ELSE [1] END |
    MERGE (ownEvidence:EvidenceRef {id: row.evidence_id})
    MERGE (event)-[:EVIDENCED_BY]->(ownEvidence)
)
FOREACH (evidenceId IN row.used_evidence_ids |
    MERGE (usedEvidence:EvidenceRef {id: evidenceId})
    MERGE (event)-[:USED_EVIDENCE]->(usedEvidence)
)
FOREACH (bucket IN row.buckets |
    MERGE (b:TimeBucket {id: bucket.id})
    SET b.symbol=bucket.symbol,b.timeframe=bucket.timeframe,
        b.starts_at=datetime(bucket.starts_at),b.ends_at=datetime(bucket.ends_at),
        b.time_convention=bucket.time_convention
    MERGE (event)-[:OCCURRED_IN]->(b)
)
"""

UPSERT_BUCKET_EDGES = """
UNWIND $edges AS edge
MATCH (child:TimeBucket {id: edge.child_id})
MATCH (parent:TimeBucket {id: edge.parent_id})
MERGE (child)-[:PART_OF]->(parent)
"""

UPSERT_NEXT_EDGES = """
UNWIND $edges AS edge
MATCH (previous:MarketEvent {id: edge.previous_id})
MATCH (current:MarketEvent {id: edge.current_id})
MERGE (previous)-[:NEXT_EVENT]->(current)
"""

UPSERT_INTRADAY_STORIES = """
UNWIND $stories AS row
MATCH (event:MarketEvent {id:row.event_id})
MERGE (story:IntradayStory {id:row.id})
SET story.symbol=row.symbol,story.as_of_utc=datetime(row.as_of_utc),
    story.recorded_at_utc=datetime(row.recorded_at_utc),story.state=row.state,
    story.market_story=row.market_story,story.sequence_explanation=row.sequence_explanation,
    story.drivers_so_far=row.drivers_so_far,
    story.contradicting_evidence=row.contradicting_evidence,
    story.prior_view_status=row.prior_view_status,story.prior_view_reason=row.prior_view_reason,
    story.next_focus=row.next_focus,story.model=row.model,story.mode=row.mode,
    story.execution_authority=row.execution_authority,
    story.eligible_for_live_context=row.eligible_for_live_context,
    story.contract_version=row.contract_version,story.fingerprint=row.fingerprint,
    story.trigger=row.trigger,story.day_open=row.day_open,story.day_high=row.day_high,
    story.day_low=row.day_low,story.day_close=row.day_close,
    story.day_net_move=row.day_net_move,story.day_range=row.day_range,
    story.structure_method=row.structure_method,
    story.deterministic_structure_state=row.deterministic_structure_state
MERGE (story)-[:DERIVED_FROM_EVENT]->(event)
MERGE (instrument:Instrument {symbol:row.symbol})
MERGE (story)-[:FOR_INSTRUMENT]->(instrument)
FOREACH (_ IN CASE WHEN row.episode_id IS NULL THEN [] ELSE [1] END |
  MERGE (episode:MarketEpisode {id:row.episode_id})
  MERGE (story)-[:DESCRIBES_EPISODE]->(episode))
FOREACH (evidenceId IN row.evidence_ids |
  MERGE (evidence:EvidenceRef {id:evidenceId})
  MERGE (story)-[:SUPPORTED_BY]->(evidence))
FOREACH (swing IN row.swings |
  MERGE (node:IntradaySwing {id:swing.id})
  SET node.ordinal=swing.ordinal,node.label=swing.label,node.kind=swing.kind,
      node.price=swing.price,node.time_utc=swing.time_utc,node.evidence_id=swing.evidence_id
  MERGE (story)-[:HAS_CONFIRMED_SWING {ordinal:swing.ordinal}]->(node)
  FOREACH (_ IN CASE WHEN swing.evidence_id IS NULL THEN [] ELSE [1] END |
    MERGE (evidence:EvidenceRef {id:swing.evidence_id})
    MERGE (node)-[:EVIDENCED_BY]->(evidence)))
FOREACH (levelRead IN row.level_reads |
  MERGE (levelReadNode:IntradayLevelRead {id:levelRead.id})
  SET levelReadNode.level_id=levelRead.level_id,
      levelReadNode.timeframe=levelRead.timeframe,
      levelReadNode.role=levelRead.role,levelReadNode.price=levelRead.price,
      levelReadNode.zone_low=levelRead.zone_low,levelReadNode.zone_high=levelRead.zone_high,
      levelReadNode.touch_episodes_today=levelRead.touch_episodes_today,
      levelReadNode.last_touch_utc=levelRead.last_touch_utc,
      levelReadNode.latest_closed_response=levelRead.latest_closed_response,
      levelReadNode.current_relation=levelRead.current_relation,
      levelReadNode.qwen_quality=levelRead.qwen_quality,
      levelReadNode.qwen_price_story=levelRead.qwen_price_story,
      levelReadNode.next_verification=levelRead.next_verification
  MERGE (story)-[:HAS_LEVEL_READ]->(levelReadNode))
"""

LINK_INTRADAY_LEVELS = """
UNWIND $stories AS row
UNWIND row.level_reads AS levelRead
MATCH (levelReadNode:IntradayLevelRead {id:levelRead.id})
OPTIONAL MATCH (level:MarketLevel {symbol:row.symbol,level_id:levelRead.level_id})
FOREACH (_ IN CASE WHEN level IS NULL THEN [] ELSE [1] END |
  MERGE (levelReadNode)-[:REFERS_TO_LEVEL]->(level))
"""

DELETE_EVENT_BUCKET_EDGES = """
UNWIND $event_ids AS eventId
MATCH (event:MarketEvent {id:eventId})-[relationship:OCCURRED_IN]->(:TimeBucket)
DELETE relationship
"""

CONTEXT_QUERY = """
UNWIND $symbols AS requested_symbol
CALL (requested_symbol) {
    UNWIND $timeframes AS requested_timeframe
    CALL (requested_symbol, requested_timeframe) {
        MATCH (event:MarketEvent {symbol: requested_symbol, timeframe: requested_timeframe})
        WHERE event.event_time <= datetime($as_of)
          AND event.recorded_at <= datetime($known_as_of)
        OPTIONAL MATCH (event)-[:OCCURRED_DURING]->(session:SessionPhase)
        WITH event,session ORDER BY event.event_time DESC
        LIMIT $per_timeframe
        RETURN collect({id:event.id,symbol:event.symbol,timeframe:event.timeframe,
                            event_type:event.event_type,event_time:toString(event.event_time),
                            evidence_id:event.evidence_id,payload_hash:event.payload_hash,
                            direction:event.direction,state:event.state,transition:event.transition,
                            open:event.open,high:event.high,low:event.low,close:event.close,
                            tick_volume:event.tick_volume,real_volume:event.real_volume,
                            session: CASE WHEN session IS NULL THEN null ELSE
                              {id:session.id,name:session.name,phase:session.phase,
                               calendar_version:session.calendar_version,
                               starts_at:toString(session.starts_at),ends_at:toString(session.ends_at)} END})[0..$per_timeframe] AS events
    }
    RETURN collect({timeframe: requested_timeframe, events: events}) AS timeframe_groups
}
RETURN requested_symbol AS symbol,timeframe_groups
"""

SESSION_CONTEXT_QUERY = """
UNWIND $symbols AS requested_symbol
CALL (requested_symbol) {
  MATCH (event:MarketEvent {symbol:requested_symbol,timeframe:'M1',event_type:'candle_closed'})
        -[:OCCURRED_DURING]->(session:SessionPhase)
  WHERE event.event_time <= datetime($as_of) AND event.recorded_at <= datetime($known_as_of)
  WITH session,event ORDER BY event.event_time
  WITH session,collect(event) AS events
  ORDER BY session.starts_at DESC
  LIMIT $session_limit
  WITH session,events,head(events) AS first,last(events) AS final,
       reduce(v=0.0,e IN events | v + coalesce(e.tick_volume,0.0)) AS total_volume,
       reduce(v=0.0,e IN events | v + CASE WHEN e.close>e.open THEN coalesce(e.tick_volume,0.0) ELSE 0.0 END) AS bullish_volume,
       reduce(v=0.0,e IN events | v + CASE WHEN e.close<e.open THEN coalesce(e.tick_volume,0.0) ELSE 0.0 END) AS bearish_volume
  WITH session,events,first,final,total_volume,bullish_volume,bearish_volume,
       reduce(h=null,e IN events | CASE WHEN h IS NULL OR e.high>h THEN e.high ELSE h END) AS high,
       reduce(l=null,e IN events | CASE WHEN l IS NULL OR e.low<l THEN e.low ELSE l END) AS low
  RETURN collect({id:session.id,name:session.name,phase:session.phase,
                  starts_at:toString(session.starts_at),ends_at:toString(session.ends_at),
                  status:CASE WHEN session.ends_at<=datetime($as_of) THEN 'completed' ELSE 'current' END,
                  open:first.open,close:final.close,high:high,low:low,range:high-low,
                  direction:CASE WHEN final.close>first.open THEN 'bullish' WHEN final.close<first.open THEN 'bearish' ELSE 'balanced' END,
                  total_tick_volume:total_volume,bullish_tick_volume:bullish_volume,
                  bearish_tick_volume:bearish_volume,
                  tolerance:(high-low)*0.08,event_count:size(events)}) AS sessions
}
RETURN requested_symbol AS symbol,sessions
"""

STRUCTURE_CONTEXT_QUERY = """
UNWIND $symbols AS requested_symbol
CALL (requested_symbol) {
    UNWIND $timeframes AS requested_timeframe
    CALL (requested_symbol, requested_timeframe) {
        MATCH (event:MarketEvent {symbol: requested_symbol, timeframe: requested_timeframe})
        WHERE event.event_type IN $event_types
          AND event.rule_version = $structure_rule_version
          AND event.event_time <= datetime($as_of)
          AND event.recorded_at <= datetime($known_as_of)
          AND datetime(coalesce(event.knowledge_time_utc, toString(event.event_time))) <= datetime($known_as_of)
        WITH event ORDER BY event.event_time DESC
        LIMIT $structure_limit
        RETURN collect(event{.id,.timeframe,.event_type,.evidence_id,.direction,
          .status,.mode,.execution_authority,.detector,.rule_version,.explanation,
          .structure_label,.prior_structure,.zone_id,.zone_kind,.zone_low,
          .zone_high,.zone_status,.source_time_utc,.source_evidence_id,
          event_time_utc:toString(event.event_time),
          confirmation_time_utc:event.confirmation_time_utc,
          knowledge_time_utc:event.knowledge_time_utc}) AS events
    }
    RETURN collect({timeframe: requested_timeframe, events: events}) AS timeframe_groups
}
RETURN requested_symbol AS symbol,timeframe_groups
"""

STRUCTURE_EVENT_TYPES = (
    "swing_high_confirmed", "swing_low_confirmed", "zone_created", "zone_tested",
    "liquidity_sweep", "bos_confirmed", "choch_confirmed", "mss_confirmed",
    "zone_broken", "zone_accepted", "zone_retested",
)

UPSERT_LEVELS = """
UNWIND $rows AS row
MERGE (level:MarketLevel {key:row.key})
ON CREATE SET level.first_seen=datetime(row.last_seen),level.recurrence_count=0
SET level.symbol=row.symbol,level.timeframe=row.timeframe,level.level_id=row.level_id,
    level.role=row.role,level.label=row.label,level.pattern=row.pattern,
    level.zone_low=row.zone_low,level.zone_high=row.zone_high,level.method=row.method,
    level.test_count=row.test_count,level.left_after_first=row.left_after_first,
    level.valid_from=datetime(row.valid_from),level.last_seen=datetime(row.last_seen),
    level.evidence_confidence=row.confidence
MERGE (observation:LevelObservation {id:row.snapshot_epoch + ':' + row.key})
ON CREATE SET observation.created=true,observation.observed_at=datetime(row.last_seen),
              observation.snapshot_epoch=row.snapshot_epoch
WITH level,observation,row,coalesce(observation.created,false) AS created
SET observation.symbol=row.symbol,observation.timeframe=row.timeframe,
    observation.level_id=row.level_id,observation.role=row.role,
    observation.label=row.label,observation.pattern=row.pattern,
    observation.zone_low=row.zone_low,observation.zone_high=row.zone_high,
    observation.method=row.method,observation.test_count=row.test_count,
    observation.evidence_confidence=row.confidence,
    observation.valid_from=datetime(row.valid_from)
SET level.recurrence_count=level.recurrence_count + CASE WHEN created THEN 1 ELSE 0 END
REMOVE observation.created
MERGE (observation)-[:OBSERVED_LEVEL]->(level)
FOREACH (evidenceId IN row.evidence_ids |
  MERGE (evidence:EvidenceRef {id:evidenceId}) MERGE (level)-[:EVIDENCED_BY]->(evidence))
"""

UPSERT_STRUCTURES = """
UNWIND $rows AS row
MERGE (state:StructureSnapshot {id:row.id})
SET state.symbol=row.symbol,state.timeframe=row.timeframe,
    state.snapshot_epoch=row.snapshot_epoch,state.observed_at=datetime(row.observed_at),
    state.location=row.location,state.auction_state=row.auction_state,
    state.evidence_confidence=row.confidence
FOREACH (evidenceId IN row.evidence_ids |
  MERGE (evidence:EvidenceRef {id:evidenceId}) MERGE (state)-[:EVIDENCED_BY]->(evidence))
"""

MARKET_MAP_QUERY = """
UNWIND $symbols AS symbol
CALL (symbol) {
  MATCH (observation:LevelObservation {symbol:symbol})-[:OBSERVED_LEVEL]->(level:MarketLevel)
  WHERE observation.observed_at <= datetime($as_of)
    AND observation.valid_from <= datetime($as_of)
  WITH level.key AS key,observation,level ORDER BY observation.observed_at DESC
  WITH key,head(collect({observation:observation,level:level})) AS latest
  WITH latest.observation AS observation,latest.level AS level
  ORDER BY observation.timeframe,observation.zone_low
  RETURN collect({key:level.key,timeframe:observation.timeframe,
                  level_id:observation.level_id,role:observation.role,
                  label:observation.label,pattern:observation.pattern,
                  zone_low:observation.zone_low,zone_high:observation.zone_high,
                  method:observation.method,test_count:observation.test_count,
                  recurrence_count:level.recurrence_count,
                  evidence_confidence:observation.evidence_confidence,
                  valid_from:toString(observation.valid_from),
                  last_seen:toString(observation.observed_at)}) AS levels
}
CALL (symbol) {
  MATCH (state:StructureSnapshot {symbol:symbol})
  WHERE state.observed_at <= datetime($as_of)
  WITH state.timeframe AS timeframe,state ORDER BY state.observed_at DESC
  WITH timeframe,head(collect(state)) AS latest
  RETURN collect(latest{.timeframe,.location,.auction_state,.evidence_confidence,
                         observed_at:toString(latest.observed_at),.snapshot_epoch}) AS structures
}
RETURN symbol,levels,structures
"""

INTRADAY_STORY_QUERY = """
UNWIND $symbols AS symbol
CALL (symbol) {
  MATCH (story:IntradayStory {symbol:symbol})
  WHERE story.as_of_utc <= datetime($as_of)
    AND story.recorded_at_utc <= datetime($known_as_of)
  WITH story ORDER BY story.as_of_utc DESC
  LIMIT $story_limit
  CALL (story) {
    OPTIONAL MATCH (story)-[edge:HAS_CONFIRMED_SWING]->(swing:IntradaySwing)
    WITH edge,swing ORDER BY edge.ordinal
    RETURN collect(CASE WHEN swing IS NULL THEN null ELSE
      swing{.*} END) AS raw_swings
  }
  CALL (story) {
    OPTIONAL MATCH (story)-[:HAS_LEVEL_READ]->(levelReadNode:IntradayLevelRead)
    WITH levelReadNode ORDER BY levelReadNode.touch_episodes_today DESC,
                                 levelReadNode.timeframe,levelReadNode.level_id
    RETURN collect(CASE WHEN levelReadNode IS NULL THEN null ELSE
      levelReadNode{.*} END) AS raw_levels
  }
  RETURN collect(story{.*,
                       as_of_utc:toString(story.as_of_utc),
                       swings:[item IN raw_swings WHERE item IS NOT NULL],
                       level_reads:[item IN raw_levels WHERE item IS NOT NULL]}) AS stories
}
RETURN symbol,stories
"""

INTRADAY_STORY_AVAILABILITY_QUERY = """
UNWIND $symbols AS symbol
OPTIONAL MATCH (story:IntradayStory {symbol:symbol})
RETURN symbol,count(story) AS story_count
"""


class Neo4jMarketGraph:
    def __init__(self, driver, database: str) -> None:
        self.driver = driver
        self.database = database

    @classmethod
    def connect(cls, config):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("neo4j Python driver is not installed") from exc
        driver = GraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
            connection_timeout=3.0,
            max_connection_pool_size=8,
            notifications_min_severity="WARNING",
        )
        driver.verify_connectivity()
        return cls(driver, config.database)

    def close(self) -> None:
        self.driver.close()

    def ensure_schema(self) -> None:
        for query in SCHEMA_QUERIES:
            self.driver.execute_query(query, database_=self.database)

    def upsert_rows(self, rows: list[dict]) -> None:
        if not rows:
            return
        self.driver.execute_query(
            DELETE_EVENT_BUCKET_EDGES,
            event_ids=[row["event_id"] for row in rows], database_=self.database,
        )
        self.driver.execute_query(UPSERT_EVENTS, rows=rows, database_=self.database)
        stories = [row["intraday_story"] for row in rows if row.get("intraday_story")]
        if stories:
            self.driver.execute_query(
                UPSERT_INTRADAY_STORIES, stories=stories, database_=self.database
            )
            self.driver.execute_query(
                LINK_INTRADAY_LEVELS, stories=stories, database_=self.database
            )
        edges = list({(edge["child_id"], edge["parent_id"]): edge
                      for row in rows for edge in row["bucket_edges"]}.values())
        if edges:
            self.driver.execute_query(UPSERT_BUCKET_EDGES, edges=edges, database_=self.database)
        next_edges = [
            {"previous_id": row["previous_event_id"], "current_id": row["event_id"]}
            for row in rows if row.get("previous_event_id")
        ]
        if next_edges:
            self.driver.execute_query(UPSERT_NEXT_EDGES, edges=next_edges, database_=self.database)

    def upsert_market_state(self, state: dict) -> None:
        if state.get("levels"):
            self.driver.execute_query(UPSERT_LEVELS, rows=state["levels"], database_=self.database)
        if state.get("structures"):
            self.driver.execute_query(
                UPSERT_STRUCTURES, rows=state["structures"], database_=self.database
            )

    def context(self, symbols: tuple[str, ...], per_timeframe: int = 12,
                as_of: str | None = None, known_as_of: str | None = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        market_as_of = as_of or now
        knowledge_as_of = known_as_of or now
        records, _, _ = self.driver.execute_query(
            CONTEXT_QUERY,
            symbols=list(symbols),
            timeframes=["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
            as_of=market_as_of,
            known_as_of=knowledge_as_of,
            per_timeframe=max(1, min(int(per_timeframe), 24)),
            database_=self.database,
        )
        result = {
            "status": "ready",
            "as_of_utc": market_as_of,
            "known_as_of_utc": knowledge_as_of,
            "symbols": {
                record["symbol"]: {
                    group["timeframe"]: group["events"]
                    for group in sorted(
                        record["timeframe_groups"], key=lambda value: value["timeframe"]
                    )
                }
                for record in records
            },
        }
        sessions, _, _ = self.driver.execute_query(
            SESSION_CONTEXT_QUERY, symbols=list(symbols), as_of=market_as_of,
            known_as_of=knowledge_as_of, session_limit=16, database_=self.database,
        )
        result["session_summaries"] = {
            record["symbol"]: record["sessions"] for record in sessions
        }
        structures, _, _ = self.driver.execute_query(
            STRUCTURE_CONTEXT_QUERY, symbols=list(symbols),
            timeframes=["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
            event_types=list(STRUCTURE_EVENT_TYPES), structure_limit=12,
            structure_rule_version="market-structure-shadow-v3-deduped",
            as_of=market_as_of, known_as_of=knowledge_as_of,
            database_=self.database,
        )
        for record in structures:
            result["symbols"].setdefault(record["symbol"], {})["structure_evidence"] = {
                group["timeframe"]: group["events"] for group in record["timeframe_groups"]
            }
        maps, _, _ = self.driver.execute_query(
            MARKET_MAP_QUERY, symbols=list(symbols), as_of=market_as_of,
            database_=self.database
        )
        for record in maps:
            target = result["symbols"].setdefault(record["symbol"], {})
            target["market_levels"] = record["levels"]
            target["market_structure"] = record["structures"]
        availability, _, _ = self.driver.execute_query(
            INTRADAY_STORY_AVAILABILITY_QUERY,
            symbols=list(symbols), database_=self.database,
        )
        available_symbols = [
            record["symbol"] for record in availability if int(record["story_count"]) > 0
        ]
        story_map = {symbol: [] for symbol in symbols}
        if available_symbols:
            stories, _, _ = self.driver.execute_query(
                INTRADAY_STORY_QUERY, symbols=available_symbols, as_of=market_as_of,
                known_as_of=knowledge_as_of, story_limit=6, database_=self.database,
            )
            story_map.update({record["symbol"]: record["stories"] for record in stories})
        result["intraday_stories"] = story_map
        return result
