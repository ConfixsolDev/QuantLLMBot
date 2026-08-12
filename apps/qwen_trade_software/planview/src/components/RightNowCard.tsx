"use client";

import type { RightNowVM } from "@/lib/viewModel";

/**
 * The one card that answers "what do I do in the next minute".
 *
 * Placed directly under the brief and never collapsed. The spec's target is
 * that a trader understands the situation in about five seconds; that only
 * works if the action is the largest thing on screen rather than something
 * inferred from four coloured badges.
 *
 * "Avoid" is given equal weight to "waiting for" on purpose. Most of the losses
 * in this system's record came from entries that were directionally right and
 * badly located -- chasing into resistance, entering before a candle closed.
 * Naming the specific wrong action is more useful than another restatement of
 * the right one.
 */

const TONE: Record<string, { border: string; bg: string; text: string }> = {
  READY: { border: "border-emerald-700", bg: "bg-emerald-950/40", text: "text-emerald-300" },
  ENTER: { border: "border-emerald-600", bg: "bg-emerald-950/50", text: "text-emerald-200" },
  MANAGE: { border: "border-sky-700", bg: "bg-sky-950/40", text: "text-sky-300" },
  CANCELLED: { border: "border-rose-800", bg: "bg-rose-950/30", text: "text-rose-300" },
  AVOID: { border: "border-zinc-700", bg: "bg-zinc-900/60", text: "text-zinc-400" },
  WAIT: { border: "border-amber-700", bg: "bg-amber-950/30", text: "text-amber-300" },
};

export function RightNowCard({ rightNow }: { rightNow: RightNowVM }) {
  const tone = TONE[rightNow.action] ?? TONE.WAIT;

  return (
    <section className={`rounded-lg border ${tone.border} ${tone.bg} p-4`}>
      <div className="flex items-center gap-3 mb-1">
        <span className={`text-2xl font-bold tracking-tight ${tone.text}`}>
          {rightNow.action}
        </span>
        <span className="text-lg text-zinc-200">{rightNow.headline}</span>
      </div>
      <p className="text-sm text-zinc-400">{rightNow.reason}</p>

      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {rightNow.waitingFor.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
              Waiting for
            </div>
            <ul className="space-y-1">
              {rightNow.waitingFor.map((item) => (
                <li key={item} className="text-sm text-zinc-300 flex gap-2">
                  <span className="text-amber-500 mt-[2px]">◦</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {rightNow.avoid.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
              Do not
            </div>
            <ul className="space-y-1">
              {rightNow.avoid.map((item) => (
                <li key={item} className="text-sm text-zinc-400 flex gap-2">
                  <span className="text-rose-500 mt-[2px]">×</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
