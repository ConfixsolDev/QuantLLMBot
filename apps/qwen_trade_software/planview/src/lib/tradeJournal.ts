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

export interface TradeJournalRow {
  proposal_id: string;
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
  qwen_analysis?: QwenTradeAnalysis | null;
  qwen_analysis_status: "pending" | "retry" | "complete";
  qwen_analyzed_at_utc?: string | null;
  qwen_analysis_model?: string | null;
}

export interface TradeJournalResponse {
  count: number;
  generated_at_utc: string;
  trades: TradeJournalRow[];
}
