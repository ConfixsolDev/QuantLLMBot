"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Clock, RuntimeStatus } from "@/lib/types";
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

function StatusPill({
  ok,
  label,
  detail,
}: {
  ok: boolean | null;
  label: string;
  detail?: string;
}) {
  const tone =
    ok === null
      ? "border-slate-700 bg-slate-900 text-slate-400"
      : ok
        ? "border-emerald-800 bg-emerald-950/50 text-emerald-300"
        : "border-rose-900 bg-rose-950/40 text-rose-300";
  return (
    <span className={`rounded border px-2 py-1 text-xs ${tone}`}>
      <span className="font-semibold">{label}</span>
      {detail ? <span className="ml-1 opacity-90">{detail}</span> : null}
    </span>
  );
}

export function HeaderClock({
  clock,
  plannerStatus,
  plannerAlive,
  runtime,
}: {
  clock: Clock;
  plannerStatus: string;
  plannerAlive?: boolean;
  runtime?: RuntimeStatus | null;
}) {
  const [remaining, setRemaining] = useState(countdown(clock.next_boundary_utc));

  useEffect(() => {
    const timer = setInterval(
      () => setRemaining(countdown(clock.next_boundary_utc)),
      1000,
    );
    return () => clearInterval(timer);
  }, [clock.next_boundary_utc]);

  const device = runtime?.model_device || "unloaded";
  const modelOk =
    runtime == null ? null : Boolean(runtime.model_resident || runtime.model_installed);
  const mt5Ok = runtime == null ? null : Boolean(runtime.mt5_connected);
  const deviceDetail =
    device === "GPU"
      ? "GPU"
      : device === "CPU"
        ? "CPU"
        : device === "MIXED"
          ? "MIXED"
          : "unloaded";

  return (
    <header className="card flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold text-gold">GoldFlow Plan View</h1>
        <p className="text-sm text-slate-400">
          Session-hierarchy planner · hourly validation
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusPill
            ok={modelOk && device === "GPU" ? true : modelOk && device !== "unloaded" ? true : modelOk}
            label="Model"
            detail={`${runtime?.model?.replace(":latest", "") || "qwen"} · ${deviceDetail}`}
          />
          <StatusPill
            ok={mt5Ok}
            label="MT5"
            detail={mt5Ok ? "connected" : mt5Ok === false ? "disconnected" : "…"}
          />
          <StatusPill
            ok={plannerAlive ?? null}
            label="Planner"
            detail={plannerStatus}
          />
          <Link
            href="/ideas/"
            className="rounded bg-gold px-2.5 py-1 text-xs font-semibold text-ink hover:brightness-110"
          >
            Trade ideas &gt;50%
          </Link>
        </div>
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
    </header>
  );
}
