export type PlanStatus = "on_track" | "drifting" | "invalidated";
export type LayerValidationStatus = PlanStatus | "pending";
export type IdeaLayerStatus = "active" | "revised" | "invalidated";

export interface Clock {
  utc_time: string;
  utc_hour: number;
  hours_into_day: number;
  session: string;
  hour_of_session: number;
  sessions_completed: string[];
  next_boundary_utc: string;
  trading_date_utc?: string;
}

export interface Scenario {
  trigger: string;
  targets: number[];
  invalidation: number;
  evidence: string[];
}

export interface KeyLevel {
  price: number;
  label: string;
  role: string;
}

export interface Validator {
  verdict: "agree" | "disagree";
  per_scenario?: { bullish: string; bearish: string };
  notes?: string;
  tradeable: boolean;
}

export interface PriceSanity {
  ok: boolean;
  live_price: number | null;
  reference_price?: number | null;
  prior_reference_price?: number | null;
  max_deviation_allowed?: number | null;
  source?: string;
  failures: string[];
}

export interface TradeIdeaH4 {
  side: "buy" | "sell" | "neutral";
  thesis: string;
  invalidation: number;
  targets: number[];
  key_level_refs: string[];
  status: IdeaLayerStatus;
  revision: number;
}

export interface TradeIdeaH1 {
  summary: string;
  levels: { price: number; label: string }[];
  invalidation: number;
  status: IdeaLayerStatus | string;
}

export interface TradeIdeaM15 {
  side: "buy" | "sell";
  pullback_zone: [number, number] | number[];
  invalidation: number;
  target: number;
  status: IdeaLayerStatus | string;
}

export interface TradeIdeaRevision {
  session?: string;
  from_revision?: number;
  to_revision?: number;
  prior_verdict_summary?: string;
  performance?: string;
  change_summary?: string;
  at_utc?: string;
}

export interface TradeIdeaStack {
  day_idea_id?: string;
  h4: TradeIdeaH4 | null;
  h1: TradeIdeaH1 | null;
  m15: TradeIdeaM15 | null;
  revisions: TradeIdeaRevision[];
  layer_validation: {
    h4: LayerValidationStatus;
    h1: LayerValidationStatus;
    m15: LayerValidationStatus;
  };
  updated_at_utc?: string;
}

export interface DayPlan {
  artifact: "day_plan";
  day_plan_id: string;
  clock: Clock;
  reference_price: number;
  bullish_scenario: Scenario;
  bearish_scenario: Scenario;
  key_levels: KeyLevel[];
  expected_session_behaviour: Record<string, string>;
  trade_idea_stack?: TradeIdeaStack;
  validator?: Validator;
  tradeable?: boolean;
  price_sanity?: PriceSanity;
}

export interface EntryZone {
  side: "buy" | "sell";
  zone: [number, number];
  invalidation: number;
  target: number;
}

export interface SessionPlan {
  artifact: "session_plan";
  session_plan_id: string;
  day_plan_id: string;
  session: string;
  clock: Clock;
  active_scenario: "bullish" | "bearish" | "neutral";
  confidence: number;
  summary: string;
  entry_zones: EntryZone[];
  trade_idea_stack?: TradeIdeaStack;
  validator?: Validator;
  tradeable?: boolean;
}

export interface HourOhlc {
  o: number;
  h: number;
  l: number;
  c: number;
}

export interface HourlyUpdate {
  artifact: "hourly_update";
  hourly_id: string;
  day_plan_id: string;
  session_plan_id: string;
  clock: Clock;
  hour_ohlc?: HourOhlc | null;
  plan_status: PlanStatus;
  confidence_delta: number;
  levels_touched: { price: number; label: string; result: string }[];
  note: string;
  layer_validation?: {
    h4: LayerValidationStatus;
    h1: LayerValidationStatus;
    m15: LayerValidationStatus;
  };
  actual_vs_expected: { expected: string; observed: string; match: boolean };
}

export interface SessionVerdict {
  artifact: "session_verdict";
  session_verdict_id: string;
  session: string;
  planned_vs_actual: string;
  scenario_outcome: string;
  zones_hit: string[];
  lesson_candidate: string;
}

export interface RuntimeStatus {
  model?: string;
  model_installed?: boolean;
  model_resident?: boolean;
  model_device?: "GPU" | "CPU" | "MIXED" | "unloaded" | string;
  mt5_connected?: boolean;
  planner_alive?: boolean;
}

export interface RegimeContext {
  regime_state?: string;
  regime_hint?: string;
  regime_family?: "trend" | "range" | "reversal" | string;
  trend_direction?: "buy" | "sell" | null;
  volatility_state?: string | null;
  regime_transition?: boolean | null;
  pullback_active?: boolean;
  transition_age_minutes?: number | null;
  source?: "live_management" | "latest_entry_decision" | "runtime_memory" | string;
}

/**
 * A day plan is a CONTAINER of two branches, not a directional bet.
 * It has no status of its own — each branch resolves independently, and only a
 * CLOSE through a branch's own invalidation can kill it.
 *
 * 2026-08-11: the old screen showed H4/H1/M15 all INVALIDATED because a
 * session-forecast miss cascaded onto every layer, while price ran through both
 * of the bullish idea's targets and never touched its invalidation.
 */
export type BranchState =
  | "armed"        // waiting for its trigger
  | "likely"       // evidence accumulating
  | "confirmed"    // trigger fired on a closed candle — callable
  | "spent"        // targets reached
  | "invalidated"; // price CLOSED through its own level

export interface PlanBranch {
  side: "buy" | "sell";
  trigger_price: number | null;
  trigger_text: string;
  targets: number[];
  invalidation: number | null;
  evidence: string[];
  state: BranchState;
  reason: string;
  confidence: number;
}

export interface DayBranches {
  bullish: PlanBranch;
  bearish: PlanBranch;
  headline: string;
  callable_side: "buy" | "sell" | null;
  version: string;
}

/**
 * Why the system is or is not trading. The plan panels show intent; this shows
 * what happened when intent tried to become a trade.
 *
 * 2026-08-11: 547 proposals produced 9 ready, 9 attempted, 2 filled — and the
 * only way to see that was reading paper-runner.log by hand.
 */
export interface FunnelStage {
  name: string;
  count: number;
  detail: string;
}

export interface FunnelBlocker {
  stage: string;
  code: string;
  label: string;
  count: number;
}

export interface ExecutionFunnel {
  stages: FunnelStage[];
  blockers: FunnelBlocker[];
  headline: string;
  net_pnl: number | null;
  closed_trades: number;
  wins: number;
  version: string;
}

export interface TimeframePair {
  timeframe: string;
  role: string;
  bull: PlanBranch;
  bear: PlanBranch;
  side: "buy" | "sell" | null;
  note: string;
}

export interface TimeframeLadder {
  pairs: TimeframePair[];
  headline: string;
  aligned: boolean;
  version: string;
}

export type OpportunityLocationState =
  | "outside_zone"
  | "approaching"
  | "inside_zone"
  | "armed"
  | "triggered"
  | "invalidated";

export interface OpportunityActiveZone {
  zone_id: string;
  side: "buy" | "sell";
  timeframe: string;
  low: number;
  high: number;
  distance: number;
  location_state: OpportunityLocationState;
  role: string;
  lifecycle_status: string;
  structure_proven: boolean;
  evidence_ids: string[];
}

export interface OpportunityBranch {
  side: "buy" | "sell";
  state: OpportunityLocationState;
  committed: boolean;
  zone: OpportunityActiveZone | null;
  reason: string;
  proof_timeframe: string | null;
  proof_evidence_ids: string[];
}

export interface OpportunityShadow {
  version: string;
  mode: "shadow_only";
  execution_authority: false;
  committed_side?: "buy" | "sell" | "wait";
  shadow_triggered_side?: "buy" | "sell" | null;
  decision: "buy" | "sell" | "wait";
  reason?: string;
  branches?: {
    buy: OpportunityBranch;
    sell: OpportunityBranch;
  };
  active_zone_registry?: {
    version: string;
    mode: "shadow_only";
    execution_authority: false;
    live_price: number;
    raw_zone_count: number;
    deduplicated_zone_count: number;
    selected_zone_count: number;
    zones: OpportunityActiveZone[];
  };
}

export interface PlannerState {
  updated_at_utc: string;
  symbol: string;
  clock: Clock;
  day_plan: DayPlan | null;
  day_branches?: DayBranches | null;
  execution_funnel?: ExecutionFunnel | null;
  timeframe_ladder?: TimeframeLadder | null;
  opportunity_shadow?: OpportunityShadow | null;
  session_plan: SessionPlan | null;
  hourly_updates: HourlyUpdate[];
  session_verdicts: SessionVerdict[];
  trade_idea_stack?: TradeIdeaStack | null;
  planner_status: string;
  last_error: string | null;
  generated_at_utc?: string;
  planner_alive?: boolean;
  live_price?: number | null;
  day_plan_live_sanity?: PriceSanity | null;
  session_plan_live_sanity?: PriceSanity | null;
  model?: string;
  model_installed?: boolean;
  model_resident?: boolean;
  model_device?: string;
  model_size_vram?: number;
  mt5_connected?: boolean;
  runtime_status?: RuntimeStatus;
}

export interface ExecutionPlan {
  status: "ready" | "wait" | string;
  side?: "buy" | "sell";
  entry_low?: number;
  entry_high?: number;
  stop_loss?: number;
  take_profit?: number;
  decision_confidence?: number;
  reason?: string;
}

export interface TradeIdea {
  bias?: string;
  confidence?: number;
  summary?: string;
  invalidation?: string;
  updated_at?: string;
  proposal_id?: string;
  proposal_price?: number;
  execution_plan?: ExecutionPlan | null;
}

export interface Snapshot {
  qwen?: TradeIdea | null;
  connected?: boolean;
  symbol?: string;
  price?: number;
  requested_symbol?: string;
  requested_market?: string;
  data_market?: string;
  availability_reason?: string;
  positions?: Array<{ ticket?: number; price_open?: number; price_current?: number }>;
  profit_protection?: {
    ticket?: number; state?: string; armed?: boolean; entry?: number;
    current?: number; peak?: number; candidate_stop?: number | null;
    progress_r?: number; locked_cash?: number; risk_cash?: number;
    timestamp_utc?: string;
  } | null;
  paper_execution?: {
    event?: string;
    reason?: string;
    fills?: unknown[];
    proposal_id?: string;
  } | null;
  market_intelligence?: MarketIntelligence;
  qwen_trace?: QwenTrace;
  qwen_event_gate?: { fingerprint?: string; called_at_epoch?: number; reason?: string };
  regime_context?: RegimeContext;
}

export interface StructureMemoryState {
  state?: string; direction?: string; active_leg?: string; transition?: string | null;
  invalidation_level_id?: string | null; latest_evidence_id?: string;
  structure_epoch?: string; unresolved_condition?: string;
}

export interface RetrievalAudit {
  request_id: string; status: string; requested_at_utc?: string;
  request?: Record<string, unknown>; result?: { row_count?: number; [key: string]: unknown };
}

export interface MarketIntelligence {
  status?: string; updated_at_utc?: string;
  hierarchy?: Record<string, StructureMemoryState>;
  dxy?: { broker_symbol?: string | null; states?: Record<string, { status?: string; direction?: string }> };
  relationship?: { state?: string; gold_pressure?: string; doctrine?: string };
  recent_retrievals?: RetrievalAudit[];
  worker_health?: {
    status?: string; updated_at_epoch?: number; replayed_events?: number;
    inserted_total?: number; dxy_broker_symbol?: string | null;
  };
  graph_health?: {
    status?: string; updated_at_epoch?: number;
    projection?: { status?: string; selected?: number; projected?: number };
    outbox?: { pending?: number; projected?: number; dead?: number };
  };
  graph_context?: GraphContext;
}

export interface GraphStructureEvidence {
  id?: string; timeframe?: string; event_type?: string; event_time_utc?: string;
  confirmation_time_utc?: string; knowledge_time_utc?: string;
  evidence_id?: string; direction?: string; status?: string; mode?: string;
  execution_authority?: boolean; detector?: string; rule_version?: string;
  explanation?: string;
  structure_label?: string; prior_structure?: string;
  zone_id?: string; zone_kind?: string; zone_low?: number; zone_high?: number;
  zone_status?: string; source_evidence_id?: string;
}

export interface GraphContext {
  status?: string; as_of_utc?: string; known_as_of_utc?: string; age_seconds?: number;
  mode?: string; packet_version?: string; packet_bytes?: number;
  packet_budget_bytes?: number; within_packet_budget?: boolean; execution_authority?: boolean;
  projection?: { pending?: number; projected?: number; dead?: number };
  xauusd_all_timeframe_temporal_structure?: Array<{
    timeframe?: string; trend_state?: string; forming_leg?: string;
    auction_state?: string; range_location?: string; latest_structure?: string;
    candle_seconds_remaining?: number | null; candle_percent_complete?: number | null;
    freshness?: string; evidence_id?: string;
    volume_confirmation?: { ratio?: number | null; sample_count?: number };
  }>;
  active_zone_positions?: Record<string, {
    zone_id?: string; zone_low?: number; zone_high?: number; distance_to_zone?: number;
    distance_to_low_boundary?: number; distance_to_high_boundary?: number;
    current_relation?: string;
    contributing_timeframes?: string[]; primary_owning_timeframe?: string;
    structural_proof?: string; history?: string; evidence_ids?: string[];
  } | string | null>;
  active_zone_plan?: {
    status?: string; source?: string; selection_rule?: string;
    focus_zone?: {
      zone_low?: number; zone_high?: number; primary_owning_timeframe?: string;
      distance_to_zone?: number; current_relation?: string;
    } | null;
    support_below?: { zone_low?: number; zone_high?: number; distance_to_zone?: number } | null;
    resistance_above?: { zone_low?: number; zone_high?: number; distance_to_zone?: number } | null;
    directional_authority?: boolean; execution_authority?: boolean;
  };
  symbols?: Record<string, {
    structure_evidence?: Record<string, GraphStructureEvidence[]>;
    [key: string]: unknown;
  }>;
}

export interface QwenTrace {
  model?: string; contract_version?: string; prompt_bytes?: number;
  decision_wall_seconds?: number | null; retrieval_requests?: Record<string, unknown>[];
  retrieval_results?: Record<string, unknown>[]; evidence_ids?: string[];
  acknowledged_epochs?: Record<string, string>; raw_response?: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  timeframe: string;
  count: number;
  candles: Candle[];
}

export const SESSION_LABELS: Record<string, string> = {
  asia: "Tokyo",
  pre_london: "Pre-London",
  london: "London",
  overlap: "Overlap",
  new_york: "New York",
  off_session: "Off Session",
};

export const PLANNING_SESSIONS = ["asia", "london", "overlap", "new_york"] as const;
