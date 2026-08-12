"use client";

import type { PlanBranch, TimeframeLadder as Ladder, TimeframePair } from "@/lib/types";
import { describeEvidence, describeTrigger } from "@/lib/translate";

/**
 * D1 / H4 / H1 / M15, each as its own window with BOTH directions live.
 *
 * The old stack carried one idea per timeframe, so a bullish H1 pullback inside
 * a bearish day could only be expressed as a contradiction — which is how the
 * screen went solid red with INVALIDATED badges on a day the bullish branch
 * reached both its targets.
 *
 * Here nothing is "invalidated" as a headline. Each frame is coloured by which
 * side currently leads and how strongly, so the ladder reads top-down: higher
 * frames give direction, lower frames give the entry, and disagreement between
 * them is a pullback rather than an error.
 */

const STATE_LABEL: Record<string, string> = {
  armed: "armed",
  likely: "likely",
  confirmed: "confirmed",
  spent: "target hit",
  invalidated: "done",
};

function SideBar({ branch, lead }: { branch: PlanBranch; lead: boolean }) {
  const bull = branch.side === "buy";
  const dead = branch.state === "invalidated" || branch.state === "spent";
  const width = Math.max(4, Math.min(100, branch.confidence));

  const fill = bull
    ? dead
      ? "bg-emerald-900/40"
      : "bg-emerald-500/70"
    : dead
      ? "bg-rose-900/40"
      : "bg-rose-500/70";

  return (
    <div className={`flex-1 ${dead ? "opacity-50" : ""}`}>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span
          className={`text-[11px] font-semibold ${
            bull ? "text-emerald-300" : "text-rose-300"
          } ${lead ? "" : "opacity-70"}`}
        >
          {bull ? "BULL" : "BEAR"}
        </span>
        <span className="text-[10px] text-slate-500">
          {STATE_LABEL[branch.state] ?? branch.state}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-slate-800">
        <div className={`h-full ${fill}`} style={{ width: `${width}%` }} />
      </div>
      <div className="mt-1 flex items-baseline justify-between text-[10px] tabular-nums text-slate-500">
        <span>{branch.confidence}</span>
        {branch.invalidation != null ? <span>inv {branch.invalidation.toFixed(2)}</span> : null}
      </div>
    </div>
  );
}

function Frame({ pair }: { pair: TimeframePair }) {
  const side = pair.side;
  const border =
    side === "buy"
      ? "border-emerald-700/50"
      : side === "sell"
        ? "border-rose-700/50"
        : "border-slate-800";

  const leadBranch = side === "buy" ? pair.bull : side === "sell" ? pair.bear : null;
  const trigger = leadBranch?.trigger_text
    ? describeTrigger(leadBranch.trigger_text)
    : null;
  const note = pair.note ? describeEvidence(pair.note) : null;

  return (
    <div className={`rounded-lg border p-3 ${border} bg-slate-900/40`}>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-200">{pair.timeframe}</h3>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
            side === "buy"
              ? "bg-emerald-500/20 text-emerald-300"
              : side === "sell"
                ? "bg-rose-500/20 text-rose-300"
                : "bg-slate-700/50 text-slate-400"
          }`}
        >
          {side ? side.toUpperCase() : "NO LEAN"}
        </span>
      </div>

      <p className="mb-2 text-[10px] leading-snug text-slate-500">{pair.role}</p>

      <div className="flex gap-3">
        <SideBar branch={pair.bull} lead={side === "buy"} />
        <SideBar branch={pair.bear} lead={side === "sell"} />
      </div>

      {trigger ? (
        <p className="mt-2 truncate text-[11px] text-slate-400" title={trigger}>
          {trigger}
        </p>
      ) : null}

      {note ? (
        <p className="mt-1.5 rounded bg-amber-500/10 px-2 py-1 text-[10px] text-amber-300/90">
          {note}
        </p>
      ) : null}
    </div>
  );
}

export function TimeframeLadderPanel({ ladder }: { ladder: Ladder | null | undefined }) {
  if (!ladder?.pairs?.length) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Timeframe ladder
        </h2>
        <p className="mt-2 text-sm text-slate-500">Waiting for plan…</p>
      </div>
    );
  }

  const tone = ladder.aligned
    ? "bg-sky-500/15 text-sky-200 ring-1 ring-sky-500/40"
    : "bg-amber-500/10 text-amber-200 ring-1 ring-amber-500/30";

  return (
    <div className="card">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Timeframe ladder
      </h2>

      <div className={`mb-3 rounded-md px-3 py-2 text-sm font-medium ${tone}`}>
        {ladder.headline}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {ladder.pairs.map((pair) => (
          <Frame key={pair.timeframe} pair={pair} />
        ))}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
        Both directions stay live at every timeframe. Higher frames set
        direction, lower frames give the entry — so a lower frame leaning the
        other way is a pullback, not a conflict. Confidence builds through the
        day as hours close and levels break.
      </p>
    </div>
  );
}
