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
  RuntimeStatus,
  SessionPlan,
  TradeIdea,
  TradeIdeaStack,
  Snapshot,
} from "@/lib/types";
import { SessionRibbon } from "@/components/SessionRibbon";
import { describeLayerStatus } from "@/lib/translate";

const STATUS_COLORS: Record<string, string> = {
  on_track: "#22c55e",
  drifting: "#f59e0b",
  invalidated: "#ef4444",
  pending: "#64748b",
};

interface PlanChartProps {
  candles: Candle[];
  dayPlan: DayPlan | null;
  sessionPlan: SessionPlan | null;
  tradeIdea: TradeIdea | null;
  profitProtection?: Snapshot["profit_protection"];
  tradeIdeaStack: TradeIdeaStack | null;
  hourlyUpdates: HourlyUpdate[];
  selectedHourlyId: string | null;
  onSelectHour: (hourlyId: string) => void;
  timeframe: string;
  runtime?: RuntimeStatus | null;
  onOpenCheat?: () => void;
}

function statusColor(status?: string | null): string {
  return STATUS_COLORS[status || "pending"] || STATUS_COLORS.pending;
}

export function PlanChart({
  candles,
  dayPlan,
  sessionPlan,
  tradeIdea,
  profitProtection,
  tradeIdeaStack,
  hourlyUpdates,
  selectedHourlyId,
  onSelectHour,
  timeframe,
  runtime,
  onOpenCheat,
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

    const t0 = (candles[0]?.time ?? 0) as unknown as import("lightweight-charts").UTCTimestamp;
    const t1 = (candles[candles.length - 1]?.time ?? 0) as unknown as import("lightweight-charts").UTCTimestamp;
    const span = (price: number, color: string, title: string, style: LineStyle, width: 1 | 2 = 1) => {
      const line = chart.addLineSeries({
        color,
        lineWidth: width,
        lineStyle: style,
        title,
      });
      line.setData([
        { time: t0, value: price },
        { time: t1, value: price },
      ]);
      return line;
    };

    const stack = tradeIdeaStack;
    const lv = stack?.layer_validation;

    if (timeframe === "H4" && stack?.h4) {
      const color = statusColor(lv?.h4);
      levelLinesRef.current.push(
        span(stack.h4.invalidation, color, `H4 inv ${stack.h4.side}`, LineStyle.Dashed, 2),
      );
      for (const [idx, target] of stack.h4.targets.entries()) {
        levelLinesRef.current.push(
          span(target, "#d4a017", `H4 TP${idx + 1}`, LineStyle.Dotted, 2),
        );
      }
    } else if (timeframe === "H1") {
      if (stack?.h1) {
        const color = statusColor(lv?.h1);
        levelLinesRef.current.push(
          span(stack.h1.invalidation, color, "H1 inv", LineStyle.Dashed, 2),
        );
        for (const level of stack.h1.levels ?? []) {
          levelLinesRef.current.push(
            span(level.price, "#38bdf8", level.label || "H1", LineStyle.Solid, 1),
          );
        }
      } else {
        for (const level of dayPlan?.key_levels ?? []) {
          levelLinesRef.current.push(
            span(level.price, "#d4a017", level.label, LineStyle.Dashed, 1),
          );
        }
      }
    } else {
      // M15 — pullback idea + session zones fallback
      if (stack?.m15) {
        const color = statusColor(lv?.m15);
        const [lo, hi] = stack.m15.pullback_zone;
        zoneLinesRef.current.push(
          span(Number(lo), color, `M15 zone lo`, LineStyle.Solid, 2),
        );
        zoneLinesRef.current.push(
          span(Number(hi), color, `M15 zone hi`, LineStyle.Solid, 2),
        );
        zoneLinesRef.current.push(
          span(stack.m15.invalidation, "#ef4444", "M15 SL", LineStyle.Dashed, 2),
        );
        zoneLinesRef.current.push(
          span(stack.m15.target, "#22c55e", "M15 TP", LineStyle.Dashed, 2),
        );
      } else {
        for (const zone of sessionPlan?.entry_zones ?? []) {
          const [lo, hi] = zone.zone;
          for (const price of [lo, hi]) {
            zoneLinesRef.current.push(
              span(
                price,
                zone.side === "buy" ? "#3b82f6" : "#f97316",
                `${zone.side} zone`,
                LineStyle.Solid,
                1,
              ),
            );
          }
        }
      }
    }
  }, [dayPlan, sessionPlan, candles, tradeIdeaStack, timeframe]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    for (const line of ideaLinesRef.current) series.removePriceLine(line);
    ideaLinesRef.current = [];

    // Paper execution idea only on M15 as an extra overlay when ready.
    if (timeframe !== "M15") return;
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
    addIdeaLine(plan.stop_loss, "Paper SL", "#ef4444", LineStyle.Dashed);
    addIdeaLine(plan.take_profit, "Paper TP", "#22c55e", LineStyle.Dashed);
  }, [tradeIdea, timeframe]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const lines: IPriceLine[] = [];
    const add = (price: number | null | undefined, title: string, color: string) => {
      if (typeof price !== "number" || !Number.isFinite(price)) return;
      lines.push(series.createPriceLine({
        price, title, color, lineWidth: 2, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
      }));
    };
    if (profitProtection?.ticket) {
      add(profitProtection.entry, "Open entry", "#38bdf8");
      add(profitProtection.peak, "MFE peak", "#a78bfa");
      add(profitProtection.candidate_stop, "Protected floor", "#f59e0b");
    }
    return () => { for (const line of lines) series.removePriceLine(line); };
  }, [profitProtection]);

  const h4 = tradeIdeaStack?.h4;
  const lv = tradeIdeaStack?.layer_validation;
  const selectedHour = hourlyUpdates.find((u) => u.hourly_id === selectedHourlyId);
  const hourLv = selectedHour?.layer_validation;

  const device = runtime?.model_device || "unloaded";
  const deviceTone =
    device === "GPU"
      ? "border-emerald-700 bg-emerald-950/40 text-emerald-300"
      : device === "CPU" || device === "MIXED"
        ? "border-amber-700 bg-amber-950/30 text-amber-200"
        : "border-slate-700 bg-slate-900 text-slate-400";

  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            Chart · {timeframe}
          </h2>
          {profitProtection?.ticket ? (
            <span className="rounded border border-amber-700 bg-amber-950/30 px-2 py-0.5 text-xs font-semibold text-amber-200">
              Protection {profitProtection.state || "watching"} · {Number(profitProtection.progress_r || 0).toFixed(2)}R · locked ${Number(profitProtection.locked_cash || 0).toFixed(2)}
            </span>
          ) : null}
          <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${deviceTone}`}>
            Model on {device}
          </span>
          {h4 && (
            <span className="rounded bg-slate-900 px-2 py-1 text-xs text-amber-200">
              Day H4 rev {h4.revision} · {h4.side.toUpperCase()} ·{" "}
              {describeLayerStatus(h4.status)}
            </span>
          )}
          {tradeIdeaStack?.revisions?.length ? (
            <span className="rounded bg-slate-900 px-2 py-1 text-xs text-violet-300">
              Session revises {tradeIdeaStack.revisions.length}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          {(["h4", "h1", "m15"] as const).map((layer) => {
            const status = hourLv?.[layer] || lv?.[layer] || "pending";
            return (
              <span
                key={layer}
                className="rounded px-2 py-1"
                style={{
                  backgroundColor: `${statusColor(status)}33`,
                  color: statusColor(status),
                }}
              >
                {layer.toUpperCase()} {describeLayerStatus(status)}
              </span>
            );
          })}
        </div>
      </div>

      {/*
        Today's session ribbon.
        Was: every hour ever recorded, labelled H0..H23, coloured by plan
        status — so it ran across several days, repeated hour numbers, and told
        you nothing about how the day was going.
        Now: today only, labelled by session (A=Asia, L=London, O=Overlap,
        N=New York), coloured bull/bear by that hour's own candle.
      */}
      <SessionRibbon
        hourlyUpdates={hourlyUpdates}
        selectedHourlyId={selectedHourlyId}
        onSelectHour={onSelectHour}
      />

      <div className="relative min-w-0 w-full">
        {onOpenCheat ? (
          <button
            type="button"
            onClick={onOpenCheat}
            className="absolute right-3 top-3 z-20 rounded-full bg-amber-400 px-3 py-1.5 text-xs font-bold text-slate-950 shadow-lg hover:bg-amber-300"
          >
            Cheat sheet
          </button>
        ) : null}
        <div ref={containerRef} className="min-w-0 w-full" />
      </div>
      <p className="text-xs text-slate-500">
        H4 = day thesis (inv + targets). H1 = refine levels. M15 = pullback zone + SL/TP.
        Ribbon shows layer validation (hour selection overrides with that hour&apos;s
        layer_validation). Gold/amber = H4, sky = H1, green/red = M15 targets/stops.
      </p>
    </div>
  );
}
