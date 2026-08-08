export type PlanStatus = "on_track" | "drifting" | "invalidated";

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

export interface DayPlan {
  artifact: "day_plan";
  day_plan_id: string;
  clock: Clock;
  reference_price: number;
  bullish_scenario: Scenario;
  bearish_scenario: Scenario;
  key_levels: KeyLevel[];
  expected_session_behaviour: Record<string, string>;
  validator?: Validator;
  tradeable?: boolean;
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

export interface PlannerState {
  updated_at_utc: string;
  symbol: string;
  clock: Clock;
  day_plan: DayPlan | null;
  session_plan: SessionPlan | null;
  hourly_updates: HourlyUpdate[];
  session_verdicts: SessionVerdict[];
  planner_status: string;
  last_error: string | null;
  generated_at_utc?: string;
  planner_alive?: boolean;
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
