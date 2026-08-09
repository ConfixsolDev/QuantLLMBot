"use client";

import type { TradeIdeaStack } from "@/lib/types";
import { SESSION_LABELS } from "@/lib/types";

const STATUS_TONE: Record<string, string> = {
  on_track: "text-emerald-400",
  drifting: "text-amber-400",
  invalidated: "text-rose-400",
  pending: "text-slate-400",
  active: "text-sky-300",
  revised: "text-violet-300",
};

export function TradeIdeaStackPanel({
  stack,
}: {
  stack: TradeIdeaStack | null | undefined;
}) {
  if (!stack?.h4) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Trade idea stack
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Waiting for H4 day idea… Session open will refine H1 and M15 pullback.
        </p>
      </div>
    );
  }

  const lv = stack.layer_validation || { h4: "pending", h1: "pending", m15: "pending" };
  const latestRev = stack.revisions?.[stack.revisions.length - 1];

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Trade idea stack · {stack.day_idea_id ?? "day"}
        </h2>
        <div className="flex flex-wrap gap-2 text-xs">
          {(["h4", "h1", "m15"] as const).map((layer) => (
            <span key={layer} className={`rounded bg-slate-900 px-2 py-1 ${STATUS_TONE[lv[layer]] || ""}`}>
              {layer.toUpperCase()} {lv[layer]}
            </span>
          ))}
        </div>
      </div>

      <section className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-300">
          H4 day idea · rev {stack.h4.revision} · {stack.h4.status}
        </h3>
        <p className="mt-1 text-sm text-slate-200">
          <span className="font-semibold uppercase text-amber-200">{stack.h4.side}</span>
          {" — "}
          {stack.h4.thesis}
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Inv {stack.h4.invalidation.toFixed(2)} · Targets{" "}
          {stack.h4.targets.map((t) => t.toFixed(2)).join(" · ") || "—"}
          {stack.h4.key_level_refs?.length
            ? ` · Refs ${stack.h4.key_level_refs.join(", ")}`
            : ""}
        </p>
      </section>

      <section className="rounded-lg border border-sky-900/40 bg-sky-950/20 p-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-sky-300">
          H1 refine · {stack.h1?.status ?? "pending"}
        </h3>
        {stack.h1 ? (
          <>
            <p className="mt-1 text-sm text-slate-200">{stack.h1.summary}</p>
            <p className="mt-1 text-xs text-slate-400">
              Inv {stack.h1.invalidation.toFixed(2)}
              {stack.h1.levels?.length
                ? ` · Levels ${stack.h1.levels
                    .map((l) => `${l.label}@${l.price.toFixed(2)}`)
                    .join(", ")}`
                : ""}
            </p>
          </>
        ) : (
          <p className="mt-1 text-sm text-slate-500">Set at next session open.</p>
        )}
      </section>

      <section className="rounded-lg border border-orange-900/40 bg-orange-950/20 p-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-orange-300">
          M15 pullback · {stack.m15?.status ?? "pending"}
        </h3>
        {stack.m15 ? (
          <p className="mt-1 text-sm text-slate-200">
            <span className="font-semibold uppercase">{stack.m15.side}</span> zone{" "}
            {Number(stack.m15.pullback_zone[0]).toFixed(2)}–
            {Number(stack.m15.pullback_zone[1]).toFixed(2)} · SL{" "}
            {stack.m15.invalidation.toFixed(2)} · TP {stack.m15.target.toFixed(2)}
          </p>
        ) : (
          <p className="mt-1 text-sm text-slate-500">Set at next session open.</p>
        )}
      </section>

      {latestRev && (
        <p className="text-xs text-slate-500">
          Last revise:{" "}
          {SESSION_LABELS[latestRev.session || ""] ?? latestRev.session ?? "session"}{" "}
          · {latestRev.change_summary || "—"}
          {latestRev.performance ? ` · prior ${latestRev.performance}` : ""}
        </p>
      )}
    </div>
  );
}
