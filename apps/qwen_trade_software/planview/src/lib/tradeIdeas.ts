export type TradeIdeaGeometry = {
  side?: string | null;
  entry_low?: number | null;
  entry_high?: number | null;
  entry_mid?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  stop_distance?: number | null;
  target_distance?: number | null;
  plan_reward_risk?: number | null;
  structural_stop_loss?: number | null;
  structural_take_profit?: number | null;
  structural_stop_distance?: number | null;
  structural_target_distance?: number | null;
  structural_reward_risk?: number | null;
  structure_timeframe?: string | null;
  frame_min_stop?: number | null;
  frame_min_target?: number | null;
  geometry_source?: string | null;
  rr_issue?: string | null;
};

export type TradeIdeaOutcome = {
  event?: string | null;
  reason?: string | null;
  detail?: string | null;
  side?: string | null;
  average_entry?: number | null;
  net_pnl?: number | null;
  created_at_utc?: string | null;
};

export type TradeIdeaRow = {
  proposal_id: string;
  created_at_utc?: string | null;
  symbol?: string | null;
  price?: number | null;
  bias?: string | null;
  confidence: number;
  summary?: string | null;
  status?: string | null;
  plan_reason?: string | null;
  side?: string | null;
  entry_low_id?: string | null;
  entry_high_id?: string | null;
  stop_level_id?: string | null;
  target_level_id?: string | null;
  geometry: TradeIdeaGeometry;
  outcome?: TradeIdeaOutcome | null;
  blocked_by_geometry: boolean;
  geometry_block_detail?: string | null;
};

export type TradeIdeasResponse = {
  min_confidence: number;
  days_back: number;
  count: number;
  ready_count: number;
  geometry_blocked_count: number;
  frame_min_targets: Record<string, number>;
  frame_min_stops: Record<string, number>;
  ideas: TradeIdeaRow[];
};

export type LifecycleResponse = {
  active_idea?: {
    state?: string;
    watching_zone?: string;
    watching_side?: string;
    active_idea?: {
      idea_id?: string;
      zone_id?: string;
      side?: string;
      zone?: number[];
      thesis?: string;
      state?: string;
      approach_summary?: Record<string, unknown>;
    };
  };
  approach?: {
    assessment?: string;
    current_distance?: number;
    distance_trend?: string;
    price_reached_zone?: boolean;
    observations?: number;
    target_zone?: number[];
  };
};
