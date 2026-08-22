"use client";

import type {
  OpportunityBranch,
  OpportunityLocationState,
  OpportunityShadow,
} from "@/lib/types";

const STATE_LABEL: Record<OpportunityLocationState, string> = {
  outside_zone: "Outside zone",
  approaching: "Approaching",
  inside_zone: "Inside zone",
  armed: "Armed — awaiting proof",
  triggered: "Closed proof present",
  invalidated: "Invalidated",
};

function price(value?: number | null): string {
  return value == null || Number.isNaN(value) ? "—" : value.toFixed(3);
}

function stateTone(state: OpportunityLocationState): string {
  if (state === "triggered") return "border-sky-700 bg-sky-950/30 text-sky-200";
  if (state === "armed" || state === "inside_zone") {
    return "border-amber-700 bg-amber-950/25 text-amber-200";
  }
  if (state === "invalidated") return "border-slate-700 bg-slate-950/50 text-slate-500";
  return "border-slate-700 bg-slate-900/50 text-slate-300";
}

function BranchCard({ branch }: { branch: OpportunityBranch }) {
  const buy = branch.side === "buy";
  const zone = branch.zone;
  return (
    <div className={`rounded-lg border p-3 ${stateTone(branch.state)}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`rounded px-2 py-0.5 text-xs font-semibold ${
              buy ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
            }`}
          >
            {buy ? "BUY CASE" : "SELL CASE"}
          </span>
          {branch.committed ? (
            <span className="rounded bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-200">
              QWEN COMMITTED
            </span>
          ) : null}
        </div>
        <span className="text-xs font-medium">{STATE_LABEL[branch.state]}</span>
      </div>

      {zone ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
          <div>
            <div className="text-sm font-medium text-slate-100">
              {zone.zone_id}
            </div>
            <div className="mt-0.5 text-xs text-slate-400">
              {zone.timeframe} · {price(zone.low)}–{price(zone.high)} · distance {price(zone.distance)}
            </div>
          </div>
          <div className="flex items-start gap-1.5 text-[10px]">
            <span className={`rounded px-2 py-1 ${zone.structure_proven ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>
              {zone.structure_proven ? "STRUCTURE PROVEN" : "CANDIDATE"}
            </span>
            <span className="rounded bg-slate-800 px-2 py-1 text-slate-400">
              {zone.lifecycle_status}
            </span>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No bounded active zone on this side.</p>
      )}

      <p className="mt-2 text-xs leading-relaxed text-slate-500">{branch.reason}</p>
    </div>
  );
}

export function OpportunityShadowPanel({
  opportunity,
}: {
  opportunity: OpportunityShadow | null | undefined;
}) {
  const branches = opportunity?.branches;
  const registry = opportunity?.active_zone_registry;
  const commitment = opportunity?.committed_side ?? "wait";

  return (
    <section className="card" aria-labelledby="opportunity-watch-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 id="opportunity-watch-title" className="text-sm font-semibold uppercase tracking-wide text-slate-300">
              Opportunity watch
            </h2>
            <span className="rounded border border-violet-800 bg-violet-950/40 px-2 py-0.5 text-[10px] font-semibold text-violet-200">
              SHADOW · EVIDENCE ONLY
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Both directions are monitored. Only Qwen can commit a side; execution remains disabled here.
          </p>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Qwen commitment</div>
          <div className={`mt-1 text-sm font-semibold ${commitment === "buy" ? "text-emerald-300" : commitment === "sell" ? "text-rose-300" : "text-slate-300"}`}>
            {commitment.toUpperCase()}
          </div>
        </div>
      </div>

      {branches ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <BranchCard branch={branches.buy} />
          <BranchCard branch={branches.sell} />
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-500">
          {opportunity?.reason || "Waiting for the first bounded opportunity snapshot."}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-800 pt-3 text-[11px] text-slate-500">
        <span>raw zones {registry?.raw_zone_count ?? "—"}</span>
        <span>after overlap control {registry?.deduplicated_zone_count ?? "—"}</span>
        <span>shown {registry?.selected_zone_count ?? "—"}</span>
        <span>live price {price(registry?.live_price)}</span>
        <span className="text-violet-300/80">execution authority: no</span>
      </div>
    </section>
  );
}
