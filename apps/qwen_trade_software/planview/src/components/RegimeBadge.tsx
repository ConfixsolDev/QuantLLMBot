import type { RegimeContext } from "@/lib/types";

const LABELS: Record<string, string> = {
  trend_strong: "Strong Trend",
  trend_channel: "Trend Channel",
  trending_range: "Trending Range",
  range: "Range",
  tight_range: "Tight Range · Edge Scalp",
  breakout_attempt: "Breakout Attempt · Response Scalp",
  breakout_confirmed: "Breakout Confirmed",
  reversal_attempt: "Reversal Attempt · Response Scalp",
  reversal_confirmed: "Reversal Confirmed",
  climax_exhaustion: "Climax / Exhaustion · Response Scalp",
  unknown: "Unknown · No Trade",
};

const TONES: Record<string, string> = {
  trend: "border-sky-700 bg-sky-950/70 text-sky-200",
  range: "border-amber-700 bg-amber-950/70 text-amber-200",
  reversal: "border-fuchsia-700 bg-fuchsia-950/70 text-fuchsia-200",
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RegimeBadge({ regime }: { regime?: RegimeContext | null }) {
  const state = String(regime?.regime_state || "unknown").toLowerCase();
  const family = String(regime?.regime_family || "unknown").toLowerCase();
  const direction = regime?.trend_direction?.toUpperCase();
  const tone = TONES[family] || "border-slate-600 bg-slate-900 text-slate-300";
  const baseLabel = LABELS[state] || titleCase(state);
  const label = regime?.pullback_active ? `${baseLabel} · Pullback` : baseLabel;
  const transitionAge = regime?.transition_age_minutes;

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-1 text-sm ${tone}`}
      title={`Deterministic regime · source: ${regime?.source || "unavailable"}${
        transitionAge != null ? ` · transition ${transitionAge.toFixed(1)}m / 15m` : ""
      }`}
      data-testid="regime-badge"
    >
      <span className="text-[10px] font-semibold uppercase tracking-wider opacity-70">
        Market regime
      </span>
      <span className="font-bold">{label}</span>
      {direction ? (
        <span className="rounded bg-black/20 px-1.5 py-0.5 text-[10px] font-semibold">
          {direction}
        </span>
      ) : null}
    </div>
  );
}
