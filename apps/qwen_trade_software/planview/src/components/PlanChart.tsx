"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  LineStyle,
  createChart,
} from "lightweight-charts";
import type {
  Candle,
  DayPlan,
  HourlyUpdate,
  SessionPlan,
  TradeIdea,
} from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  on_track: "#22c55e",
  drifting: "#f59e0b",
  invalidated: "#ef4444",
};

interface PlanChartProps {
  candles: Candle[];
  dayPlan: DayPlan | null;
  sessionPlan: SessionPlan | null;
  tradeIdea: TradeIdea | null;
  hourlyUpdates: HourlyUpdate[];
  selectedHourlyId: string | null;
  onSelectHour: (hourlyId: string) => void;
  timeframe: string;
}

export function PlanChart({
  candles,
  dayPlan,
  sessionPlan,
  tradeIdea,
  hourlyUpdates,
  selectedHourlyId,
  onSelectHour,
  timeframe,
}: PlanChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const levelLinesRef = useRef<ReturnType<IChartApi["addLineSeries"]>[]>([]);
  const zoneLinesRef = useRef<ReturnType<IChartApi["addLineSeries"]>[]>([]);
  const ideaLinesRef = useRef<IPriceLine[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0b0f17" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: true },
      crosshair: { mode: 1 },
      width: containerRef.current.clientWidth,
      height: 440,
    });
    const series = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(
      candles.map((c) => ({
        time: c.time as unknown as import("lightweight-charts").UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const line of levelLinesRef.current) chart.removeSeries(line);
    for (const line of zoneLinesRef.current) chart.removeSeries(line);
    levelLinesRef.current = [];
    zoneLinesRef.current = [];

    for (const level of dayPlan?.key_levels ?? []) {
      const line = chart.addLineSeries({
        color: "#d4a017",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        title: level.label,
      });
      line.setData([
        {
          time: (candles[0]?.time ?? 0) as unknown as import("lightweight-charts").UTCTimestamp,
          value: level.price,
        },
        {
          time: (candles[candles.length - 1]?.time ?? 0) as unknown as import("lightweight-charts").UTCTimestamp,
          value: level.price,
        },
      ]);
      levelLinesRef.current.push(line);
    }

    for (const zone of sessionPlan?.entry_zones ?? []) {
      const [lo, hi] = zone.zone;
      for (const price of [lo, hi]) {
        const line = chart.addLineSeries({
          color: zone.side === "buy" ? "#3b82f6" : "#f97316",
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          title: `${zone.side} zone`,
        });
        line.setData([
          {
            time: (candles[0]?.time ?? 0) as unknown as import("lightweight-charts").UTCTimestamp,
            value: price,
          },
          {
            time: (candles[candles.length - 1]?.time ?? 0) as unknown as import("lightweight-charts").UTCTimestamp,
            value: price,
          },
        ]);
        zoneLinesRef.current.push(line);
      }
    }
  }, [dayPlan, sessionPlan, candles]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    for (const line of ideaLinesRef.current) series.removePriceLine(line);
    ideaLinesRef.current = [];

    const plan = tradeIdea?.execution_plan;
    if (!plan || plan.status !== "ready") return;

    const sideLabel = (plan.side ?? "").toUpperCase();
    const entryColor = plan.side === "buy" ? "#38bdf8" : "#c084fc";

    const addIdeaLine = (
      price: number | undefined,
      title: string,
      color: string,
      lineStyle: LineStyle,
    ) => {
      if (typeof price !== "number" || !Number.isFinite(price)) return;
      ideaLinesRef.current.push(
        series.createPriceLine({
          price,
          color,
          lineWidth: 2,
          lineStyle,
          axisLabelVisible: true,
          title,
        }),
      );
    };

    addIdeaLine(plan.entry_low, `${sideLabel} entry low`, entryColor, LineStyle.Solid);
    addIdeaLine(plan.entry_high, `${sideLabel} entry high`, entryColor, LineStyle.Solid);
    addIdeaLine(plan.stop_loss, "SL", "#ef4444", LineStyle.Dashed);
    addIdeaLine(plan.take_profit, "TP", "#22c55e", LineStyle.Dashed);
  }, [tradeIdea]);

  const ideaPlan =
    tradeIdea?.execution_plan?.status === "ready"
      ? tradeIdea.execution_plan
      : null;

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            Chart · {timeframe}
          </h2>
          {ideaPlan && (
            <span
              className={`rounded px-2 py-0.5 text-xs font-semibold ${
                ideaPlan.side === "buy"
                  ? "bg-sky-500/15 text-sky-300"
                  : "bg-purple-500/15 text-purple-300"
              }`}
            >
              Idea: {ideaPlan.side?.toUpperCase()} {ideaPlan.entry_low}–
              {ideaPlan.entry_high} · SL {ideaPlan.stop_loss} · TP{" "}
              {ideaPlan.take_profit}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          {hourlyUpdates.map((update) => (
            <button
              key={update.hourly_id}
              type="button"
              onClick={() => onSelectHour(update.hourly_id)}
              className={`rounded px-2 py-1 ${
                selectedHourlyId === update.hourly_id
                  ? "ring-1 ring-gold"
                  : "opacity-80 hover:opacity-100"
              }`}
              style={{
                backgroundColor: `${STATUS_COLORS[update.plan_status]}33`,
                color: STATUS_COLORS[update.plan_status],
              }}
            >
              H{update.clock.utc_hour}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="w-full" />
      <p className="text-xs text-slate-500">
        Gold dashed lines = day key levels. Blue/orange bands = session entry zones.
        Labeled price lines = active trade idea (entry zone, SL red, TP green).
        Hour buttons color by plan_status (on_track / drifting / invalidated).
      </p>
    </div>
  );
}
