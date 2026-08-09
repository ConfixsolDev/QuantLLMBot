"use client";

import type { HourlyUpdate } from "@/lib/types";
import { SESSION_LABELS } from "@/lib/types";

export function HourValidationCard({ update }: { update: HourlyUpdate | null }) {
  if (!update) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Hour validation
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          No closed hour to validate yet. Updates appear after each UTC hour closes.
        </p>
      </div>
    );
  }

  const ohlc = update.hour_ohlc;

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Hour validation · {update.hourly_id}
        </h2>
        <span className={`badge badge-${update.plan_status}`}>
          {update.plan_status.replace("_", " ")}
        </span>
      </div>
      <p className="text-sm">
        {SESSION_LABELS[update.clock.session] ?? update.clock.session} · hour{" "}
        {update.clock.hour_of_session} of session · UTC hour {update.clock.utc_hour}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 p-3">
          <h3 className="text-xs uppercase text-slate-500">Expected</h3>
          <p className="mt-1">{update.actual_vs_expected.expected || "—"}</p>
        </div>
        <div className="rounded-lg border border-slate-800 p-3">
          <h3 className="text-xs uppercase text-slate-500">Observed</h3>
          <p className="mt-1">{update.actual_vs_expected.observed}</p>
          <p
            className={`mt-1 text-xs ${
              update.actual_vs_expected.match ? "text-emerald-400" : "text-amber-400"
            }`}
          >
            Match: {update.actual_vs_expected.match ? "yes" : "no"}
          </p>
        </div>
      </div>
      {ohlc && (
        <div className="rounded-lg border border-slate-800 p-3 font-mono text-sm">
          <h3 className="mb-2 text-xs uppercase text-slate-500">Hour OHLC</h3>
          O {ohlc.o.toFixed(2)} · H {ohlc.h.toFixed(2)} · L {ohlc.l.toFixed(2)} · C{" "}
          {ohlc.c.toFixed(2)}
        </div>
      )}
      {update.levels_touched.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs uppercase text-slate-500">Levels touched</h3>
          <ul className="space-y-1 text-sm">
            {update.levels_touched.map((level) => (
              <li key={`${level.price}-${level.label}`}>
                {level.label} @ {level.price.toFixed(2)} → {level.result}
              </li>
            ))}
          </ul>
        </div>
      )}
      {update.layer_validation && (
        <div className="flex flex-wrap gap-2 text-xs">
          {(["h4", "h1", "m15"] as const).map((layer) => (
            <span
              key={layer}
              className={`badge badge-${update.layer_validation?.[layer] || "pending"}`}
            >
              {layer.toUpperCase()} {update.layer_validation?.[layer]}
            </span>
          ))}
        </div>
      )}
      <p className="text-sm text-slate-300">{update.note}</p>
      <p className="text-xs text-slate-500">
        Confidence delta: {update.confidence_delta >= 0 ? "+" : ""}
        {update.confidence_delta}
      </p>
    </div>
  );
}
