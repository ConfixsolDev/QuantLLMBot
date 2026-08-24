import type { CandlesResponse, PlannerState, Snapshot } from "./types";
import type { LifecycleResponse, TradeIdeasResponse } from "./tradeIdeas";
import type { TradeJournalResponse } from "./tradeJournal";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:48632";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchPlan(): Promise<PlannerState> {
  return fetchJson<PlannerState>("/plan");
}

export function fetchCandles(
  timeframe: string,
  count = 200,
): Promise<CandlesResponse> {
  return fetchJson<CandlesResponse>(`/candles?tf=${timeframe}&count=${count}`);
}

function withSymbol(path: string, symbol?: string): string {
  if (!symbol) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}symbol=${encodeURIComponent(symbol)}`;
}

export function fetchSnapshot(symbol?: string): Promise<Snapshot> {
  return fetchJson<Snapshot>(withSymbol("/snapshot", symbol));
}

export function fetchPlanHistory(date: string) {
  return fetchJson(`/plan/history?date=${date}`);
}

export function fetchTradeIdeas(options?: {
  minConfidence?: number;
  days?: number;
  readyOnly?: boolean;
  limit?: number;
  symbol?: string;
}): Promise<TradeIdeasResponse> {
  const params = new URLSearchParams({
    min_confidence: String(options?.minConfidence ?? 50),
    days: String(options?.days ?? 2),
    ready_only: options?.readyOnly ? "1" : "0",
    limit: String(options?.limit ?? 300),
  });
  if (options?.symbol) params.set("symbol", options.symbol);
  return fetchJson<TradeIdeasResponse>(`/trade-ideas?${params.toString()}`);
}

export function fetchLifecycle(symbol?: string): Promise<LifecycleResponse> {
  return fetchJson<LifecycleResponse>(withSymbol("/lifecycle", symbol));
}

export function fetchTradeJournal(options?: {
  limit?: number;
  startUtc?: string;
  endUtc?: string;
}): Promise<TradeJournalResponse> {
  const params = new URLSearchParams({
    limit: String(options?.limit ?? 200),
  });
  if (options?.startUtc) params.set("start_utc", options.startUtc);
  if (options?.endUtc) params.set("end_utc", options.endUtc);
  return fetchJson<TradeJournalResponse>(`/trade-journal?${params.toString()}`);
}
