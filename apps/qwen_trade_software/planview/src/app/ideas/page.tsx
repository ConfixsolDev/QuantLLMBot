"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchLifecycle, fetchSnapshot, fetchTradeIdeas } from "@/lib/api";
import {
  LOW_CONFIDENCE_FLOOR,
  useHideLowConfidence,
} from "@/lib/hideLowConfidence";
import type { LifecycleResponse, TradeIdeaRow, TradeIdeasResponse } from "@/lib/tradeIdeas";
import type { Snapshot } from "@/lib/types";
import { describeTrigger, levelName } from "@/lib/translate";
import { AppNav } from "@/components/AppNav";

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function fmtLocalSystemTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function fmtUtcTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace(".000Z", "Z").replace(/\.\d{3}Z$/, "Z");
}

function SideBadge({ side }: { side?: string | null }) {
  const s = (side || "").toLowerCase();
  const tone =
    s === "buy"
      ? "bg-emerald-950/50 text-emerald-300 border-emerald-800"
      : s === "sell"
        ? "bg-rose-950/40 text-rose-300 border-rose-900"
        : "bg-slate-900 text-slate-400 border-slate-700";
  return (
    <span className={`rounded border px-2 py-0.5 text-xs uppercase ${tone}`}>
      {s || "—"}
    </span>
  );
}

function OutcomeCell({ row }: { row: TradeIdeaRow }) {
  const outcome = row.outcome;
  if (row.blocked_by_geometry) {
    return (
      <div>
        <div className="font-medium text-amber-300">Geometry blocked</div>
        <div className="text-xs text-amber-200/80">
          {row.geometry_block_detail || outcome?.reason || "reward/risk gate"}
        </div>
      </div>
    );
  }
  if (!outcome) {
    return <span className="text-slate-500">No execution yet</span>;
  }
  if (outcome.event === "mt5_execution_closed") {
    const pnl = outcome.net_pnl;
    const tone =
      pnl == null ? "text-slate-300" : pnl >= 0 ? "text-emerald-300" : "text-rose-300";
    return (
      <div>
        <div className={`font-medium ${tone}`}>
          Closed {pnl == null ? "" : `(${pnl >= 0 ? "+" : ""}${fmt(pnl, 2)})`}
        </div>
        <div className="text-xs text-slate-400">{outcome.reason || "closed"}</div>
      </div>
    );
  }
  if (outcome.event === "mt5_fill") {
    return (
      <div>
        <div className="font-medium text-sky-300">Taken / open</div>
        <div className="text-xs text-slate-400">
          entry {fmt(outcome.average_entry, 3)}
        </div>
      </div>
    );
  }
  if (outcome.event === "mt5_execution_started") {
    return (
      <div>
        <div className="font-medium text-violet-300">Watching entry — not filled</div>
        <div className="text-xs text-slate-400">executor started; broker position not confirmed</div>
      </div>
    );
  }
  if (outcome.event === "mt5_execution_skipped") {
    return (
      <div>
        <div className="font-medium text-amber-300">Skipped</div>
        <div className="text-xs text-amber-200/80">
          {outcome.detail || outcome.reason || "skipped"}
        </div>
      </div>
    );
  }
  return (
    <span className="text-slate-400">{outcome.event || "—"}</span>
  );
}

export default function TradeIdeasPage() {
  const [data, setData] = useState<TradeIdeasResponse | null>(null);
  const [lifecycle, setLifecycle] = useState<LifecycleResponse | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [readyOnly, setReadyOnly] = useState(false);
  const [geometryOnly, setGeometryOnly] = useState(false);
  const [symbol, setSymbol] = useState("XAUUSDr");
  const [symbolDraft, setSymbolDraft] = useState("XAUUSDr");
  const { hideLowConfidence, setHideLowConfidence } = useHideLowConfidence();
  const minConfidence = hideLowConfidence ? LOW_CONFIDENCE_FLOOR : -1;

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("symbol");
    if (requested) {
      setSymbol(requested);
      setSymbolDraft(requested);
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        fetchTradeIdeas({ minConfidence, days: 2, readyOnly, limit: 400, symbol }),
        fetchLifecycle(symbol),
        fetchSnapshot(symbol),
      ]);
      if (results[0].status === "fulfilled") setData(results[0].value);
      if (results[1].status === "fulfilled") setLifecycle(results[1].value);
      if (results[2].status === "fulfilled") setSnapshot(results[2].value);
      const failures = results
        .filter((result): result is PromiseRejectedResult => result.status === "rejected")
        .map((result) => result.reason instanceof Error ? result.reason.message : String(result.reason));
      setError(failures.length ? failures.join(" · ") : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trade ideas");
    }
  }, [minConfidence, readyOnly, symbol]);

  const applySymbol = useCallback(() => {
    const next = symbolDraft.trim() || "XAUUSDr";
    const url = new URL(window.location.href);
    url.searchParams.set("symbol", next);
    window.history.replaceState({}, "", url);
    setData(null);
    setLifecycle(null);
    setSnapshot(null);
    setSymbol(next);
  }, [symbolDraft]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 20000);
    return () => clearInterval(timer);
  }, [load]);

  const rows = useMemo(() => {
    const ideas = data?.ideas ?? [];
    if (!geometryOnly) return ideas;
    return ideas.filter(
      (row) => row.blocked_by_geometry || Boolean(row.geometry?.rr_issue),
    );
  }, [data, geometryOnly]);

  return (
    <main className="mx-auto min-h-screen max-w-[1400px] space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
            GoldFlow Plan View
          </p>
          <h1 className="text-2xl font-semibold text-slate-100">
            Trade ideas
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            {hideLowConfidence
              ? `Hiding plans at or below ${LOW_CONFIDENCE_FLOOR}% confidence. Uncheck the box at the top to include 0-confidence plans.`
              : "Including 0-confidence plans. Check the box at the top to hide them again."}
          </p>
        </div>
        <AppNav />
      </header>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2 text-slate-300">
          Instrument
          <input
            aria-label="Instrument symbol"
            value={symbolDraft}
            onChange={(e) => setSymbolDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") applySymbol(); }}
            className="w-32 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
          />
        </label>
        <button
          type="button"
          onClick={applySymbol}
          className="rounded bg-sky-900 px-3 py-1 text-sky-100 hover:bg-sky-800"
        >
          Load instrument
        </button>
        <label className="flex items-center gap-2 font-medium text-slate-200">
          <input
            type="checkbox"
            checked={hideLowConfidence}
            onChange={(e) => setHideLowConfidence(e.target.checked)}
          />
          Hide low confidence (≤{LOW_CONFIDENCE_FLOOR}%)
        </label>
        <label className="flex items-center gap-2 text-slate-300">
          <input
            type="checkbox"
            checked={readyOnly}
            onChange={(e) => setReadyOnly(e.target.checked)}
          />
          Ready only
        </label>
        <label className="flex items-center gap-2 text-slate-300">
          <input
            type="checkbox"
            checked={geometryOnly}
            onChange={(e) => setGeometryOnly(e.target.checked)}
          />
          Geometry / R:R issues only
        </label>
        <button
          type="button"
          onClick={load}
          className="rounded bg-slate-800 px-3 py-1 text-slate-200 hover:bg-slate-700"
        >
          Refresh
        </button>
        {data && (
          <span className="text-xs text-slate-500">
            showing {rows.length} / {data.count} · ready {data.ready_count} ·
            geometry-blocked {data.geometry_blocked_count}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          {error} — restart the reviewer if `/trade-ideas` is 404 (new endpoint).
        </div>
      )}

      <section className="grid gap-3 md:grid-cols-5" aria-label="Live trade workflow">
        <div className="card p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">1 · Context</div>
          <div className="mt-2 text-lg font-semibold text-slate-100">
            {snapshot?.connected ? "Live" : "Disconnected"} · {fmt(snapshot?.price, 3)}
          </div>
          <div className="text-xs text-slate-400">{snapshot?.symbol || symbol} broker quote</div>
        </div>
        <div className="card p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">2 · Zone memory</div>
          <div className="mt-2 flex items-center gap-2">
            <SideBadge side={lifecycle?.active_idea?.watching_side} />
            <span className="font-medium text-slate-100">
              {lifecycle?.active_idea?.watching_zone || "No active zone"}
            </span>
          </div>
          <div className="mt-1 text-xs text-slate-400">
            {lifecycle?.active_idea?.active_idea?.zone?.map((n) => fmt(n, 3)).join(" – ") || "—"}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">3 · Entry search</div>
          <div className="mt-2 text-lg font-semibold text-slate-100">
            {lifecycle?.active_idea?.state || "idle"}
          </div>
          <div className="text-xs text-slate-400">
            {lifecycle?.approach?.assessment || "no approach"} · {lifecycle?.approach?.distance_trend || "—"} · distance {fmt(lifecycle?.approach?.current_distance, 3)}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">4 · Current trade</div>
          <div className={`mt-2 text-lg font-semibold ${(snapshot?.positions?.length || 0) > 0 ? "text-sky-300" : "text-emerald-300"}`}>
            {(snapshot?.positions?.length || 0) > 0
              ? `${snapshot?.positions?.length} open position(s)`
              : "No open position"}
          </div>
          <div className="text-xs text-slate-400">
            last executor: {snapshot?.paper_execution?.event || "—"} · {snapshot?.paper_execution?.reason || "—"}
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">5 · Profit protection</div>
          <div className={`mt-2 text-lg font-semibold ${snapshot?.profit_protection?.armed ? "text-amber-300" : "text-slate-300"}`}>
            {snapshot?.profit_protection?.state || "Not armed"}
          </div>
          <div className="text-xs text-slate-400">
            floor {fmt(snapshot?.profit_protection?.candidate_stop, 3)} · {fmt(snapshot?.profit_protection?.progress_r, 2)}R · locked ${fmt(snapshot?.profit_protection?.locked_cash, 2)}
          </div>
        </div>
      </section>

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-800 bg-slate-950/80 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-3">System time (planned)</th>
              <th className="px-3 py-3">Side</th>
              <th className="px-3 py-3">Conf</th>
              <th className="px-3 py-3">Status</th>
              <th className="px-3 py-3">Idea</th>
              <th className="px-3 py-3">Zone / levels</th>
              <th className="px-3 py-3">Stop / Target</th>
              <th className="px-3 py-3">R:R</th>
              <th className="px-3 py-3">Frame mins</th>
              <th className="px-3 py-3">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const g = row.geometry || {};
              const rr =
                g.structural_reward_risk ?? g.plan_reward_risk ?? null;
              const highlight = row.blocked_by_geometry || Boolean(g.rr_issue);
              return (
                <tr
                  key={row.proposal_id}
                  className={`border-b border-slate-800/80 ${
                    highlight
                      ? "bg-amber-950/20"
                      : row.confidence <= LOW_CONFIDENCE_FLOOR
                        ? "bg-slate-950/40 text-slate-400"
                        : "hover:bg-slate-900/50"
                  }`}
                >
                  <td className="whitespace-nowrap px-3 py-3 align-top text-xs">
                    <div className="font-medium text-slate-100">
                      {fmtLocalSystemTime(row.created_at_utc)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-500">
                      local system
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-slate-500">
                      UTC {fmtUtcTime(row.created_at_utc)}
                    </div>
                    {row.outcome?.created_at_utc && (
                      <div className="mt-1 text-[10px] text-sky-400/90">
                        exec {fmtLocalSystemTime(row.outcome.created_at_utc)}
                      </div>
                    )}
                    <div className="mt-1 font-mono text-[10px] text-slate-600">
                      {row.proposal_id}
                    </div>
                  </td>
                  <td className="px-3 py-3 align-top">
                    <SideBadge side={row.side || row.bias} />
                  </td>
                  <td className="px-3 py-3 align-top font-semibold text-slate-100">
                    {fmt(row.confidence, 0)}
                  </td>
                  <td className="px-3 py-3 align-top">
                    <div className="text-slate-200">{row.status || "—"}</div>
                    <div className="max-w-[12rem] text-xs text-slate-500">
                      {describeTrigger(row.plan_reason)}
                    </div>
                  </td>
                  <td className="px-3 py-3 align-top">
                    <div className="max-w-[18rem] text-slate-200">
                      {row.summary || "—"}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      spot {fmt(row.price, 3)}
                    </div>
                  </td>
                  <td className="px-3 py-3 align-top text-xs text-slate-300">
                    <div>
                      {levelName(row.entry_low_id)} → {levelName(row.entry_high_id)}
                    </div>
                    <div className="text-slate-500">
                      {fmt(g.entry_low, 3)} – {fmt(g.entry_high, 3)}
                    </div>
                    <div className="mt-1 text-slate-500">
                      SL {levelName(row.stop_level_id)} · TP{" "}
                      {levelName(row.target_level_id)}
                    </div>
                  </td>
                  <td className="px-3 py-3 align-top text-xs text-slate-300">
                    <div>
                      plan Δ {fmt(g.stop_distance)} / {fmt(g.target_distance)}
                    </div>
                    <div>
                      struct Δ {fmt(g.structural_stop_distance)} /{" "}
                      {fmt(g.structural_target_distance)}
                    </div>
                    <div className="text-slate-500">
                      TF {g.structure_timeframe || "—"} ·{" "}
                      {g.geometry_source || "—"}
                    </div>
                  </td>
                  <td className="px-3 py-3 align-top">
                    <div
                      className={
                        rr != null && rr < 1.2
                          ? "font-semibold text-amber-300"
                          : "font-semibold text-slate-100"
                      }
                    >
                      {rr == null ? "—" : `${fmt(rr, 2)} : 1`}
                    </div>
                    {g.rr_issue && (
                      <div className="mt-1 max-w-[12rem] text-xs text-amber-200/90">
                        {g.rr_issue}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 align-top text-xs text-slate-400">
                    min SL {fmt(g.frame_min_stop, 1)}
                    <br />
                    min TP {fmt(g.frame_min_target, 1)}
                  </td>
                  <td className="px-3 py-3 align-top">
                    <OutcomeCell row={row} />
                  </td>
                </tr>
              );
            })}
            {!rows.length && !error && (
              <tr>
                <td
                  colSpan={10}
                  className="px-3 py-8 text-center text-slate-500"
                >
                  No ideas yet for the selected filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
