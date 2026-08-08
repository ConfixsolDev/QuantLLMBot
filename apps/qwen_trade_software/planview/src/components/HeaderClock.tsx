"use client";

import { useEffect, useState } from "react";
import type { Clock } from "@/lib/types";
import { SESSION_LABELS } from "@/lib/types";

function countdown(nextBoundaryUtc: string): string {
  const target = new Date(nextBoundaryUtc).getTime();
  const now = Date.now();
  const diff = Math.max(0, target - now);
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${hours}h ${minutes}m ${seconds}s`;
}

export function HeaderClock({ clock, plannerStatus, plannerAlive }: {
  clock: Clock;
  plannerStatus: string;
  plannerAlive?: boolean;
}) {
  const [remaining, setRemaining] = useState(countdown(clock.next_boundary_utc));

  useEffect(() => {
    const timer = setInterval(
      () => setRemaining(countdown(clock.next_boundary_utc)),
      1000,
    );
    return () => clearInterval(timer);
  }, [clock.next_boundary_utc]);

  return (
    <header className="card flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold text-gold">GoldFlow Plan View</h1>
        <p className="text-sm text-slate-400">
          Session-hierarchy planner · hourly validation
        </p>
      </div>
      <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm md:grid-cols-4">
        <div>
          <span className="text-slate-500">UTC</span>
          <p className="font-mono">{clock.utc_time.replace("T", " ").replace("Z", "")}</p>
        </div>
        <div>
          <span className="text-slate-500">Session</span>
          <p>
            {SESSION_LABELS[clock.session] ?? clock.session} · hour{" "}
            {clock.hour_of_session}
          </p>
        </div>
        <div>
          <span className="text-slate-500">Hours into day</span>
          <p>{clock.hours_into_day} / 24</p>
        </div>
        <div>
          <span className="text-slate-500">Next boundary</span>
          <p className="font-mono text-xs">{remaining}</p>
        </div>
      </div>
      <div className="text-xs text-slate-500">
        Planner: {plannerStatus}
        {plannerAlive === false ? " (process offline)" : ""}
      </div>
    </header>
  );
}
