import type { PlannerState, Snapshot } from "@/lib/types";
import { STRATEGY_CATALOG } from "@/lib/strategies";

function Status({ label, ok }: { label: string; ok?: boolean }) {
  return <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
    <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
    <div className={ok ? "mt-1 text-emerald-300" : "mt-1 text-amber-300"}>{ok ? "Online" : "Unavailable / paused"}</div>
  </div>;
}

export function SystemOverview({ plan, snapshot }: { plan: PlannerState | null; snapshot: Snapshot | null }) {
  const runtime = plan?.runtime_status;
  const graph = snapshot?.market_intelligence?.graph_health;
  return <section className="card">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><div className="text-xs font-semibold uppercase tracking-[.2em] text-gold">System control plane</div><h2 className="mt-1 text-xl font-semibold">Overall system state</h2><p className="mt-1 text-sm text-slate-400">Strategy-independent health and data availability. No trade authorization is implied by this page.</p></div>
      <span className="badge bg-amber-950/70 text-amber-300">NO-TRADE / TESTING</span>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Status label="Planner" ok={runtime?.planner_alive ?? plan?.planner_alive} />
      <Status label="MT5 read-only" ok={runtime?.mt5_connected ?? plan?.mt5_connected} />
      <Status label="Model" ok={runtime?.model_resident ?? plan?.model_resident} />
      <Status label="Graph projection" ok={graph?.status === "healthy" || graph?.status === "ok"} />
      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"><div className="text-[11px] uppercase tracking-wider text-slate-500">Registered strategies</div><div className="mt-1 font-semibold text-slate-100">{STRATEGY_CATALOG.length}</div></div>
    </div>
  </section>;
}
