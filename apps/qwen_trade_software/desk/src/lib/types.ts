export type Timeframe = "M1" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1";

export type DeskView = "dashboard" | "sheet" | "cheat";

export interface Level {
  id: string;
  price: number;
  role: string;
  respect_count: number;
}

export interface ExecutionPlan {
  status: "ready" | "wait" | string;
  side?: "buy" | "sell";
  entry_low?: number;
  entry_high?: number;
  stop_loss?: number;
  take_profit?: number;
  reason?: string;
  decision_confidence?: number;
}

export interface QwenState {
  bias: string;
  confidence: number;
  summary: string;
  invalidation: string;
  updated_at: string;
  proposal_id?: string;
  proposal_price?: number;
  execution_plan?: ExecutionPlan;
}

export interface Position {
  ticket: number;
  side: string;
  volume: number;
  open_price: number;
  profit: number;
  qwen_owned?: boolean;
  comment?: string;
}

export interface PaperExecution {
  event?: string;
  proposal_id?: string;
  reason?: string;
  gross_pnl?: number;
  maximum_drawdown?: number;
  fill?: {
    price: number;
    bucket: number;
    phase: string;
  };
}

export interface Snapshot {
  connected: boolean;
  model: string;
  model_status: string;
  symbol: string;
  price: number;
  change: number;
  timeframe: string;
  levels: Partial<Record<Timeframe, Level[]>>;
  positions: Position[];
  today: {
    net_profit: number;
    baskets: number;
    deals: number;
    median_hold_seconds: number;
    win_rate: number;
  };
  qwen: QwenState;
  paper_execution?: PaperExecution | null;
  context_cache?: {
    status?: string;
  };
}

export const TIMEFRAMES: Timeframe[] = [
  "M1",
  "M5",
  "M15",
  "M30",
  "H1",
  "H4",
  "D1",
];

export const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  M1: "Intraday · reactive",
  M5: "Execution · reactive",
  M15: "Intraday · umbrella",
  M30: "Structural · strong",
  H1: "Historical · major",
  H4: "Historical · major",
  D1: "Historical anchor",
};

export const DEFAULT_SNAPSHOT: Snapshot = {
  connected: false,
  model: "qwen-trading-v002:latest",
  model_status: "Waiting for local reviewer",
  symbol: "XAUUSDr",
  price: 0,
  change: 0,
  timeframe: "M15",
  levels: {},
  positions: [],
  today: {
    net_profit: 0,
    baskets: 0,
    deals: 0,
    median_hold_seconds: 0,
    win_rate: 0,
  },
  qwen: {
    bias: "Waiting",
    confidence: 50,
    summary: "Waiting for a live MT5 and Qwen snapshot.",
    invalidation: "No active paper thesis.",
    updated_at: "",
    execution_plan: { status: "wait", reason: "Live data is not available." },
  },
};
