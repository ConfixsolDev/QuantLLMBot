"use client";

import type { HourlyUpdate } from "@/lib/types";

/**
 * Today's hours as a session ribbon.
 *
 * The old ribbon rendered every hourly update ever recorded, labelled
 * H0…H23 and coloured by plan_status. Across several days that produced
 * "H21 H22 H23 H0 H1 H2 …" with hour numbers repeating and no way to tell which
 * day or session an hour belonged to.
 *
 * This shows today only, labels each hour by its session (A=Asia, L=London,
 * O=Overlap, N=New York, P=pre-London, X=off-session) with its index inside
 * that session, and colours it by the hour's OWN candle — green when it closed
 * up, red when it closed down. Reading left to right you can see how the day
 * has actually gone, session by session.
 */

const SESSION_CODE: Record<string, string> = {
  asia: "A",
  london: "L",
  overlap: "O",
  new_york: "N",
  pre_london: "P",
  off_session: "X",
};

// UTC session boundaries, matching market_context_cache.session_at().
function sessionOf(hour: number): string {
  if (hour < 7) return "asia";
  if (hour < 8) return "pre_london";
  if (hour < 13) return "london";
  if (hour < 16) return "overlap";
  if (hour < 21) return "new_york";
  return "off_session";
}

function sessionStart(session: string): number {
  switch (session) {
    case "asia":
      return 0;
    case "pre_london":
      return 7;
    case "london":
      return 8;
    case "overlap":
      return 13;
    case "new_york":
      return 16;
    default:
      return 21;
  }
}

type Marked = {
  update: HourlyUpdate;
  label: string;
  session: string;
  direction: "bull" | "bear" | "flat";
  change: number | null;
};

function directionOf(update: HourlyUpdate): { dir: "bull" | "bear" | "flat"; change: number | null } {
  const ohlc = (update as unknown as { hour_ohlc?: { o?: number; c?: number } }).hour_ohlc;
  if (ohlc && typeof ohlc.o === "number" && typeof ohlc.c === "number") {
    const change = ohlc.c - ohlc.o;
    if (change > 0) return { dir: "bull", change };
    if (change < 0) return { dir: "bear", change };
    return { dir: "flat", change: 0 };
  }
  const observed = String(
    (update as unknown as { actual_vs_expected?: { observed?: string } })
      .actual_vs_expected?.observed ?? "",
  ).toLowerCase();
  if (observed.includes("bullish")) return { dir: "bull", change: null };
  if (observed.includes("bearish")) return { dir: "bear", change: null };
  return { dir: "flat", change: null };
}

export function SessionRibbon({
  hourlyUpdates,
  selectedHourlyId,
  onSelectHour,
}: {
  hourlyUpdates: HourlyUpdate[];
  selectedHourlyId: string | null;
  onSelectHour: (id: string) => void;
}) {
  // Today = the trading date of the most recent update, so the ribbon stays
  // correct when reviewing a session that has rolled past midnight UTC.
  const latest = hourlyUpdates[hourlyUpdates.length - 1];
  const today = latest?.clock?.trading_date_utc;

  const marked: Marked[] = hourlyUpdates
    .filter((u) => !today || u.clock?.trading_date_utc === today)
    .map((update) => {
      const hour = update.clock?.utc_hour ?? 0;
      const session = sessionOf(hour);
      const index = hour - sessionStart(session) + 1;
      const { dir, change } = directionOf(update);
      return {
        update,
        session,
        label: `${SESSION_CODE[session] ?? "?"}${index}`,
        direction: dir,
        change,
      };
    });

  if (!marked.length) {
    return (
      <div className="text-xs text-slate-600">No hourly updates for today yet.</div>
    );
  }

  const bull = marked.filter((m) => m.direction === "bull").length;
  const bear = marked.filter((m) => m.direction === "bear").length;

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {marked.map((m) => {
          const selected = selectedHourlyId === m.update.hourly_id;
          const tone =
            m.direction === "bull"
              ? "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
              : m.direction === "bear"
                ? "bg-rose-500/20 text-rose-300 hover:bg-rose-500/30"
                : "bg-slate-700/40 text-slate-400 hover:bg-slate-700/60";
          return (
            <button
              key={m.update.hourly_id}
              type="button"
              onClick={() => onSelectHour(m.update.hourly_id)}
              title={`${m.session.replace("_", " ")} · UTC hour ${
                m.update.clock?.utc_hour
              }${m.change != null ? ` · ${m.change >= 0 ? "+" : ""}${m.change.toFixed(2)}` : ""}`}
              className={`min-w-[2.4rem] rounded px-2 py-1 font-medium tabular-nums transition-colors ${tone} ${
                selected ? "ring-1 ring-gold" : ""
              }`}
            >
              {m.label}
            </button>
          );
        })}
      </div>
      <div className="text-[11px] text-slate-600">
        Today · <span className="text-emerald-400">{bull} up</span> ·{" "}
        <span className="text-rose-400">{bear} down</span> · A Asia · L London ·
        O Overlap · N New York
      </div>
    </div>
  );
}
