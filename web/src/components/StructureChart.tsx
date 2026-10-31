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

export type Layers = Record<"zones" | "ob" | "fvg" | "ranges" | "trend" | "liquidity" | "levels" | "swings" | "other" | "vwap", boolean>;

// VWAP colours per anchor; bands are drawn dashed and fainter
const VWAP_COL: Record<string, string> = { day: "250,204,21", week: "232,121,249", session: "56,189,248" };

const C = {
  demand: "34,197,94", supply: "239,68,68", fvgUp: "45,212,191", fvgDown: "251,146,60",
  range: "148,163,184", bos: "#e2e8f0", choch: "#fb923c", level: "#60a5fa", liq: "#22d3ee",
  spike: "#c084fc", pattern: "#facc15", swing: "#94a3b8", vwap: "#fde047",
};

// `cursor` (replay): the moment the engine is at; candles after it are the
// shaded future. `focus`: a time to scroll into view (clicked detection).
export default function StructureChart({ chart, layers, fitKey, cursor, focus }: {
  chart: Chart | null; layers: Layers; fitKey: string; cursor?: number; focus?: number;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const dataRef = useRef<{ ov: Overlays | null; layers: Layers; cursor?: number; futureFrom?: number }>({ ov: null, layers });
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
    const { ov, layers: L, cursor: cur, futureFrom } = dataRef.current;
    if (!ov) return;
    const ts = ch.timeScale();
    const right = w - ch.priceScale("right").width();
    const X = (t: number) => ts.timeToCoordinate(t as UTCTimestamp);
    const Y = (p: number) => s.priceToCoordinate(p);
    g.font = "10px ui-sans-serif, system-ui";
    g.save();
    g.beginPath(); g.rect(0, 0, right, h); g.clip();

    if (futureFrom !== undefined) {                     // replay: shade the future
      const xf = X(futureFrom);
      if (xf !== null) {
        g.fillStyle = "rgba(15,23,42,0.55)"; g.fillRect(xf - 3, 0, right - xf + 3, h);
        g.strokeStyle = "#fbbf24"; g.setLineDash([4, 3]);
        g.beginPath(); g.moveTo(xf - 3, 0); g.lineTo(xf - 3, h); g.stroke(); g.setLineDash([]);
        g.fillStyle = "#fbbf24";
        g.fillText(cur ? `engine @ ${new Date(cur * 1000).toISOString().slice(11, 16)} UTC` : "now", xf + 2, 12);
      }
    }
    if (L.vwap && ov.curves) {                         // VWAP lines and ±σ bands
      for (const [anchor, pts] of Object.entries(ov.curves)) {
        const rgb = VWAP_COL[anchor] ?? "203,213,225";
        const path = (val: (p: (typeof pts)[number]) => number | null | undefined, style: string, dash: number[]) => {
          g.strokeStyle = style; g.setLineDash(dash); g.beginPath();
          let pen = false, lastStart: number | undefined;
          for (const p of pts) {
            const v = val(p), x = X(p.time);
            if (p.start !== lastStart) pen = false;     // a new period starts: no joining line
            lastStart = p.start;
            if (v === null || v === undefined || x === null) { pen = false; continue; }
            const y = Y(v);
            if (y === null) { pen = false; continue; }
            if (pen) g.lineTo(x, y); else g.moveTo(x, y);
            pen = true;
          }
          g.stroke(); g.setLineDash([]);
        };
        path((p) => p.vwap, `rgba(${rgb},0.95)`, []);
        for (const k of ["1.0", "2.0"]) {
          path((p) => p.bands?.[k]?.[0], `rgba(${rgb},${k === "1.0" ? 0.3 : 0.55})`, [2, 3]);
          path((p) => p.bands?.[k]?.[1], `rgba(${rgb},${k === "1.0" ? 0.3 : 0.55})`, [2, 3]);
        }
        const last = [...pts].reverse().find((p) => p.vwap !== null);
        if (last && last.vwap !== null) {
          const y = Y(last.vwap), x = X(last.time);
          if (y !== null && x !== null) { g.fillStyle = `rgba(${rgb},1)`; g.fillText(`VWAP ${anchor}`, x + 4, y - 3); }
        }
      }
    }

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
    const future = chart.future ?? [];
    s.setData([
      ...rows.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })),
      ...future.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close,
        color: c.close >= c.open ? "rgba(34,197,94,0.28)" : "rgba(239,68,68,0.28)",
        wickColor: "rgba(148,163,184,0.3)" })),
    ]);
    const ov = chart.overlays;
    const markers: SeriesMarker<Time>[] = [];
    if (ov) {
      if (layers.swings)
        for (const sw of ov.swings)
          markers.push({ time: sw.time as UTCTimestamp, position: sw.kind === "high" ? "aboveBar" : "belowBar",
            color: C.swing, shape: sw.kind === "high" ? "arrowDown" : "arrowUp", text: sw.label, size: 0.6 });
      for (const m of ov.markers) {
        const isLiq = m.level !== undefined;
        const isVwap = m.kind.startsWith("vwap");
        if ((isLiq && !layers.liquidity) || (isVwap && !layers.vwap) || (!isLiq && !isVwap && !layers.other)) continue;
        markers.push({ time: m.time as UTCTimestamp, position: m.position === "above" ? "aboveBar" : "belowBar",
          color: isVwap ? C.vwap : isLiq ? C.liq : m.kind === "close_spike" ? C.spike : C.pattern,
          shape: isVwap ? "square" : "circle", text: m.text, size: isVwap ? 0.4 : 0.7 });
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    s.setMarkers(markers);
    dataRef.current = { ov, layers, cursor, futureFrom: future.length ? future[0].time : undefined };
    // Zoom to the last ~160 candles when the timeframe changes, and again while
    // history is still arriving (the first refresh may hold only a few bars).
    const fitTag = `${fitKey}:${rows.length < 160 ? rows.length : "full"}`;
    if (fittedRef.current !== fitTag && rows.length) {
      const extra = Math.min(future.length, 40);
      ch.timeScale().setVisibleLogicalRange({ from: Math.max(0, rows.length - 160), to: rows.length + extra + 5 });
      fittedRef.current = fitTag;
    }
    requestAnimationFrame(draw);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart, layers, fitKey, cursor]);

  // ----- scroll a clicked detection into view
  useEffect(() => {
    const ch = chartRef.current;
    if (!ch || !focus || !chart) return;
    const all = [...chart.candles, ...(chart.future ?? [])];
    let i = all.findIndex((c) => c.time >= focus);
    if (i < 0) i = all.length - 1;
    const r = ch.timeScale().getVisibleLogicalRange();
    const half = r ? Math.max(30, (r.to - r.from) / 2) : 80;
    ch.timeScale().setVisibleLogicalRange({ from: i - half, to: i + half });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  return (
    <div className="relative h-full w-full">
      <div ref={boxRef} className="absolute inset-0" />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10" />
    </div>
  );
}
