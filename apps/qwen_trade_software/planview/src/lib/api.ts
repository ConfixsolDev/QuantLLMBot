import type { CandlesResponse, PlannerState, Snapshot } from "./types";
import type { TradeIdeasResponse } from "./tradeIdeas";

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

export function fetchSnapshot(): Promise<Snapshot> {
  return fetchJson<Snapshot>("/snapshot");
}

export function fetchPlanHistory(date: string) {
  return fetchJson(`/plan/history?date=${date}`);
}

export function fetchTradeIdeas(options?: {
  minConfidence?: number;
  days?: number;
  readyOnly?: boolean;
  limit?: number;
}): Promise<TradeIdeasResponse> {
  const params = new URLSearchParams({
    min_confidence: String(options?.minConfidence ?? 50),
    days: String(options?.days ?? 2),
    ready_only: options?.readyOnly ? "1" : "0",
    limit: String(options?.limit ?? 300),
  });
  return fetchJson<TradeIdeasResponse>(`/trade-ideas?${params.toString()}`);
}
