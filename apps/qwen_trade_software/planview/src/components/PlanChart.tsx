"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  IChartApi,
  ISeriesApi,
  LineStyle,
  createChart,
} from "lightweight-charts";
import type {
  Candle,
  DayPlan,
  HourlyUpdate,
  SessionPlan,
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
  hourlyUpdates: HourlyUpdate[];
  selectedHourlyId: string | null;
  onSelectHour: (hourlyId: string) => void;
  timeframe: string;
}

export function PlanChart({
  candles,
  dayPlan,
  sessionPlan,
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

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Chart · {timeframe}
        </h2>
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
        Hour buttons color by plan_status (on_track / drifting / invalidated).
      </p>
    </div>
  );
}
