"use client";

import type { MarketBriefVM, RightNowVM } from "@/lib/viewModel";
import { TRADE_STATUS_TEXT, price as fmt } from "@/lib/translate";

/**
 * Four separate claims, side by side.
 *
 * The point of this card is the separation itself. Bias, trade status, location
 * and confirmation are independent facts, and the old screen let them blur:
 * "BULLISH" sat next to a green branch and read as "buy now", when the honest
 * reading was "the market leans up AND there is no valid entry at this price".
 *
 * Showing them as four columns makes the common case legible at a glance --
 * bullish, waiting, at resistance, unconfirmed -- which is a complete thought
 * rather than a mixed signal.
 */

const LOCATION_TEXT: Record<string, string> = {
  AT_SUPPORT: "At support",
  NEAR_SUPPORT: "Near support",
  MID_RANGE: "Mid-range",
  NEAR_RESISTANCE: "Near resistance",
  AT_RESISTANCE: "At resistance",
  INSIDE_ENTRY_ZONE: "In the entry zone",
  UNKNOWN: "Unknown",
};

/** Amber for wait, green for go, red for dead. Location is amber when poor. */
function statusTone(status: string): string {
  switch (status) {
    case "READY":
    case "ENTER":
      return "text-emerald-300";
    case "CANCELLED":
      return "text-rose-300";
    case "AVOID":
      return "text-zinc-400";
    default:
      return "text-amber-300";
  }
}

function locationTone(location: string): string {
  if (location === "INSIDE_ENTRY_ZONE") return "text-emerald-300";
  if (location === "AT_RESISTANCE" || location === "AT_SUPPORT") return "text-amber-300";
  return "text-sky-300";
}

function biasTone(bias: string): string {
  if (bias === "BULLISH") return "text-emerald-300";
  if (bias === "BEARISH") return "text-rose-300";
  return "text-zinc-400";
}

function Cell({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone: string;
  hint?: string;
}) {
  return (
    <div className="flex-1 min-w-[150px]">
      <div className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className={`text-lg font-semibold ${tone}`}>{value}</div>
      {hint ? <div className="text-[11px] text-zinc-500 mt-0.5">{hint}</div> : null}
    </div>
  );
}

export function MarketBrief({
  brief,
  rightNow,
}: {
  brief: MarketBriefVM;
  rightNow: RightNowVM;
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="flex items-baseline justify-between mb-3">
        <div className="flex items-baseline gap-3">
          <span className="text-xl font-semibold text-zinc-100">{brief.symbol}</span>
          <span className="text-2xl font-mono text-zinc-100">{fmt(brief.price)}</span>
        </div>
        <div className="text-xs text-zinc-500">
          {brief.session}
          {brief.sessionHour != null ? ` · hour ${brief.sessionHour}` : ""}
        </div>
      </div>

      <div className="flex flex-wrap gap-4">
        <Cell label="Market bias" value={brief.bias} tone={biasTone(brief.bias)} />
        <Cell
          label="Trade status"
          value={brief.tradeStatus}
          tone={statusTone(brief.tradeStatus)}
          hint={TRADE_STATUS_TEXT[brief.tradeStatus]}
        />
        <Cell
          label="Price location"
          value={LOCATION_TEXT[brief.location] ?? brief.location}
          tone={locationTone(brief.location)}
        />
        <Cell label="Confirmation" value={brief.confirmation} tone="text-zinc-300" />
      </div>

      {/*
        The action line lives here rather than in a card of its own.
        A separate AVOID panel repeated the status, the subtitle and the reason
        that are already in this card -- four renderings of "already played out"
        on one screen. One home per fact.
      */}
      <div className="mt-3 pt-3 border-t border-zinc-800 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={`text-sm font-semibold ${statusTone(brief.tradeStatus)}`}>
          {brief.condition}
        </span>
        {rightNow.waitingFor.length > 0 && (
          <span className="text-sm text-zinc-400">
            Waiting for: {rightNow.waitingFor.join(" · ")}
          </span>
        )}
      </div>

      {rightNow.avoid.length > 0 && (
        <div className="mt-1 text-sm text-zinc-500">
          <span className="text-rose-400/80">Don&apos;t: </span>
          {rightNow.avoid.join(" · ")}
        </div>
      )}
    </section>
  );
}
