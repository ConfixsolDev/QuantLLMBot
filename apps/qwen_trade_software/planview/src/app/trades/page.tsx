"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchTradeJournal } from "@/lib/api";
import type { TradeJournalResponse, TradeJournalRow } from "@/lib/tradeJournal";

const money = (value?: number | null) =>
  value == null ? "—" : `${value >= 0 ? "+" : ""}$${value.toFixed(2)}`;
const price = (value?: number | null) => value == null ? "—" : value.toFixed(3);
const when = (value?: string | null) => value ? new Date(value).toLocaleString() : "—";
const duration = (seconds?: number | null) => {
  if (seconds == null) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
};
const reasonText = (reason: TradeJournalRow["loss_reasons"][number]) =>
  typeof reason === "string" ? reason.replaceAll("_", " ") :
    String(reason.code || "Recorded loss factor").replaceAll("_", " ");
const localDateValue = (value = new Date()) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};
const localDayUtcBounds = (date: string) => {
  const [year, month, day] = date.split("-").map(Number);
  const start = new Date(year, month - 1, day);
  const end = new Date(year, month - 1, day + 1);
  return { startUtc: start.toISOString(), endUtc: end.toISOString() };
};
const displayDate = (date: string) => {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-GB", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
};

function Metric({ label, value, tone = "text-slate-100" }: { label: string; value: string; tone?: string }) {
  return <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
    <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
    <div className={`mt-1 font-semibold ${tone}`}>{value}</div>
  </div>;
}

function AnalysisList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return <div>
    <h4 className={`text-xs font-semibold uppercase tracking-wider ${tone}`}>{title}</h4>
    {items.length ? <ul className="mt-2 space-y-1 text-sm text-slate-300">
      {items.map((item, i) => <li key={`${item}-${i}`} className="flex gap-2"><span>•</span><span>{item}</span></li>)}
    </ul> : <p className="mt-2 text-sm text-slate-500">No confirmed item recorded.</p>}
  </div>;
}

function TradeCard({ trade }: { trade: TradeJournalRow }) {
  const [open, setOpen] = useState(false);
  const positive = (trade.net_pnl ?? 0) >= 0;
  const analysis = trade.qwen_analysis;
  const exitLegs = trade.exit_legs || [];
  const partialCloses = exitLegs.filter((leg) => leg.kind === "partial");
  const entryEvidence = trade.entry_evidence || {};
  const selectedZone = entryEvidence.selected_zone || {};
  const trigger = entryEvidence.execution_trigger || {};
  const invalidation = entryEvidence.invalidation || {};
  const target = entryEvidence.target || {};
  const decision = entryEvidence.decision || {};
  return <article className={`overflow-hidden rounded-xl border ${positive ? "border-emerald-900/70" : "border-rose-900/70"} bg-panel/90`}>
    <button type="button" onClick={() => setOpen(!open)} className="grid w-full gap-3 p-4 text-left md:grid-cols-[1.1fr_.7fr_.7fr_.7fr_auto] md:items-center">
      <div>
        <div className="flex items-center gap-2">
          <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${positive ? "bg-emerald-950 text-emerald-300" : "bg-rose-950 text-rose-300"}`}>{trade.result}</span>
          <span className="text-sm font-semibold uppercase text-slate-200">{trade.side} {trade.symbol}</span>
          <span className="text-xs text-slate-500">{trade.structure_timeframe || "—"}</span>
        </div>
        <p className="mt-2 line-clamp-2 text-sm text-slate-300">{trade.idea_summary || trade.idea_reason || "No idea summary recorded"}</p>
        <p className="mt-1 text-xs text-slate-500">Closed {when(trade.exit_time_utc)}</p>
      </div>
      <Metric label="Net result" value={money(trade.net_pnl)} tone={positive ? "text-emerald-300" : "text-rose-300"} />
      <Metric label="Best open P&L" value={money(trade.peak_pnl)} tone="text-sky-300" />
      <Metric label="Profit secured" value={money(trade.secured_cash)} tone={(trade.secured_cash ?? 0) > 0 ? "text-amber-300" : "text-slate-400"} />
      <span className="text-sm text-slate-400">{open ? "Close ↑" : "Analyze ↓"}</span>
    </button>

    {open && <div className="border-t border-slate-800 p-4 md:p-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <Metric label="Entry → exit" value={`${price(trade.entry_price)} → ${price(trade.exit_price)}`} />
        <Metric label="Initial SL / TP" value={`${price(trade.initial_stop)} / ${price(trade.initial_target)}`} />
        <Metric label="MFE / MAE move" value={`${price(trade.mfe_price)} / ${price(trade.mae_price)}`} />
        <Metric label="Giveback move" value={price(trade.giveback_price)} tone={(trade.giveback_price ?? 0) > 0 ? "text-amber-300" : "text-slate-100"} />
        <Metric label="Holding time" value={duration(trade.holding_seconds)} />
        <Metric
          label="Exit legs"
          value={exitLegs.length ? `${exitLegs.length} (${partialCloses.length} partial)` : "1 (legacy)"}
          tone={partialCloses.length ? "text-amber-300" : "text-slate-100"}
        />
      </div>

      {exitLegs.length > 0 && <section className="mt-5 rounded-lg border border-amber-900/50 bg-amber-950/10 p-4">
        <h3 className="font-semibold text-amber-200">Broker exit legs</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500"><tr>
              <th className="py-2 pr-4">Stage</th><th className="py-2 pr-4">Time</th>
              <th className="py-2 pr-4">Volume</th><th className="py-2 pr-4">Price</th>
              <th className="py-2 pr-4">Net P&amp;L</th><th className="py-2">Broker comment</th>
            </tr></thead>
            <tbody>{exitLegs.map((leg, index) => <tr key={`${leg.deal || index}-${leg.kind}`} className="border-t border-slate-800">
              <td className={`py-2 pr-4 font-medium ${leg.kind === "partial" ? "text-amber-300" : "text-emerald-300"}`}>{leg.kind}</td>
              <td className="py-2 pr-4 text-slate-400">{when(leg.closed_at_utc)}</td>
              <td className="py-2 pr-4 text-slate-200">{leg.volume.toFixed(2)}</td>
              <td className="py-2 pr-4 text-slate-200">{price(leg.price)}</td>
              <td className={`py-2 pr-4 ${(leg.net_pnl ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{money(leg.net_pnl)}</td>
              <td className="py-2 text-slate-400">{leg.comment || "—"}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-800 bg-slate-950/45 p-4">
          <h3 className="font-semibold text-slate-100">Recorded facts</h3>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-slate-500">Trade idea</dt><dd className="text-slate-300">{trade.idea_reason || trade.idea_summary || "—"}</dd>
            <dt className="text-slate-500">Geometry</dt><dd className="text-slate-300">{trade.geometry_source || "—"}</dd>
            <dt className="text-slate-500">Exit</dt><dd className="text-slate-300">{trade.exit_reason || "—"}</dd>
            <dt className="text-slate-500">Costs</dt><dd className="text-slate-300">{money(trade.costs)}</dd>
            <dt className="text-slate-500">Secured stop</dt><dd className="text-slate-300">{price(trade.secured_stop)}</dd>
            <dt className="text-slate-500">Confidence</dt><dd className="text-slate-300">{trade.confidence == null ? "—" : `${trade.confidence}%`}</dd>
          </dl>
          {trade.loss_reasons.length > 0 && <div className="mt-4 rounded-lg border border-rose-900/60 bg-rose-950/20 p-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-rose-300">Deterministic loss findings</div>
            <ul className="mt-2 space-y-1 text-sm text-rose-100">{trade.loss_reasons.map((r, i) => <li key={i}>• {reasonText(r)}</li>)}</ul>
          </div>}
        </section>

        <section className="rounded-lg border border-violet-900/60 bg-violet-950/15 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold text-violet-200">Qwen post-trade analysis</h3>
            <span className={`rounded px-2 py-1 text-[11px] uppercase ${trade.qwen_analysis_status === "complete" ? "bg-violet-950 text-violet-300" : "bg-amber-950 text-amber-300"}`}>{trade.qwen_analysis_status}</span>
          </div>
          {analysis ? <div className="mt-3 space-y-4">
            <p className="text-sm leading-6 text-slate-200">{analysis.summary}</p>
            <div><div className="text-xs uppercase tracking-wider text-slate-500">Entry assessment</div><p className="mt-1 text-sm text-slate-300">{analysis.entry_assessment}</p></div>
            <div><div className="text-xs uppercase tracking-wider text-slate-500">Management assessment</div><p className="mt-1 text-sm text-slate-300">{analysis.management_assessment}</p></div>
            <div className="grid gap-4 sm:grid-cols-2"><AnalysisList title="What worked" items={analysis.what_worked} tone="text-emerald-300" /><AnalysisList title="What failed" items={analysis.what_failed} tone="text-rose-300" /></div>
            <div className="rounded border border-gold/30 bg-amber-950/20 p-3"><div className="text-xs uppercase tracking-wider text-amber-300">Lesson</div><p className="mt-1 text-sm text-amber-100">{analysis.lesson}</p></div>
            <div className="text-xs text-slate-500">Qwen confidence {analysis.confidence}% · {trade.qwen_analysis_model || "model not recorded"}</div>
          </div> : <p className="mt-4 text-sm text-amber-200">Facts are already saved. Qwen analysis is queued and will appear automatically.</p>}
        </section>
      </div>
      <section className="mt-5 rounded-lg border border-sky-900/60 bg-sky-950/10 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-sky-200">Structure evidence used for this trade</h3>
          <span className="text-xs text-slate-500">Decision evidence and actual execution trigger are kept separate</span>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="Selected zone band"
            value={`${price(selectedZone.zone_low)}–${price(selectedZone.zone_high)}`}
            tone="text-sky-200"
          />
          <Metric
            label="Zone / owner"
            value={`${selectedZone.low_id || "—"} · ${selectedZone.owning_timeframe || "—"}`}
          />
          <Metric
            label="Invalidation"
            value={`${invalidation.level_id || "—"} · ${price(invalidation.broker_price ?? invalidation.planned_price)}`}
          />
          <Metric
            label="Target"
            value={`${target.level_id || "—"} · ${price(target.broker_price ?? target.planned_price)}`}
          />
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <div className="rounded border border-slate-800 bg-slate-950/45 p-3 text-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Decision claim</div>
            <p className="mt-1 text-slate-200">{decision.reason || trade.idea_reason || "No decision reason recorded"}</p>
            <p className="mt-2 text-xs text-slate-500">
              Regime {decision.regime_hint || "—"} / {decision.regime_state || "—"} · trend {decision.trend_direction || "—"} · decided {when(decision.decision_time_utc)}
            </p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950/45 p-3 text-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Actual closed M1 trigger</div>
            {trigger.evidence_id ? <>
              <p className={`mt-1 font-medium ${trigger.direction === "up" ? "text-emerald-300" : trigger.direction === "down" ? "text-rose-300" : "text-slate-300"}`}>
                {trigger.direction || "—"} · O {price(trigger.open)} H {price(trigger.high)} L {price(trigger.low)} C {price(trigger.close)}
              </p>
              <p className="mt-2 text-xs text-slate-500">{trigger.evidence_id} · gate {trigger.gate || "—"}</p>
            </> : <p className="mt-1 text-amber-300">Actual execution-trigger candle was not recorded by this older trade.</p>}
          </div>
        </div>
        <div className="mt-3 break-all text-xs text-slate-600">
          Evidence IDs: {trade.evidence_ids.length ? trade.evidence_ids.join(" · ") : "none recorded"}
        </div>
      </section>
      <div className="mt-4 text-xs text-slate-600">Proposal {trade.proposal_id} · Execution {trade.execution_id || "—"}</div>
    </div>}
  </article>;
}

export default function TradesPage() {
  const [data, setData] = useState<TradeJournalResponse | null>(null);
  const [filter, setFilter] = useState<"all" | "win" | "loss">("all");
  const [selectedDate, setSelectedDate] = useState(localDateValue);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setData(await fetchTradeJournal({ ...localDayUtcBounds(selectedDate), limit: 1000 }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Journal unavailable");
    }
  }, [selectedDate]);
  useEffect(() => { load(); const timer = setInterval(load, 15000); return () => clearInterval(timer); }, [load]);
  const dateTrades = useMemo(() => (data?.trades || []).filter((trade) => {
    if (!trade.exit_time_utc) return false;
    return localDateValue(new Date(trade.exit_time_utc)) === selectedDate;
  }), [data, selectedDate]);
  const trades = useMemo(() => dateTrades.filter(t => filter === "all" || t.result === filter), [dateTrades, filter]);
  const stats = useMemo(() => {
    const all = dateTrades; const net = all.reduce((n, t) => n + (t.net_pnl || 0), 0);
    const wins = all.filter(t => t.result === "win").length;
    return { count: all.length, net, wins, losses: all.filter(t => t.result === "loss").length, winRate: all.length ? wins / all.length * 100 : 0 };
  }, [dateTrades]);

  return <main className="mx-auto min-h-screen max-w-7xl space-y-5 p-4 md:p-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><div className="text-xs font-semibold uppercase tracking-[.2em] text-gold">Trading memory</div><h1 className="mt-1 text-2xl font-bold">Trade Analysis Journal</h1><p className="mt-1 text-sm text-slate-400">Broker facts, deterministic findings, and asynchronous Qwen review—kept visibly separate.</p></div>
      <nav className="flex gap-2"><Link href="/ideas" className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Trade ideas</Link><Link href="/" className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Chart / plan</Link></nav>
    </header>
    <div className="text-sm text-slate-400">Showing closed trades for <span className="font-medium text-slate-200">{displayDate(selectedDate)}</span></div>
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><Metric label="Closed trades" value={String(stats.count)} /><Metric label="Net P&L" value={money(stats.net)} tone={stats.net >= 0 ? "text-emerald-300" : "text-rose-300"} /><Metric label="Wins" value={String(stats.wins)} tone="text-emerald-300" /><Metric label="Losses" value={String(stats.losses)} tone="text-rose-300" /><Metric label="Win rate" value={`${stats.winRate.toFixed(1)}%`} /></section>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex gap-2">{(["all", "win", "loss"] as const).map(x => <button key={x} onClick={() => setFilter(x)} className={`rounded px-3 py-1.5 text-sm capitalize ${filter === x ? "bg-gold text-ink" : "bg-slate-800 text-slate-300"}`}>{x}</button>)}</div>
      <div className="flex items-center gap-2">
        <input
          type="date"
          value={selectedDate}
          max={localDateValue()}
          onChange={(event) => setSelectedDate(event.target.value || localDateValue())}
          className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 [color-scheme:dark] hover:bg-slate-800"
          aria-label="Select trade date"
          title="Select one trade date"
        />
        <button onClick={load} className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700">Refresh</button>
      </div>
    </div>
    {error && <div className="rounded border border-rose-900 bg-rose-950/30 p-3 text-rose-200">{error}</div>}
    <section className="space-y-3">{trades.map(trade => <TradeCard key={trade.proposal_id} trade={trade} />)}{!error && trades.length === 0 && <div className="card text-center text-slate-400">No closed trades match this date and result filter.</div>}</section>
  </main>;
}
