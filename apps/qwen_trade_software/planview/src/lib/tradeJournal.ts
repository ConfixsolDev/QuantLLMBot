export interface LossReason {
  code?: string;
  evidence?: unknown;
}

export interface QwenTradeAnalysis {
  summary: string;
  entry_assessment: string;
  management_assessment: string;
  what_worked: string[];
  what_failed: string[];
  likely_loss_reasons: string[];
  lesson: string;
  confidence: number;
}

export interface TradeExitLeg {
  kind: "partial" | "final";
  deal?: number | null;
  order?: number | null;
  volume: number;
  price: number;
  gross_pnl?: number | null;
  costs?: number | null;
  net_pnl?: number | null;
  comment?: string | null;
  closed_at_utc?: string | null;
  remaining_volume?: number | null;
}

export interface EntryEvidence {
  selected_zone?: {
    low_id?: string | null; high_id?: string | null;
    zone_low?: number | null; zone_high?: number | null;
    owning_timeframe?: string | null;
  };
  decision?: {
    reason?: string | null; decision_time_utc?: string | null;
    evidence_ids?: string[]; regime_hint?: string | null;
    regime_state?: string | null; trend_direction?: string | null;
  };
  execution_trigger?: {
    gate?: string | null; evidence_id?: string | null;
    open_time_utc?: string | null; close_time_utc?: string | null;
    open?: number | null; high?: number | null; low?: number | null;
    close?: number | null; direction?: string | null;
  };
  invalidation?: {
    level_id?: string | null; planned_price?: number | null;
    structural_price?: number | null; broker_price?: number | null;
  };
  target?: {
    level_id?: string | null; planned_price?: number | null;
    structural_price?: number | null; broker_price?: number | null;
  };
}

export interface TradeJournalRow {
  proposal_id: string;
  strategy_id?: string | null;
  strategy_version?: string | null;
  magic_number?: number | null;
  comment?: string | null;
  execution_id?: string | null;
  symbol: string;
  side: string;
  result: "win" | "loss" | "breakeven";
  idea_summary?: string | null;
  idea_reason?: string | null;
  model?: string | null;
  confidence?: number | null;
  structure_timeframe?: string | null;
  entry_time_utc?: string | null;
  exit_time_utc?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  volume?: number | null;
  initial_stop?: number | null;
  initial_target?: number | null;
  geometry_source?: string | null;
  gross_pnl?: number | null;
  costs?: number | null;
  net_pnl?: number | null;
  peak_pnl?: number | null;
  maximum_drawdown?: number | null;
  mfe_price?: number | null;
  mae_price?: number | null;
  giveback_price?: number | null;
  secured_cash?: number | null;
  secured_stop?: number | null;
  secured_at_utc?: string | null;
  exit_reason?: string | null;
  attribution_source?: string | null;
  holding_seconds?: number | null;
  loss_reasons: Array<LossReason | string>;
  evidence_ids: string[];
  entry_evidence: EntryEvidence;
  qwen_analysis?: QwenTradeAnalysis | null;
  qwen_analysis_status: "pending" | "retry" | "complete";
  qwen_analyzed_at_utc?: string | null;
  qwen_analysis_model?: string | null;
  exit_legs: TradeExitLeg[];
}

export interface TradeJournalResponse {
  count: number;
  generated_at_utc: string;
  trades: TradeJournalRow[];
}
