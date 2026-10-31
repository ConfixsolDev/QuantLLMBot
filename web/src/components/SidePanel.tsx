"use client";

// What the engine thinks right now, in words: trend per timeframe, the
// liquidity around price and what just happened there, nearby zones, order
// blocks and fair value gaps, and the session levels.

import { fmtTime, type Snapshot } from "@/lib/api";

const arrow = (s: string) => (s === "up" ? "▲ up" : s === "down" ? "▼ down" : "– none");
const tone = (s: string) => (s === "up" || s === "demand" ? "text-emerald-400" : s === "down" || s === "supply" ? "text-rose-400" : "text-slate-400");
const p = (x: number | null | undefined) => (x === null || x === undefined ? "–" : x.toFixed(2));
const LEVEL_TXT: Record<string, string> = {
  level_test: "Test", level_rejection: "M1 rejection", level_followthrough: "Follow-through", level_held: "Held",
  level_broken: "Broken", level_pattern: "M1 pattern at level",
};
const LIQ: Record<string, string> = { liquidity_sweep: "Sweep", sweep_failed: "Sweep failed", false_break: "False break", liquidity_taken: "Taken" };

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h3>
      {children}
    </section>
  );
}

export default function SidePanel({ snap }: { snap: Snapshot | null }) {
  if (!snap || !snap.as_of) return <div className="card text-sm text-slate-400">Waiting for the engine…</div>;
  const price = snap.price ?? 0;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <Card title="Trend (BOS / CHoCH)">
        <table className="w-full">
          <tbody>
            {Object.entries(snap.trend ?? {}).map(([tf, t]) => (
              <tr key={tf} className="border-b border-slate-800/60 last:border-0">
                <td className="py-1 pr-2 text-slate-400">{tf}</td>
                <td className={`py-1 pr-2 font-medium ${tone(t.state)}`}>{arrow(t.state)}</td>
                <td className="py-1 text-xs text-slate-400">
                  {t.last_break ? `${t.last_break.kind.toUpperCase()} ${t.last_break.direction} @ ${p(t.last_break.level)}` : "no break yet"}
                  {t.protected !== null ? <span className="block">protected {p(t.protected)}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="HTF levels (H1/H4 swings, sessions, day, week)">
        {(snap.htf_levels ?? []).slice(0, 8).map((lv) => (
          <div key={lv.id} className="flex justify-between py-0.5">
            <span className={lv.side === "high" ? "text-rose-300" : "text-emerald-300"}>
              {lv.sources.join(" + ")}
              <span className="text-xs text-slate-500"> · {lv.tests ? `tested ${lv.tests}×` : "untested"}{lv.testing ? " · testing now" : ""}</span>
            </span>
            <span>{p(lv.price)} <span className="text-xs text-slate-500">({lv.price > price ? "+" : ""}{(lv.price - price).toFixed(1)})</span></span>
          </div>
        ))}
        {!snap.htf_levels?.length && <div className="text-slate-500">no active level</div>}
        {(snap.recent_level_events ?? []).slice(0, 6).map((e, i) => (
          <div key={i} className="flex justify-between border-t border-slate-800/60 py-0.5 text-xs text-slate-300">
            <span>{LEVEL_TXT[e.kind] ?? e.kind}{e.test_no ? ` (test ${e.test_no})` : ""}{e.result ? `: ${e.result}` : ""}{e.approach ? `, ${e.approach}` : ""}{e.pattern ? `: ${e.pattern.replace("_", " ")}` : ""}</span>
            <span className="text-slate-500">{p(e.level)} · {fmtTime(e.time).slice(11, 16)}</span>
          </div>
        ))}
      </Card>

      <Card title="Liquidity — what just happened">
        {(snap.recent_liquidity ?? []).slice(0, 6).map((e, i) => (
          <div key={i} className="flex justify-between border-b border-slate-800/60 py-1 last:border-0">
            <span className={e.kind === "liquidity_sweep" || e.kind === "false_break" ? "text-cyan-300" : "text-slate-300"}>
              {LIQ[e.kind] ?? e.kind} {e.side}
            </span>
            <span className="text-xs text-slate-400">{e.levels.map(([k, v]) => `${k.replace("_", " ")} ${p(v)}`).join(", ")}</span>
          </div>
        ))}
        {!snap.recent_liquidity?.length && <div className="text-slate-500">nothing yet</div>}
      </Card>

      <Card title="Liquidity pools nearest price">
        {(snap.liquidity_pools ?? []).slice(0, 8).map((lp, i) => (
          <div key={i} className="flex justify-between py-0.5">
            <span className={lp.side === "high" ? "text-rose-300" : "text-emerald-300"}>{lp.kind.replace(/_/g, " ")} <span className="text-slate-500">{lp.source_tf}</span></span>
            <span>{p(lp.price)} <span className="text-xs text-slate-500">({lp.price > price ? "+" : ""}{(lp.price - price).toFixed(1)})</span></span>
          </div>
        ))}
      </Card>

      <Card title="Supply / demand zones (ranked)">
        {(snap.top_zones ?? []).map((z, i) => (
          <div key={i} className="flex justify-between py-0.5">
            <span className={tone(z.zone.side)}>{z.zone.tf} {z.zone.side} {z.zone.tests ? `· tested ${z.zone.tests}` : "· fresh"}</span>
            <span>{p(z.zone.low)}–{p(z.zone.high)} <span className="text-xs text-slate-500">{z.score.toFixed(2)}</span></span>
          </div>
        ))}
        {!snap.top_zones?.length && <div className="text-slate-500">no active zone</div>}
      </Card>

      <Card title="Order blocks & fair value gaps near price">
        {(snap.order_blocks ?? []).slice(0, 5).map((o, i) => (
          <div key={`o${i}`} className="flex justify-between py-0.5">
            <span className={tone(o.direction)}>OB {o.tf} {o.direction === "up" ? "bullish" : "bearish"} · {o.status.toLowerCase()}</span>
            <span>{p(o.low)}–{p(o.high)}</span>
          </div>
        ))}
        {(snap.fair_value_gaps ?? []).slice(0, 5).map((g, i) => (
          <div key={`g${i}`} className="flex justify-between py-0.5">
            <span className={tone(g.direction)}>FVG {g.tf} {g.direction === "up" ? "bullish" : "bearish"} · {g.status.toLowerCase()}</span>
            <span>{p(g.low)}–{p(g.high)}</span>
          </div>
        ))}
      </Card>

      <Card title="Sessions">
        {snap.forming?.session && (
          <div className="flex justify-between py-0.5 text-slate-300">
            <span>{snap.forming.session.name} (forming)</span>
            <span>{p(snap.forming.session.low)}–{p(snap.forming.session.high)}</span>
          </div>
        )}
        {(snap.levels ?? []).slice(-6).reverse().map((lv, i) => (
          <div key={i} className="flex justify-between py-0.5">
            <span className="text-slate-400">{lv.name}</span>
            <span>{p(lv.low)}–{p(lv.high)} <span className="text-xs text-slate-500">{fmtTime(lv.end).slice(5, 16)}</span></span>
          </div>
        ))}
      </Card>
    </div>
  );
}
