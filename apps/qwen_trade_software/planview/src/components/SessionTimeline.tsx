"use client";

import type { Clock, HourlyUpdate, SessionPlan, SessionVerdict } from "@/lib/types";
import { PLANNING_SESSIONS, SESSION_LABELS } from "@/lib/types";

interface SessionTimelineProps {
  clock: Clock;
  sessionPlan: SessionPlan | null;
  sessionVerdicts: SessionVerdict[];
  hourlyUpdates: HourlyUpdate[];
}

export function SessionTimeline({
  clock,
  sessionPlan,
  sessionVerdicts,
  hourlyUpdates,
}: SessionTimelineProps) {
  return (
    <div className="card">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Session timeline
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {PLANNING_SESSIONS.map((session) => {
          const isCurrent = clock.session === session;
          const verdict = sessionVerdicts.find((v) => v.session === session);
          const planForSession =
            sessionPlan?.session === session ? sessionPlan : null;
          const hourlies = hourlyUpdates.filter(
            (u) => u.clock.session === session,
          );
          return (
            <div
              key={session}
              className={`rounded-lg border p-3 ${
                isCurrent
                  ? "border-gold bg-gold/10"
                  : "border-slate-800 bg-slate-900/40"
              }`}
            >
              <p className="font-medium">{SESSION_LABELS[session]}</p>
              {isCurrent && (
                <p className="text-xs text-gold">
                  Active · hour {clock.hour_of_session}
                </p>
              )}
              {planForSession && (
                <p className="mt-1 text-xs text-slate-400">
                  {planForSession.active_scenario} · conf {planForSession.confidence}
                </p>
              )}
              {verdict && (
                <p className="mt-1 text-xs text-emerald-400">
                  Verdict: {verdict.scenario_outcome}
                </p>
              )}
              {hourlies.length > 0 && (
                <p className="mt-1 text-xs text-slate-500">
                  {hourlies.length} hourly update(s)
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
