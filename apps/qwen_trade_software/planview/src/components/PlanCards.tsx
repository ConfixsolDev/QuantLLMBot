"use client";

import type { PlanVM, PriceLocationVM } from "@/lib/viewModel";
import { CONFIDENCE_TEXT, price as fmt } from "@/lib/translate";

/**
 * Primary and alternative, deliberately unequal.
 *
 * The old screen rendered bullish and bearish as matching cards side by side.
 * Two identical panels read as two equally available trades, when in reality at
 * most one is live and the other needs its own trigger before it means
 * anything. Equal styling was quietly making a claim about probability that
 * nothing in the data supported.
 *
 * Primary gets full contrast and every field. Alternative is muted, narrower,
 * and leads with its activation condition rather than its targets -- because
 * until that condition fires, its targets are not a plan.
 */

function ToneBar({ direction }: { direction: string }) {
  const colour = direction === "BUY" ? "bg-emerald-500" : "bg-rose-500";
  return <span className={`inline-block w-1.5 h-5 rounded-sm ${colour}`} />;
}

function LevelRow({
  label,
  value,
  tone = "text-zinc-200",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex justify-between gap-4 text-sm py-0.5">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono ${tone}`}>{value}</span>
    </div>
  );
}

export function PrimaryPlanCard({
  plan,
  alternative,
  location,
}: {
  plan: PlanVM | null;
  alternative: PlanVM | null;
  location: PriceLocationVM;
}) {
  if (!plan) {
    return (
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h3 className="text-sm uppercase tracking-wide text-zinc-500">Primary plan</h3>
        <p className="text-sm text-zinc-400 mt-2">No active plan.</p>
      </section>
    );
  }

  const dead = !plan.isActive;

  return (
    <section
      className={`rounded-lg border p-4 ${
        dead ? "border-zinc-800 bg-zinc-900/30 opacity-60" : "border-zinc-700 bg-zinc-900/60"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <ToneBar direction={plan.direction} />
          <h3 className="text-sm uppercase tracking-wide text-zinc-400">Primary plan</h3>
          <span
            className={`text-lg font-bold ${
              plan.direction === "BUY" ? "text-emerald-300" : "text-rose-300"
            }`}
          >
            {plan.direction}
          </span>
        </div>
      </div>

      <p className="text-sm text-zinc-300 mb-3">{plan.thesis}</p>

      <div className="rounded border border-zinc-800 bg-zinc-950/40 px-3 py-2 mb-3">
        <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
          What has to happen
        </div>
        <div className="text-sm text-zinc-200">{plan.trigger}</div>
      </div>

      <div className="space-y-0.5">
        {location.entryZone && (
          <LevelRow
            label="Entry zone"
            value={`${fmt(location.entryZone[0])}–${fmt(location.entryZone[1])}`}
            tone="text-sky-300"
          />
        )}
        {plan.targets.map((target, index) => (
          <LevelRow
            key={target}
            label={`Target ${index + 1}`}
            value={fmt(target)}
            tone="text-emerald-300"
          />
        ))}
        <LevelRow
          label="Invalidation"
          value={fmt(plan.invalidation)}
          tone="text-rose-300"
        />
      </div>

      {plan.evidence.length > 0 && (
        <div className="mt-3 pt-3 border-t border-zinc-800">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
            Why the system believes this
          </div>
          <ul className="space-y-0.5">
            {plan.evidence.map((item) => (
              <li key={item} className="text-sm text-zinc-400 flex gap-2">
                <span className="text-zinc-600 mt-[2px]">·</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 pt-2 border-t border-zinc-800 flex items-baseline gap-2">
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">Confidence</span>
        <span className="text-sm text-zinc-200">
          {CONFIDENCE_TEXT[plan.confidenceLabel]}
        </span>
        <span className="text-xs text-zinc-600 font-mono">{plan.confidence}</span>
      </div>

      <AlternativeFooter plan={alternative} />
    </section>
  );
}

/**
 * The alternative, as a footer inside the plan box rather than a card of its own.
 *
 * Given equal billing it read as a second available trade. It is not one -- it
 * needs its own trigger, and until that fires the only useful thing to say is
 * one line about when it would matter.
 */
function AlternativeFooter({ plan }: { plan: PlanVM | null }) {
  if (!plan) return null;

  return (
    <div className="mt-4 pt-3 border-t border-zinc-800">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-[11px] uppercase tracking-wide text-zinc-600">
          If that fails
        </span>
        <span className="text-xs font-medium text-zinc-500">{plan.direction}</span>
        <span className="text-[11px] text-zinc-600">— not a trade yet</span>
      </div>
      <div className="text-sm text-zinc-400">{plan.activationCondition}</div>
    </div>
  );
}
