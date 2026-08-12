"use client";

import type { BranchState, DayBranches, PlanBranch, PriceSanity } from "@/lib/types";
import { describeEvidence, describeTrigger } from "@/lib/translate";

/**
 * The day plan as TWO always-present branches.
 *
 * Replaces the old single-idea view that showed "INVALIDATED" across H4/H1/M15
 * and left you unable to read whether the system was buying or selling.
 *
 * On 2026-08-11 that screen was solid red while the bullish idea reached both
 * its targets — because a session-forecast miss ("expected range compression,
 * observed bullish hour", −30 confidence) cascaded onto every layer. The plan
 * itself now has no status; each branch resolves on its own, and only a CLOSE
 * through a branch's own invalidation can kill it.
 */

const STATE_STYLE: Record<BranchState, { chip: string; card: string; label: string }> = {
  armed: {
    chip: "bg-slate-700/60 text-slate-300",
    card: "border-slate-700/60 bg-slate-900/40",
    label: "ARMED",
  },
  likely: {
    chip: "bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40",
    card: "border-amber-600/50 bg-amber-950/20",
    label: "LIKELY",
  },
  confirmed: {
    chip: "bg-emerald-500/25 text-emerald-200 ring-1 ring-emerald-400/50",
    card: "border-emerald-500/60 bg-emerald-950/30",
    label: "CONFIRMED",
  },
  spent: {
    chip: "bg-sky-500/20 text-sky-200 ring-1 ring-sky-400/40",
    card: "border-sky-700/50 bg-sky-950/20",
    label: "TARGET REACHED",
  },
  invalidated: {
    chip: "bg-rose-500/15 text-rose-300/80",
    card: "border-slate-800 bg-slate-950/60 opacity-60",
    label: "INVALIDATED",
  },
};

function distanceTo(price: number | null | undefined, level: number | null): string {
  if (price == null || level == null) return "—";
  const delta = level - price;
  const sign = delta >= 0 ? "+" : "";
  return `${level.toFixed(2)}  (${sign}${delta.toFixed(2)})`;
}

function BranchCard({
  branch,
  livePrice,
}: {
  branch: PlanBranch;
  livePrice?: number | null;
}) {
  const style = STATE_STYLE[branch.state] ?? STATE_STYLE.armed;
  const isBull = branch.side === "buy";
  const dead = branch.state === "invalidated";
  const trigger = describeTrigger(branch.trigger_text);
  const reason = branch.reason ? describeTrigger(branch.reason) : "";
  const evidence = branch.evidence.map(describeEvidence);

  return (
    <div className={`rounded-lg border p-3 transition-opacity ${style.card}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className={`font-semibold ${isBull ? "text-emerald-300" : "text-rose-300"}`}>
          {isBull ? "BULLISH" : "BEARISH"}
          <span className="ml-2 text-xs font-normal text-slate-500">
            {branch.side.toUpperCase()}
          </span>
        </h3>
        <span className={`rounded px-2 py-0.5 text-[11px] font-semibold ${style.chip}`}>
          {style.label}
        </span>
      </div>

      {reason ? (
        <p className={`mb-2 text-xs ${dead ? "text-slate-500" : "text-slate-300"}`}>
          {reason}
        </p>
      ) : null}

      <dl className="space-y-1.5 text-sm">
        <div>
          <dt className="text-xs text-slate-500">Trigger</dt>
          <dd className="text-slate-200">{trigger}</dd>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <dt className="text-xs text-slate-500">Targets</dt>
            <dd className="tabular-nums text-slate-200">
              {branch.targets.length ? branch.targets.map((t) => t.toFixed(2)).join(" · ") : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Invalidation</dt>
            <dd className="tabular-nums text-slate-200">
              {distanceTo(livePrice, branch.invalidation)}
            </dd>
          </div>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Confidence</dt>
          <dd className="flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded bg-slate-800">
              <div
                className={`h-full ${isBull ? "bg-emerald-500/70" : "bg-rose-500/70"}`}
                style={{ width: `${Math.max(0, Math.min(100, branch.confidence))}%` }}
              />
            </div>
            <span className="w-8 text-right text-xs tabular-nums text-slate-400">
              {branch.confidence}
            </span>
          </dd>
        </div>
        {evidence.length ? (
          <div>
            <dt className="text-xs text-slate-500">Evidence</dt>
            <dd className="text-xs text-slate-400">{evidence.join("; ")}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}

export function DayBranchPanel({
  branches,
  livePrice,
  liveSanity,
  referencePrice,
}: {
  branches: DayBranches | null | undefined;
  livePrice?: number | null;
  liveSanity?: PriceSanity | null;
  referencePrice?: number | null;
}) {
  if (!branches) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Day plan
        </h2>
        <p className="mt-2 text-sm text-slate-500">Waiting for day plan…</p>
      </div>
    );
  }

  const { bullish, bearish, headline, callable_side: callable } = branches;

  const headlineTone =
    callable === "buy"
      ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-500/40"
      : callable === "sell"
        ? "bg-rose-500/15 text-rose-200 ring-1 ring-rose-500/40"
        : "bg-slate-800/70 text-slate-300 ring-1 ring-slate-700";

  return (
    <div className="card">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Day plan
        </h2>
        <div className="text-xs text-slate-500">
          {referencePrice != null ? (
            <span className="tabular-nums">ref {referencePrice.toFixed(2)}</span>
          ) : null}
          {livePrice != null ? (
            <span className="ml-2 tabular-nums text-slate-400">
              live {livePrice.toFixed(2)}
            </span>
          ) : null}
          {liveSanity ? (
            <span
              className={`ml-2 ${liveSanity.ok ? "text-slate-500" : "text-amber-400"}`}
              title={liveSanity.failures?.join("; ")}
            >
              · sanity {liveSanity.ok ? "ok" : (liveSanity.failures?.[0] ?? "failed")}
            </span>
          ) : null}
        </div>
      </div>

      {/* The one line the old screen could not answer: buying, selling, or waiting. */}
      <div className={`mb-3 rounded-md px-3 py-2 text-sm font-medium ${headlineTone}`}>
        {headline}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <BranchCard branch={bullish} livePrice={livePrice} />
        <BranchCard branch={bearish} livePrice={livePrice} />
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
        Both branches stay on screen all day. A branch dies only when price
        <span className="text-slate-500"> closes </span>
        through its own invalidation — a wick through the level is the level
        being tested, not broken. Session-forecast accuracy moves confidence,
        never state.
      </p>
    </div>
  );
}
