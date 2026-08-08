"use client";

import type { DayPlan } from "@/lib/types";

function ScenarioCard({
  title,
  scenario,
  tone,
}: {
  title: string;
  scenario: DayPlan["bullish_scenario"];
  tone: "bull" | "bear";
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        tone === "bull"
          ? "border-emerald-900/50 bg-emerald-950/30"
          : "border-rose-900/50 bg-rose-950/30"
      }`}
    >
      <h3 className="mb-2 font-medium capitalize">{title}</h3>
      <dl className="space-y-1 text-sm">
        <div>
          <dt className="text-slate-500">Trigger</dt>
          <dd>{scenario.trigger}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Targets</dt>
          <dd>{scenario.targets.join(" · ")}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Invalidation</dt>
          <dd>{scenario.invalidation}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Evidence</dt>
          <dd className="text-xs text-slate-400">{scenario.evidence.join("; ")}</dd>
        </div>
      </dl>
    </div>
  );
}

export function DayPlanPanel({ dayPlan }: { dayPlan: DayPlan | null }) {
  if (!dayPlan) {
    return (
      <div className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Day plan
        </h2>
        <p className="mt-2 text-sm text-slate-500">Waiting for day plan…</p>
      </div>
    );
  }

  const validator = dayPlan.validator;

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Day plan · {dayPlan.day_plan_id}
        </h2>
        <div className="flex gap-2">
          <span
            className={`badge ${
              validator?.verdict === "agree" ? "badge-on_track" : "badge-invalidated"
            }`}
          >
            Validator: {validator?.verdict ?? "pending"}
          </span>
          <span
            className={`badge ${
              dayPlan.tradeable ? "badge-on_track" : "badge-drifting"
            }`}
          >
            {dayPlan.tradeable ? "Tradeable" : "Not tradeable"}
          </span>
        </div>
      </div>
      <p className="text-sm text-slate-300">
        Reference {dayPlan.reference_price.toFixed(2)}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <ScenarioCard
          title="Bullish"
          scenario={dayPlan.bullish_scenario}
          tone="bull"
        />
        <ScenarioCard
          title="Bearish"
          scenario={dayPlan.bearish_scenario}
          tone="bear"
        />
      </div>
      <div>
        <h3 className="mb-2 text-xs uppercase text-slate-500">Expected session behaviour</h3>
        <ul className="grid gap-1 text-sm md:grid-cols-2">
          {Object.entries(dayPlan.expected_session_behaviour).map(([session, text]) => (
            <li key={session}>
              <span className="text-slate-500">{session}:</span> {text}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
