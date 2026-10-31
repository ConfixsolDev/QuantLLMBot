"use client";

// Candles from the engine plus everything the engine marked on them.
// Candles, swings and event markers use lightweight-charts; boxes (zones,
// order blocks, FVGs, ranges), BOS/CHoCH segments and session levels are drawn
// on a transparent canvas laid over the chart, re-drawn whenever the view moves.

import { useEffect, useRef } from "react";
import {
  ColorType, createChart, type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import type { Chart, Overlays } from "@/lib/api";

export type Layers = Record<"zones" | "ob" | "fvg" | "ranges" | "trend" | "liquidity" | "levels" | "swings" | "other", boolean>;

const C = {
  demand: "34,197,94", supply: "239,68,68", fvgUp: "45,212,191", fvgDown: "251,146,60",
  range: "148,163,184", bos: "#e2e8f0", choch: "#fb923c", level: "#60a5fa", liq: "#22d3ee",
  spike: "#c084fc", pattern: "#facc15", swing: "#94a3b8",
};

export default function StructureChart({ chart, layers, fitKey }: { chart: Chart | null; layers: Layers; fitKey: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const dataRef = useRef<{ ov: Overlays | null; layers: Layers }>({ ov: null, layers });
  const fittedRef = useRef<string>("");

  // ----- draw boxes, lines and levels on the canvas
  const draw = () => {
    const canvas = canvasRef.current, ch = chartRef.current, s = seriesRef.current, box = boxRef.current;
    if (!canvas || !ch || !s || !box) return;
    const dpr = window.devicePixelRatio || 1;
    const w = box.clientWidth, h = box.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
    const g = canvas.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const { ov, layers: L } = dataRef.current;
    if (!ov) return;
    const ts = ch.timeScale();
    const right = w - ch.priceScale("right").width();
    const X = (t: number) => ts.timeToCoordinate(t as UTCTimestamp);
    const Y = (p: number) => s.priceToCoordinate(p);
    g.font = "10px ui-sans-serif, system-ui";
    g.save();
    g.beginPath(); g.rect(0, 0, right, h); g.clip();

    for (const b of ov.boxes) {
      const on = { zone: L.zones, ob: L.ob, fvg: L.fvg, range: L.ranges }[b.kind];
      if (!on) continue;
      const x1 = X(b.t1), x2 = X(b.t2), y1 = Y(b.high), y2 = Y(b.low);
      if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
      const bull = b.side === "demand" || b.side === "up";
      const rgb = b.kind === "range" ? C.range : b.kind === "fvg" ? (bull ? C.fvgUp : C.fvgDown) : bull ? C.demand : C.supply;
      const alpha = (b.kind === "zone" ? 0.16 : b.kind === "ob" ? 0.24 : b.kind === "fvg" ? 0.13 : 0) * (b.alive ? 1 : 0.5);
      const xe = Math.max(x2 + 6, x1 + 2);
      if (alpha > 0) { g.fillStyle = `rgba(${rgb},${alpha})`; g.fillRect(x1, y1, xe - x1, Math.max(1.5, y2 - y1)); }
      if (b.kind === "ob" || b.kind === "range") {
        g.strokeStyle = `rgba(${rgb},${b.alive ? 0.9 : 0.4})`;
        g.setLineDash(b.kind === "range" ? [3, 3] : []);
        g.strokeRect(x1, y1, xe - x1, Math.max(1.5, y2 - y1));
        g.setLineDash([]);
      }
      g.fillStyle = `rgba(${rgb},0.95)`;
      const tag = b.kind === "zone" ? `${b.tf} ${b.side}${b.tests ? ` t${b.tests}` : ""}` : b.kind === "ob" ? `${b.tf} OB` : b.kind === "fvg" ? "FVG" : "range";
      g.fillText(tag, x1 + 2, y1 - 2);
    }
    if (L.levels) {
      for (const lv of ov.levels) {
        const x1 = X(lv.t1), y = Y(lv.price);
        if (x1 === null || y === null) continue;
        g.strokeStyle = lv.confirmed ? C.level : "rgba(96,165,250,0.45)";
        g.setLineDash(lv.confirmed ? [5, 4] : [2, 3]);
        g.beginPath(); g.moveTo(x1, y); g.lineTo(right, y); g.stroke();
        g.setLineDash([]);
        g.fillStyle = g.strokeStyle;
        g.fillText(`${lv.name.slice(0, 3)} ${lv.side === "high" ? "H" : "L"}${lv.confirmed ? "" : " (forming)"}`, x1 + 2, y - 2);
      }
    }
    if (L.trend) {
      for (const ln of ov.lines) {
        const x1 = X(ln.t1), x2 = X(ln.t2), y = Y(ln.price);
        if (x1 === null || x2 === null || y === null) continue;
        const col = ln.kind === "bos" ? C.bos : C.choch;
        g.strokeStyle = col; g.lineWidth = 1.3;
        g.beginPath(); g.moveTo(x1, y); g.lineTo(x2, y); g.stroke();
        g.lineWidth = 1;
        g.fillStyle = col; g.font = "bold 10px ui-sans-serif, system-ui";
        g.fillText(ln.label, (x1 + x2) / 2 - 12, ln.direction === "up" ? y - 3 : y + 11);
        g.font = "10px ui-sans-serif, system-ui";
      }
    }
    if (L.liquidity) {                                   // the swept level, up to the candle
      for (const m of ov.markers) {
        if (m.level === undefined || m.level_t1 === undefined) continue;
        const x1 = X(m.level_t1), x2 = X(m.time), y = Y(m.level);
        if (x1 === null || x2 === null || y === null) continue;
        g.strokeStyle = "rgba(34,211,238,0.6)";
        g.beginPath(); g.moveTo(x1, y); g.lineTo(x2 + 4, y); g.stroke();
      }
    }
    g.restore();
  };

  // ----- create the chart once
  useEffect(() => {
    if (!boxRef.current) return;
    const ch = createChart(boxRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#0b0f17" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "#161e2e" }, horzLines: { color: "#161e2e" } },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
      autoSize: true,
    });
    const s = ch.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444", borderVisible: false, wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    chartRef.current = ch; seriesRef.current = s;
    ch.timeScale().subscribeVisibleLogicalRangeChange(draw);
    const ro = new ResizeObserver(() => requestAnimationFrame(draw));
    ro.observe(boxRef.current);
    return () => { ro.disconnect(); ch.remove(); chartRef.current = null; seriesRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ----- new data or layer change
  useEffect(() => {
    const s = seriesRef.current, ch = chartRef.current;
    if (!s || !ch || !chart) return;
    const rows = [...chart.candles];
    if (chart.forming && (!rows.length || chart.forming.time > rows[rows.length - 1].time)) rows.push(chart.forming);
    s.setData(rows.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })));
    const ov = chart.overlays;
    const markers: SeriesMarker<Time>[] = [];
    if (ov) {
      if (layers.swings)
        for (const sw of ov.swings)
          markers.push({ time: sw.time as UTCTimestamp, position: sw.kind === "high" ? "aboveBar" : "belowBar",
            color: C.swing, shape: sw.kind === "high" ? "arrowDown" : "arrowUp", text: sw.label, size: 0.6 });
      for (const m of ov.markers) {
        const isLiq = m.level !== undefined;
        if ((isLiq && !layers.liquidity) || (!isLiq && !layers.other)) continue;
        markers.push({ time: m.time as UTCTimestamp, position: m.position === "above" ? "aboveBar" : "belowBar",
          color: isLiq ? C.liq : m.kind === "close_spike" ? C.spike : C.pattern, shape: "circle", text: m.text, size: 0.5 });
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    s.setMarkers(markers);
    dataRef.current = { ov, layers };
    // Zoom to the last ~160 candles when the timeframe changes, and again while
    // history is still arriving (the first refresh may hold only a few bars).
    const fitTag = `${fitKey}:${rows.length < 160 ? rows.length : "full"}`;
    if (fittedRef.current !== fitTag && rows.length) {
      ch.timeScale().setVisibleLogicalRange({ from: Math.max(0, rows.length - 160), to: rows.length + 5 });
      fittedRef.current = fitTag;
    }
    requestAnimationFrame(draw);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart, layers, fitKey]);

  return (
    <div className="relative h-full w-full">
      <div ref={boxRef} className="absolute inset-0" />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10" />
    </div>
  );
}
