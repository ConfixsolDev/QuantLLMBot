"use client";

import type { ExecutionFunnel } from "@/lib/types";

/**
 * Answers "are we trading, and if not why not" — the question the old screen
 * could not answer without opening paper-runner.log.
 *
 * On 2026-08-11 the page showed plans and ideas everywhere while 547 proposals
 * quietly became 2 trades. The drop-off and its causes were invisible.
 */

function Stage({
  stage,
  first,
  previousCount,
}: {
  stage: { name: string; count: number; detail: string };
  first: boolean;
  previousCount: number;
}) {
  const dropped = first ? 0 : Math.max(0, previousCount - stage.count);
  const survived = stage.count > 0;
  const pct = previousCount > 0 ? Math.round((stage.count / previousCount) * 100) : 0;

  return (
    <div className="flex items-center gap-3">
      <div className="w-32 shrink-0 text-xs text-slate-400">{stage.name}</div>
      <div className="flex-1">
        <div className="h-5 overflow-hidden rounded bg-slate-800/70">
          <div
            className={`flex h-full items-center justify-end pr-2 text-[11px] font-medium tabular-nums ${
              survived ? "bg-sky-600/50 text-sky-100" : "bg-slate-700/40 text-slate-500"
            }`}
            style={{ width: `${first ? 100 : Math.max(4, pct)}%` }}
          >
            {stage.count}
          </div>
        </div>
      </div>
      <div className="w-24 shrink-0 text-right text-[11px] tabular-nums text-slate-500">
        {!first && dropped > 0 ? `−${dropped}` : ""}
      </div>
    </div>
  );
}

export function ExecutionFunnelPanel({
  funnel,
}: {
  funnel: ExecutionFunnel | null | undefined;
}) {
  if (!funnel) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Execution
        </h2>
        <p className="mt-2 text-sm text-slate-500">No execution data yet…</p>
      </div>
    );
  }

  const traded = funnel.closed_trades > 0;
  const profitable = (funnel.net_pnl ?? 0) > 0;
  const headlineTone = !traded
    ? "bg-slate-800/70 text-slate-300 ring-1 ring-slate-700"
    : profitable
      ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/40"
      : "bg-rose-500/15 text-rose-200 ring-1 ring-rose-500/40";

  return (
    <div className="card">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Execution
      </h2>

      {/* The one line: trading or not, and why not. */}
      <div className={`mb-3 rounded-md px-3 py-2 text-sm font-medium ${headlineTone}`}>
        {funnel.headline}
      </div>

      <div className="space-y-1.5">
        {funnel.stages.map((stage, i) => (
          <Stage
            key={stage.name}
            stage={stage}
            first={i === 0}
            previousCount={i === 0 ? stage.count : funnel.stages[i - 1].count}
          />
        ))}
      </div>

      {funnel.blockers.length ? (
        <div className="mt-4">
          <h3 className="mb-1.5 text-xs uppercase tracking-wide text-slate-500">
            Where it stopped
          </h3>
          <ul className="space-y-1">
            {funnel.blockers.map((b, i) => (
              <li
                key={`${b.code}-${i}`}
                className="flex items-start gap-2 text-xs"
                title={b.code}
              >
                <span className="mt-px w-10 shrink-0 text-right font-medium tabular-nums text-amber-400">
                  {b.count}×
                </span>
                <span className="text-slate-300">{b.label}</span>
                <span className="ml-auto shrink-0 text-[10px] text-slate-600">
                  {b.stage}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
        Counts are for the current UTC day. A large drop between Proposals and
        Ready means the model is not clearing the confidence bar; a drop between
        Entry attempted and Filled means risk geometry refused the trade.
      </p>
    </div>
  );
}
