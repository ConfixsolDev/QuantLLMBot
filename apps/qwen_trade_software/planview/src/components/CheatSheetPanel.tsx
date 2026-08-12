"use client";

import type { DayPlan, SessionPlan, TradeIdea } from "@/lib/types";
import { levelName } from "@/lib/translate";

interface CheatLevel {
  label: string;
  price: number;
  role: string;
}

interface CheatSheetPanelProps {
  open: boolean;
  onClose: () => void;
  livePrice?: number | null;
  dayPlan: DayPlan | null;
  sessionPlan: SessionPlan | null;
  tradeIdea: TradeIdea | null;
}

function collectLevels(
  dayPlan: DayPlan | null,
  sessionPlan: SessionPlan | null,
  tradeIdea: TradeIdea | null,
): CheatLevel[] {
  const rows: CheatLevel[] = [];
  for (const level of dayPlan?.key_levels ?? []) {
    rows.push({
      label: levelName(level.label) || "day level",
      price: Number(level.price),
      role: String(level.role || "level").replace(/_/g, " "),
    });
  }
  for (const zone of sessionPlan?.entry_zones ?? []) {
    const lo = Array.isArray(zone.zone) ? Number(zone.zone[0]) : NaN;
    const hi = Array.isArray(zone.zone) ? Number(zone.zone[1]) : NaN;
    if (Number.isFinite(lo) && Number.isFinite(hi)) {
      rows.push({
        label: `${zone.side || "zone"} entry`,
        price: (lo + hi) / 2,
        role: `${lo.toFixed(1)}–${hi.toFixed(1)}`,
      });
    }
  }
  const plan = tradeIdea?.execution_plan;
  if (plan?.status === "ready") {
    if (typeof plan.entry_low === "number") {
      rows.push({ label: "Qwen entry low", price: plan.entry_low, role: "entry" });
    }
    if (typeof plan.entry_high === "number") {
      rows.push({ label: "Qwen entry high", price: plan.entry_high, role: "entry" });
    }
    if (typeof plan.stop_loss === "number") {
      rows.push({ label: "Broker SL ($3)", price: plan.stop_loss, role: "stop" });
    }
    if (typeof plan.take_profit === "number") {
      rows.push({ label: "Broker TP ($5)", price: plan.take_profit, role: "target" });
    }
  }
  const seen = new Set<string>();
  return rows
    .filter((row) => Number.isFinite(row.price))
    .sort((a, b) => b.price - a.price)
    .filter((row) => {
      const key = `${row.label}:${row.price.toFixed(3)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

export function CheatSheetPanel({
  open,
  onClose,
  livePrice,
  dayPlan,
  sessionPlan,
  tradeIdea,
}: CheatSheetPanelProps) {
  if (!open) return null;
  const levels = collectLevels(dayPlan, sessionPlan, tradeIdea);
  const price = typeof livePrice === "number" ? livePrice : null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end bg-black/50 p-4 md:p-6">
      <button
        type="button"
        aria-label="Close cheat sheet"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <aside className="relative z-10 mt-16 w-full max-w-md rounded-xl border border-slate-700 bg-slate-950 p-4 shadow-2xl">
        <header className="mb-3 flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-400">
              Cheat sheet
            </p>
            <h2 className="text-lg font-semibold text-slate-100">Named levels</h2>
            <p className="mt-1 text-xs text-slate-400">
              Live {price && price > 0 ? price.toFixed(3) : "—"} · scenario{" "}
              {sessionPlan?.active_scenario || "n/a"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
          >
            Close
          </button>
        </header>

        <div className="mb-3 rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-300">
          <p className="font-semibold text-slate-100">Do not</p>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            <li>Fade acceptance above broken resistance / under broken support</li>
            <li>Buy into holding resistance or sell into holding support</li>
            <li>Trade the middle of a two-sided balance</li>
          </ul>
        </div>

        <div className="max-h-[60vh] space-y-2 overflow-y-auto">
          {levels.length === 0 ? (
            <p className="text-sm text-slate-500">No plan/Qwen levels yet.</p>
          ) : (
            levels.map((level) => {
              const side =
                price && price > 0
                  ? level.price >= price
                    ? "resistance"
                    : "support"
                  : "level";
              return (
                <div
                  key={`${level.label}-${level.price}`}
                  className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-100">{level.label}</p>
                    <p className="text-[11px] uppercase tracking-wide text-slate-500">
                      {level.role} · {side}
                    </p>
                  </div>
                  <code className="text-sm font-semibold text-amber-300">
                    {level.price.toFixed(3)}
                  </code>
                </div>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
}
