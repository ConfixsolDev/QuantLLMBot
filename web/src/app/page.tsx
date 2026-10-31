"use client";

// QuantLLM — live market structure. One page: status bar, timeframe and layer
// switches, the chart with every marking, and the side panel. Refreshes every
// 5 seconds from the backend (python -m quantllm serve).

import { useCallback, useEffect, useState } from "react";
import SidePanel from "@/components/SidePanel";
import StructureChart, { type Layers } from "@/components/StructureChart";
import { fetchChart, fetchHealth, fetchSnapshot, fmtTime, type Chart, type Health, type Snapshot } from "@/lib/api";

const TFS = ["M1", "M5", "M15", "M30", "H1", "H4"];
const LAYER_NAMES: [keyof Layers, string][] = [
  ["trend", "BOS / CHoCH"], ["liquidity", "Liquidity"], ["zones", "Zones"], ["ob", "Order blocks"],
  ["fvg", "FVG"], ["ranges", "Ranges"], ["levels", "Session levels"], ["swings", "Swings"], ["other", "Spikes & patterns"],
];

export default function Page() {
  const [tf, setTf] = useState("M15");
  const [layers, setLayers] = useState<Layers>({
    trend: true, liquidity: true, zones: true, ob: true, fvg: false, ranges: true, levels: true, swings: true, other: true,
  });
  const [chart, setChart] = useState<Chart | null>(null);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const [h, c, s] = await Promise.all([fetchHealth(), fetchChart(tf, 400), fetchSnapshot()]);
      setHealth(h); setChart(c); setSnap(s); setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [tf]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const state = health?.state ?? "connecting";
  const stateTone = state === "live" ? "bg-emerald-900/60 text-emerald-300"
    : state === "offline" ? "bg-amber-900/60 text-amber-300" : "bg-sky-900/60 text-sky-300";

  return (
    <main className="flex h-screen flex-col gap-3 p-3">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold text-gold">QuantLLM · Market structure</h1>
        <span className={`badge ${stateTone}`}>{state}{health && state !== "live" && health.progress < 1 ? ` ${Math.round(health.progress * 100)}%` : ""}</span>
        <span className="text-sm text-slate-300">{health?.symbol} {snap?.price ? snap.price.toFixed(2) : ""}</span>
        <span className="text-xs text-slate-500">last bar {fmtTime(health?.last_bar)} · MT5 {health?.mt5} · {health?.database ?? ""}</span>
        {health?.message && <span className="text-xs text-slate-400">{health.message}</span>}
        {error && <span className="text-xs text-rose-400">backend not reachable: {error}</span>}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {TFS.map((t) => (
          <button key={t} onClick={() => setTf(t)}
            className={`rounded-md px-3 py-1 text-sm ${t === tf ? "bg-gold text-ink" : "bg-panel text-slate-300 hover:bg-slate-800"}`}>
            {t}
          </button>
        ))}
        <span className="mx-2 h-5 w-px bg-slate-700" />
        {LAYER_NAMES.map(([k, label]) => (
          <label key={k} className="flex cursor-pointer items-center gap-1 text-xs text-slate-300">
            <input type="checkbox" checked={layers[k]} onChange={() => setLayers({ ...layers, [k]: !layers[k] })} />
            {label}
          </label>
        ))}
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        <div className="card min-w-0 flex-1 p-1">
          <StructureChart chart={chart} layers={layers} fitKey={tf} />
        </div>
        <aside className="w-[340px] shrink-0 overflow-y-auto xl:w-[380px]">
          <SidePanel snap={snap} />
        </aside>
      </div>
      <div className="text-xs text-slate-500">
        Labels: <span className="text-cyan-300">SW</span> sweep · <span className="text-cyan-300">SW✗</span> sweep failed ·{" "}
        <span className="text-cyan-300">FB</span> false break · <span className="text-cyan-300">TK</span> liquidity taken ·{" "}
        <span className="text-yellow-300">DT/DB/TT/TB</span> double/triple top/bottom · HH/HL/LH/LL swings ·
        boxes: zones (fill), order blocks (outlined), FVG (light), ranges (dashed)
      </div>
      <footer className="text-xs text-slate-500">
        config {health?.config_id} · {health?.config_hash} · {health?.bars_processed ?? 0} M1 bars processed · {health?.events ?? 0} events
      </footer>
    </main>
  );
}
