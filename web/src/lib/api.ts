// Talks to the QuantLLM backend (python -m quantllm serve).
// Served by the backend itself the API is same-origin ("/api/..."); during
// `npm run dev` set NEXT_PUBLIC_API_BASE=http://127.0.0.1:8765.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number };

export type Line = { kind: "bos" | "choch"; direction: "up" | "down"; price: number; t1: number; t2: number; label: string };
export type Box = {
  kind: "fvg" | "ob" | "zone" | "range"; tf: string; side: string; low: number; high: number;
  t1: number; t2: number; status: string; tests: number; alive: boolean;
};
export type Marker = {
  kind: string; time: number; price: number; position: "above" | "below"; text: string; detail?: string;
  level?: number; level_t1?: number;
};
export type Level = { name: string; side: "high" | "low"; price: number; t1: number; confirmed: boolean };
export type Swing = { time: number; price: number; kind: "high" | "low"; label: string };
export type HLevel = {
  id: string; price: number; side: "high" | "low"; sources: string[]; tests: number;
  t1: number; t2: number; alive: boolean; label: string;
};
export type VwapPoint = { time: number; vwap: number | null; bands?: Record<string, [number, number]>; start?: number };
export type Overlays = {
  lines: Line[]; boxes: Box[]; markers: Marker[]; levels: Level[]; swings: Swing[];
  curves?: Record<string, VwapPoint[]>;          // VWAP per anchor: day / week / session
  hlevels?: HLevel[];                            // higher-timeframe levels and their tests
};

export type Chart = {
  tf: string; candles: Candle[]; forming?: Candle | null; overlays: Overlays | null; as_of: number | null;
  future?: Candle[];                             // replay only: what happened next (shaded)
  trend?: Record<string, Trend>; price?: number;
};

export type Health = {
  state: string; message: string; progress: number; mt5: string; symbol: string; database?: string;
  config_id: string; config_hash: string; last_bar: number | null; bars_processed: number; events: number;
};

export type Trend = { state: "up" | "down" | "none"; protected: number | null;
  last_break: { kind: string; direction: string; level: number; break_time: number } | null };

export type Snapshot = {
  as_of: number | null; price?: number; atr?: Record<string, number | null>;
  trend?: Record<string, Trend>;
  liquidity_pools?: { kind: string; side: string; price: number; source_tf: string; state: string }[];
  recent_liquidity?: { kind: string; side: string; time: number; levels: [string, number][] }[];
  top_zones?: { score: number; zone: { tf: string; side: string; low: number; high: number; tests: number; status: string } }[];
  order_blocks?: { tf: string; direction: string; low: number; high: number; status: string; tests: number }[];
  fair_value_gaps?: { tf: string; direction: string; low: number; high: number; status: string }[];
  ranges?: Record<string, { top: number; bottom: number } | null>;
  levels?: { name: string; high: number; low: number; end: number }[];
  forming?: { session: { name: string; high: number; low: number } | null; day: { high: number; low: number } | null };
  pending_patterns?: { kind: string; neckline: number }[];
  event_counts?: Record<string, number>;
  htf_levels?: { id: string; price: number; side: string; sources: string[]; tests: number; held: number; testing: number | null }[];
  recent_level_events?: { kind: string; time: number; level: number; side: string; sources: string[];
    test_no: number | null; result: string | null; approach: string | null; pattern: string | null }[];
  vwap?: Record<string, { vwap: number; sd: number; name: string; bands: Record<string, [number, number]> } | null>;
};

// ---------------------------------------------------------------- replay
export type Detection = { id: string; kind: string; tf: string; time: number; available_at: number; text: string };
export type Verdict = "correct" | "wrong" | "missed";
export type Review = { id: string; kind: string; tf: string; time: number | null; verdict: Verdict; note: string };
export type Check = { ok: boolean; [k: string]: unknown };
export type DayChecks = {
  date: string; events: number; invariants: Check & { violations: string[] }; determinism: Check;
  no_repaint: Check & { cuts: number[]; failed_cuts: number[] };
  audit: Check & { checked: number; failed: number; examples: Record<string, string[]> };
};
export type ReplayDay = {
  date: string; start: number; end: number; detections: Detection[]; reviews: Review[]; checks: DayChecks | null;
};
export type Scorecard = {
  days_reviewed: number;
  kinds: { kind: string; correct: number; wrong: number; missed: number; precision: number | null; recall: number | null }[];
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

export const fetchHealth = () => get<Health>("/api/health");
export const fetchChart = (tf: string, bars: number) => get<Chart>(`/api/chart?tf=${tf}&bars=${bars}`);
export const fetchSnapshot = () => get<Snapshot>("/api/snapshot");

export const fetchDays = () => get<{ days: string[] }>("/api/replay/days");
export const fetchReplayDay = (date: string) => get<ReplayDay>(`/api/replay/day?date=${date}`);
export const fetchReplayChart = (date: string, tf: string, t: number, bars: number) =>
  get<Chart>(`/api/replay/chart?date=${date}&tf=${tf}&t=${t}&bars=${bars}`);
export const fetchChecks = (date: string) => get<DayChecks>(`/api/replay/checks?date=${date}`);
export const fetchScorecard = (from: string, to: string) => get<Scorecard>(`/api/reviews/summary?from=${from}&to=${to}`);

async function post(path: string, body: unknown): Promise<void> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
}
export const saveReview = (r: Review & { day: string }) => post("/api/reviews", r);
export const deleteReview = (id: string) => post("/api/reviews/delete", { id });

export const fmtTime = (t: number | null | undefined) =>
  t ? new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC" : "–";
