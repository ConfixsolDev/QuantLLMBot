"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchCandles, fetchPlan, fetchSnapshot } from "@/lib/api";
import type { HourlyUpdate, PlannerState, Snapshot, TradeIdea } from "@/lib/types";
import { DayBranchPanel } from "@/components/DayBranchPanel";
import { ExecutionFunnelPanel } from "@/components/ExecutionFunnelPanel";
import { TimeframeLadderPanel } from "@/components/TimeframeLadder";
import { HeaderClock } from "@/components/HeaderClock";
import { CheatSheetPanel } from "@/components/CheatSheetPanel";
import { PlanChart } from "@/components/PlanChart";
import { TechnicalDetails } from "@/components/NarrativePanels";
import { buildPlanViewModel } from "@/lib/viewModel";
import { MarketIntelligencePanel } from "@/components/MarketIntelligencePanel";

const TIMEFRAMES = ["H4", "H1", "M15"] as const;

export default function PlanViewPage() {
  const [plan, setPlan] = useState<PlannerState | null>(null);
  const [candles, setCandles] = useState<
    import("@/lib/types").Candle[]
  >([]);
  const [timeframe, setTimeframe] =
    useState<(typeof TIMEFRAMES)[number]>("M15");
  const [selectedHourlyId, setSelectedHourlyId] = useState<string | null>(null);
  const [tradeIdea, setTradeIdea] = useState<TradeIdea | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [cheatOpen, setCheatOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPlan = useCallback(async () => {
    try {
      const data = await fetchPlan();
      setPlan(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plan");
    }
  }, []);

  const loadCandles = useCallback(async () => {
    try {
      const data = await fetchCandles(timeframe, 200);
      setCandles(data.candles);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candles");
    }
  }, [timeframe]);

  const loadTradeIdea = useCallback(async () => {
    try {
      const snapshot = await fetchSnapshot();
      setTradeIdea(snapshot.qwen ?? null);
      setSnapshot(snapshot);
    } catch {
      // Trade idea overlay is optional; chart still works without it.
    }
  }, []);

  useEffect(() => {
    loadPlan();
    const timer = setInterval(loadPlan, 15000);
    return () => clearInterval(timer);
  }, [loadPlan]);

  useEffect(() => {
    loadTradeIdea();
    const timer = setInterval(loadTradeIdea, 15000);
    return () => clearInterval(timer);
  }, [loadTradeIdea]);

  useEffect(() => {
    loadCandles();
    const timer = setInterval(loadCandles, 30000);
    return () => clearInterval(timer);
  }, [loadCandles]);

  const hourlyUpdates = plan?.hourly_updates ?? [];
  const tradeIdeaStack =
    plan?.trade_idea_stack ??
    plan?.session_plan?.trade_idea_stack ??
    plan?.day_plan?.trade_idea_stack ??
    null;

  const selectedUpdate: HourlyUpdate | null = useMemo(() => {
    if (!hourlyUpdates.length) return null;
    if (selectedHourlyId) {
      return hourlyUpdates.find((u) => u.hourly_id === selectedHourlyId) ?? null;
    }
    return hourlyUpdates[hourlyUpdates.length - 1];
  }, [hourlyUpdates, selectedHourlyId]);

  const viewModel = useMemo(
    () =>
      buildPlanViewModel(
        plan,
        { symbol: plan?.symbol, price: plan?.live_price ?? undefined },
        tradeIdeaStack ?? undefined,
        selectedUpdate ?? undefined,
      ),
    [plan, tradeIdeaStack, selectedUpdate],
  );

  const defaultClock = {
    utc_time: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    utc_hour: new Date().getUTCHours(),
    hours_into_day: new Date().getUTCHours(),
    session: "off_session",
    hour_of_session: 1,
    sessions_completed: [],
    next_boundary_utc: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  };

  return (
    <main className="mx-auto min-h-screen max-w-7xl space-y-4 p-4 md:p-6">
      <HeaderClock
        clock={plan?.clock ?? defaultClock}
        plannerStatus={plan?.planner_status ?? "loading"}
        plannerAlive={plan?.planner_alive}
        runtime={
          plan?.runtime_status ?? {
            model: plan?.model,
            model_installed: plan?.model_installed,
            model_resident: plan?.model_resident,
            model_device: plan?.model_device,
            mt5_connected: plan?.mt5_connected,
            planner_alive: plan?.planner_alive,
          }
        }
      />

      <div className="flex flex-wrap gap-2">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            type="button"
            onClick={() => setTimeframe(tf)}
            className={`rounded px-3 py-1 text-sm ${
              timeframe === tf
                ? "bg-gold text-ink"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          {error} — ensure backend is running on :48632 and planner process is up.
        </div>
      )}

      <PlanChart
        candles={candles}
        dayPlan={plan?.day_plan ?? null}
        sessionPlan={plan?.session_plan ?? null}
        tradeIdea={tradeIdea}
        profitProtection={snapshot?.profit_protection}
        tradeIdeaStack={tradeIdeaStack ?? null}
        hourlyUpdates={hourlyUpdates}
        selectedHourlyId={selectedUpdate?.hourly_id ?? null}
        onSelectHour={setSelectedHourlyId}
        timeframe={timeframe}
        onOpenCheat={() => setCheatOpen(true)}
        runtime={
          plan?.runtime_status ?? {
            model: plan?.model,
            model_installed: plan?.model_installed,
            model_resident: plan?.model_resident,
            model_device: plan?.model_device,
            mt5_connected: plan?.mt5_connected,
            planner_alive: plan?.planner_alive,
          }
        }
      />

      <CheatSheetPanel
        open={cheatOpen}
        onClose={() => setCheatOpen(false)}
        livePrice={plan?.live_price}
        dayPlan={plan?.day_plan ?? null}
        sessionPlan={plan?.session_plan ?? null}
        tradeIdea={tradeIdea}
      />

      {/* One home per fact: ladder = TF lean; day plan = bull/bear side by side. */}
      <TimeframeLadderPanel ladder={plan?.timeframe_ladder} />

      <MarketIntelligencePanel
        intelligence={snapshot?.market_intelligence}
        trace={snapshot?.qwen_trace}
        gate={snapshot?.qwen_event_gate}
      />

      <DayBranchPanel
        branches={plan?.day_branches}
        livePrice={plan?.live_price}
        liveSanity={plan?.day_plan_live_sanity}
        referencePrice={plan?.day_plan?.reference_price ?? null}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <TechnicalDetails vm={viewModel} />
        <ExecutionFunnelPanel funnel={plan?.execution_funnel} />
      </div>
    </main>
  );
}
