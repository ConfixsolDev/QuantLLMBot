"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchTradeIdeas } from "@/lib/api";
import { AppNav } from "@/components/AppNav";
import { STRATEGY_CATALOG, strategyLabel } from "@/lib/strategies";
import type { TradeIdeasResponse } from "@/lib/tradeIdeas";

export default function StrategiesPage() {
  const [ideas, setIdeas] = useState<TradeIdeasResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchTradeIdeas({ days: 14, limit: 300, minConfidence: 0 }).then(setIdeas).catch((e) => setError(e instanceof Error ? e.message : "Trade ideas unavailable")); }, []);
  const unassigned = useMemo(() => ideas?.ideas.filter((idea) => !((idea as typeof idea & { strategy_id?: string }).strategy_id)) ?? [], [ideas]);
  return <main className="mx-auto min-h-screen max-w-7xl space-y-5 p-4 md:p-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><div className="text-xs font-semibold uppercase tracking-[.2em] text-gold">Strategy workspace</div><h1 className="mt-1 text-2xl font-bold">Strategies &amp; trade ideas</h1><p className="mt-1 text-sm text-slate-400">Each strategy owns its identity, explanation, entry contract, and future performance attribution.</p></div><AppNav /></header>
    {error && <div className="rounded border border-rose-900 bg-rose-950/30 p-3 text-rose-200">{error}</div>}
    <div className="grid gap-4 lg:grid-cols-2">{STRATEGY_CATALOG.map((strategy) => <article key={strategy.strategy_id} className="card">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold text-slate-100">{strategy.strategy_id}</h2><p className="mt-1 text-xs text-slate-500">v{strategy.version} · {strategy.pair} · magic {strategy.magic_number} · {strategy.trade_class}</p></div><span className="badge bg-amber-950 text-amber-300">{strategy.status}</span></div>
      <p className="mt-4 text-sm leading-6 text-slate-300">{strategy.explanation}</p>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-slate-500">Context</dt><dd className="text-slate-200">{strategy.context_timeframes.join(" · ")}</dd></div><div><dt className="text-slate-500">Setup → execution</dt><dd className="text-slate-200">{strategy.setup_timeframes.join(" · ")} → {strategy.execution_timeframes.join(" · ")}</dd></div><div><dt className="text-slate-500">Excluded</dt><dd className="text-slate-200">{strategy.excluded_timeframes.join(" · ")}</dd></div><div><dt className="text-slate-500">Trade comment</dt><dd className="text-slate-200">QVN:XAU:M15M1:50</dd></div></dl>
      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3"><div className="text-xs uppercase tracking-wider text-slate-500">Deterministic management</div><div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-300">{Object.entries(strategy.management).map(([key, value]) => <div key={key}><span className="text-slate-500">{key.replaceAll("_", " ")}</span><span className="ml-2 text-slate-100">{value}</span></div>)}</div></div>
      <Link href={`/ideas?strategy=${encodeURIComponent(strategy.strategy_id)}`} className="mt-4 inline-block rounded bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700">View strategy ideas</Link>
    </article>)}</div>
    <section className="card"><h2 className="font-semibold text-slate-100">Current feed attribution</h2><p className="mt-1 text-sm text-slate-400">{unassigned.length} of {ideas?.count ?? 0} returned idea records do not carry a strategy identity and are shown as legacy/unassigned. They are not attributed to the new strategy.</p><p className="mt-3 text-xs text-slate-500">The first strategy remains inactive until its complete shared evidence contract is emitted.</p></section>
  </main>;
}
