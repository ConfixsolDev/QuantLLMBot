"use client";

// Replay & verify — play one day of the engine candle by candle and judge it.
//
// The chart shows exactly what the engine knew at the cursor time (every event
// with available_at <= cursor); candles after the cursor are drawn faded so you
// can see what happened next. The check sheet lists every detection of the day:
// mark it ✓ correct / ✗ wrong, add what the engine MISSED, write a note. Your
// verdicts are stored in the database (table structure.reviews).
//
// "Day checks" runs the automatic verification for the day (invariants,
// determinism, no-repaint, independent audit). "Month" runs it for every day
// of the month and shows the scorecard of your verdicts (precision / recall
// per kind) — the number to watch before tuning the config.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import StructureChart, { type Layers } from "@/components/StructureChart";
import {
  deleteReview, fetchChecks, fetchDays, fetchReplayChart, fetchReplayDay, fetchScorecard, saveReview,
  type Chart, type DayChecks, type Detection, type ReplayDay, type Review, type Scorecard, type Verdict,
} from "@/lib/api";

const TFS = ["M1", "M5", "M15", "M30", "H1", "H4"];
const TF_SEC: Record<string, number> = { M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400 };
const LAYER_NAMES: [keyof Layers, string][] = [
  ["trend", "BOS/CHoCH"], ["liquidity", "Liquidity"], ["zones", "Zones"], ["ob", "OB"], ["fvg", "FVG"],
  ["ranges", "Ranges"], ["levels", "Levels"], ["swings", "Swings"], ["other", "Spikes & patterns"], ["vwap", "VWAP"], ["htf", "HTF levels"],
];
// detection groups for the check-sheet filter
const GROUPS: Record<string, string[]> = {
  "HTF levels": ["level_test", "level_rejection", "level_followthrough", "level_held", "level_broken", "level_pattern"],
  "BOS / CHoCH": ["bos", "choch"],
  Liquidity: ["liquidity_sweep", "sweep_failed", "false_break", "liquidity_taken", "equal_highs", "equal_lows"],
  "FVG / OB / zones": ["fvg_created", "order_block_created", "zone_created", "range_formed"],
  "Patterns & spikes": ["pattern_confirmed", "close_spike"],
  Levels: ["session_level", "prior_day_level", "prior_week_level"],
  VWAP: ["vwap_cross", "vwap_band_reject"],
};
const MISSABLE = ["level_rejection", "level_pattern", "level_test", "bos", "choch", "liquidity_sweep", "false_break", "equal_highs", "equal_lows", "fvg_created",
  "order_block_created", "zone_created", "pattern_confirmed", "vwap_band_reject", "other"];
const hhmm = (t: number) => new Date(t * 1000).toISOString().slice(11, 16);
const ok = (b: boolean | undefined) => (b === undefined ? "…" : b ? "✓" : "✗");

export default function ReplayPage() {
  const [days, setDays] = useState<string[]>([]);
  const [date, setDate] = useState("");
  const [tf, setTf] = useState("M5");
  const [layers, setLayers] = useState<Layers>({
    trend: true, liquidity: true, zones: false, ob: true, fvg: true, ranges: false, levels: true, swings: true,
    other: true, vwap: true, htf: true,
  });
  const [day, setDay] = useState<ReplayDay | null>(null);
  const [cursor, setCursor] = useState(0);
  const [chart, setChart] = useState<Chart | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [focus, setFocus] = useState<number | undefined>();
  const [tab, setTab] = useState<"sheet" | "checks" | "month">("sheet");
  const [groups, setGroups] = useState<string[]>(Object.keys(GROUPS).filter((g) => g !== "VWAP" && g !== "Levels"));
  const [onlyPast, setOnlyPast] = useState(true);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [checks, setChecks] = useState<DayChecks | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // ---- days with data; default to the latest
  useEffect(() => {
    fetchDays().then((d) => { setDays(d.days); if (d.days.length) setDate(d.days[0]); })
      .catch((e) => setError(String(e)));
  }, []);

  // ---- load a day (engine run on the backend, ~1-2 s)
  useEffect(() => {
    if (!date) return;
    setBusy("running the engine over the day…"); setDay(null); setChecks(null); setPlaying(false);
    fetchReplayDay(date).then((d) => {
      setDay(d); setCursor(d.start + 2 * 3600); setReviews(Object.fromEntries(d.reviews.map((r) => [r.id, r])));
      setChecks(d.checks); setBusy(""); setError("");
    }).catch((e) => { setBusy(""); setError(String(e)); });
  }, [date]);

  // ---- chart at the cursor (debounced while scrubbing)
  const reqRef = useRef(0);
  useEffect(() => {
    if (!day || !cursor) return;
    const id = ++reqRef.current;
    const h = setTimeout(() => {
      fetchReplayChart(day.date, tf, cursor, 400).then((c) => { if (id === reqRef.current) setChart(c); })
        .catch((e) => setError(String(e)));
    }, 60);
    return () => clearTimeout(h);
  }, [day, tf, cursor]);

  // ---- play: one chart candle per tick
  useEffect(() => {
    if (!playing || !day) return;
    const h = setInterval(() => {
      setCursor((c) => {
        const n = c + TF_SEC[tf];
        if (n >= day.end) { setPlaying(false); return day.end; }
        return n;
      });
    }, 700 / speed);
    return () => clearInterval(h);
  }, [playing, speed, tf, day]);

  // ---- keyboard: ← → step, space play
  const step = useCallback((k: number) => {
    if (!day) return;
    setCursor((c) => Math.min(day.end, Math.max(day.start, c - (c % TF_SEC[tf]) + k * TF_SEC[tf])));
  }, [day, tf]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return;
      if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === " ") { e.preventDefault(); setPlaying((p) => !p); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [step]);

  // ---- verdicts
  const judge = async (d: { id: string; kind: string; tf: string; time: number }, verdict: Verdict | null, note?: string) => {
    if (!day) return;
    const prev = reviews[d.id];
    try {
      if (verdict === null) {
        await deleteReview(d.id);
        const next = { ...reviews }; delete next[d.id]; setReviews(next);
      } else {
        const r: Review = { id: d.id, kind: d.kind, tf: d.tf, time: d.time, verdict, note: note ?? prev?.note ?? "" };
        await saveReview({ ...r, day: day.date });
        setReviews({ ...reviews, [d.id]: r });
      }
    } catch (e) { setError(String(e)); }
  };

  const kindsOn = useMemo(() => new Set(groups.flatMap((g) => GROUPS[g])), [groups]);
  const rows = useMemo(() => (day?.detections ?? []).filter((d) => kindsOn.has(d.kind) && (!onlyPast || d.available_at <= cursor)),
    [day, kindsOn, onlyPast, cursor]);
  const missed = Object.values(reviews).filter((r) => r.verdict === "missed");
  const judged = Object.values(reviews).filter((r) => r.verdict !== "missed");

  const runChecks = async () => {
    if (!day) return;
    setBusy("running automatic checks…");
    try { setChecks(await fetchChecks(day.date)); } catch (e) { setError(String(e)); }
    setBusy("");
  };

  return (
    <main className="flex h-screen flex-col gap-2 p-3">
      <header className="flex flex-wrap items-center gap-3">
        <a href="/" className="text-sm text-slate-400 hover:text-slate-200">← live</a>
        <h1 className="text-lg font-semibold text-gold">Replay &amp; verify</h1>
        <button className="btn" onClick={() => { const i = days.indexOf(date); if (i < days.length - 1) setDate(days[i + 1]); }}>‹ day</button>
        <select value={date} onChange={(e) => setDate(e.target.value)} className="rounded-md bg-panel px-2 py-1 text-sm">
          {days.map((d) => <option key={d} value={d}>{d} {new Date(d + "T12:00:00Z").toUTCString().slice(0, 3)}</option>)}
        </select>
        <button className="btn" onClick={() => { const i = days.indexOf(date); if (i > 0) setDate(days[i - 1]); }}>day ›</button>
        <span className="text-xs text-slate-500">UTC day · engine warmed up on the 10 days before</span>
        {busy && <span className="text-xs text-sky-300">{busy}</span>}
        {error && <span className="text-xs text-rose-400">{error}</span>}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {TFS.map((t) => (
          <button key={t} onClick={() => setTf(t)}
            className={`rounded-md px-3 py-1 text-sm ${t === tf ? "bg-gold text-ink" : "bg-panel text-slate-300 hover:bg-slate-800"}`}>{t}</button>
        ))}
        <span className="mx-1 h-5 w-px bg-slate-700" />
        {LAYER_NAMES.map(([k, label]) => (
          <label key={k} className="flex cursor-pointer items-center gap-1 text-xs text-slate-300">
            <input type="checkbox" checked={layers[k]} onChange={() => setLayers({ ...layers, [k]: !layers[k] })} />{label}
          </label>
        ))}
      </div>

      {day && (
        <div className="flex items-center gap-2">
          <button className="btn" title="day start" onClick={() => setCursor(day.start)}>⏮</button>
          <button className="btn" title="step back (←)" onClick={() => step(-1)}>◀</button>
          <button className="btn w-16" title="play / pause (space)" onClick={() => setPlaying(!playing)}>{playing ? "❚❚" : "▶ play"}</button>
          <button className="btn" title="step forward (→)" onClick={() => step(1)}>▶</button>
          <button className="btn" title="day end" onClick={() => setCursor(day.end)}>⏭</button>
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="rounded-md bg-panel px-1 py-1 text-xs">
            {[0.5, 1, 2, 4, 8].map((s) => <option key={s} value={s}>{s}×</option>)}
          </select>
          <input type="range" min={day.start} max={day.end} step={60} value={cursor}
            onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)); }} className="flex-1 accent-amber-400" />
          <span className="w-28 text-right font-mono text-sm text-amber-300">{hhmm(cursor)} UTC</span>
          <TrendStrip chart={chart} />
        </div>
      )}

      <div className="flex min-h-0 flex-1 gap-3">
        <div className="card min-w-0 flex-1 p-1">
          <StructureChart chart={chart} layers={layers} fitKey={`${date}:${tf}`} cursor={cursor} focus={focus} />
        </div>
        <aside className="flex w-[430px] shrink-0 flex-col gap-2 overflow-hidden">
          <div className="flex gap-1">
            {([["sheet", `Check sheet (${judged.length}/${day?.detections.length ?? 0})`], ["checks", "Day checks"], ["month", "Month"]] as const).map(([k, l]) => (
              <button key={k} onClick={() => setTab(k)}
                className={`flex-1 rounded-md px-2 py-1 text-xs ${tab === k ? "bg-gold text-ink" : "bg-panel text-slate-300"}`}>
                {l}{k === "checks" && checks ? ` ${allOk(checks) ? "✓" : "✗"}` : ""}
              </button>
            ))}
          </div>
          <div className="card min-h-0 flex-1 overflow-y-auto text-sm">
            {tab === "sheet" && day && (
              <CheckSheet rows={rows} reviews={reviews} missed={missed} cursor={cursor} groups={groups} setGroups={setGroups}
                onlyPast={onlyPast} setOnlyPast={setOnlyPast} judge={judge}
                jump={(d) => { setPlaying(false); setCursor(Math.max(cursor, d.available_at)); setFocus(d.time + Math.random() * 1e-3); }}
                addMissed={(kind, mtf, note) => judge({ id: `missed-${day.date}-${Date.now()}`, kind, tf: mtf, time: cursor }, "missed", note)} />
            )}
            {tab === "checks" && <ChecksView checks={checks} run={runChecks} busy={!!busy} />}
            {tab === "month" && date && <MonthView date={date} days={days} open={(d) => { setDate(d); setTab("sheet"); }} />}
          </div>
        </aside>
      </div>
    </main>
  );
}

function TrendStrip({ chart }: { chart: Chart | null }) {
  if (!chart?.trend) return null;
  return (
    <span className="flex gap-2 text-xs">
      {Object.entries(chart.trend).map(([t, v]) => (
        <span key={t} className={v.state === "up" ? "text-emerald-400" : v.state === "down" ? "text-rose-400" : "text-slate-500"}>
          {t}{v.state === "up" ? "▲" : v.state === "down" ? "▼" : "–"}
        </span>
      ))}
    </span>
  );
}

function CheckSheet({ rows, reviews, missed, cursor, groups, setGroups, onlyPast, setOnlyPast, judge, jump, addMissed }: {
  rows: Detection[]; reviews: Record<string, Review>; missed: Review[]; cursor: number;
  groups: string[]; setGroups: (g: string[]) => void; onlyPast: boolean; setOnlyPast: (b: boolean) => void;
  judge: (d: { id: string; kind: string; tf: string; time: number }, v: Verdict | null, note?: string) => void;
  jump: (d: Detection) => void; addMissed: (kind: string, tf: string, note: string) => void;
}) {
  const [mk, setMk] = useState("liquidity_sweep");
  const [mtf, setMtf] = useState("M5");
  const [mnote, setMnote] = useState("");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1">
        {Object.keys(GROUPS).map((g) => (
          <button key={g} onClick={() => setGroups(groups.includes(g) ? groups.filter((x) => x !== g) : [...groups, g])}
            className={`rounded-full px-2 py-0.5 text-[11px] ${groups.includes(g) ? "bg-sky-900 text-sky-200" : "bg-slate-800 text-slate-500"}`}>{g}</button>
        ))}
        <label className="ml-auto flex items-center gap-1 text-[11px] text-slate-400">
          <input type="checkbox" checked={onlyPast} onChange={() => setOnlyPast(!onlyPast)} />up to cursor
        </label>
      </div>
      {rows.length === 0 && <div className="text-slate-500">No detections {onlyPast ? "up to the cursor" : ""} in the selected groups.</div>}
      {rows.map((d) => {
        const r = reviews[d.id];
        return (
          <div key={d.id} className={`rounded-md border px-2 py-1 ${r?.verdict === "correct" ? "border-emerald-800 bg-emerald-950/30"
            : r?.verdict === "wrong" ? "border-rose-800 bg-rose-950/30" : "border-slate-800"} ${d.available_at > cursor ? "opacity-50" : ""}`}>
            <div className="flex items-start gap-2">
              <button onClick={() => jump(d)} className="flex-1 text-left hover:text-gold" title="show on the chart">
                <span className="font-mono text-xs text-slate-500">{hhmm(d.available_at)}</span> {d.text}
              </button>
              <button title="correct" onClick={() => judge(d, r?.verdict === "correct" ? null : "correct")}
                className={`rounded px-1.5 ${r?.verdict === "correct" ? "bg-emerald-600 text-white" : "bg-slate-800 text-emerald-400"}`}>✓</button>
              <button title="wrong" onClick={() => judge(d, r?.verdict === "wrong" ? null : "wrong")}
                className={`rounded px-1.5 ${r?.verdict === "wrong" ? "bg-rose-600 text-white" : "bg-slate-800 text-rose-400"}`}>✗</button>
            </div>
            {r && (
              <input defaultValue={r.note} placeholder="note (why?)" onBlur={(e) => e.target.value !== r.note && judge(d, r.verdict, e.target.value)}
                className="mt-1 w-full rounded bg-slate-900 px-1 py-0.5 text-xs text-slate-300" />
            )}
          </div>
        );
      })}

      <div className="mt-2 border-t border-slate-800 pt-2">
        <h4 className="mb-1 text-xs font-semibold uppercase text-slate-400">Missed by the engine (at the cursor {hhmm(cursor)})</h4>
        <div className="flex gap-1">
          <select value={mk} onChange={(e) => setMk(e.target.value)} className="rounded bg-slate-900 px-1 text-xs">
            {MISSABLE.map((k) => <option key={k}>{k}</option>)}
          </select>
          <select value={mtf} onChange={(e) => setMtf(e.target.value)} className="rounded bg-slate-900 px-1 text-xs">
            {TFS.map((t) => <option key={t}>{t}</option>)}
          </select>
          <input value={mnote} onChange={(e) => setMnote(e.target.value)} placeholder="what was missed"
            className="flex-1 rounded bg-slate-900 px-1 text-xs" />
          <button className="btn" onClick={() => { addMissed(mk, mtf, mnote); setMnote(""); }}>+ add</button>
        </div>
        {missed.map((m) => (
          <div key={m.id} className="mt-1 flex items-center gap-2 text-xs text-amber-300">
            <span className="font-mono text-slate-500">{m.time ? hhmm(m.time) : ""}</span>
            <span className="flex-1">{m.tf} {m.kind} — {m.note}</span>
            <button className="text-slate-500 hover:text-rose-400" onClick={() => judge({ id: m.id, kind: m.kind, tf: m.tf, time: m.time ?? 0 }, null)}>remove</button>
          </div>
        ))}
      </div>
    </div>
  );
}

const allOk = (c: DayChecks) => c.invariants.ok && c.determinism.ok && c.no_repaint.ok && c.audit.ok && (c.clock?.ok ?? true);

function ChecksView({ checks, run, busy }: { checks: DayChecks | null; run: () => void; busy: boolean }) {
  if (!checks) return (
    <div className="flex flex-col gap-2 text-slate-300">
      <p>Automatic proof that the deterministic code behaved for this day:</p>
      <ul className="list-disc pl-5 text-xs text-slate-400">
        <li><b>Invariants</b> — geometry that must always hold (FVG gap, BOS beyond the level, sweep wick beyond and close back, VWAP cross and band-reject geometry…)</li>
        <li><b>Determinism</b> — a second run gives byte-identical events</li>
        <li><b>No repaint</b> — runs stopped at 3 points in the day reproduce exactly what the full run had said by then</li>
        <li><b>Independent audit</b> — every event re-checked against candles rebuilt by separate code</li>
        <li><b>Clock</b> — gold's daily break starts at 17:00 New York, so bar times are real UTC</li>
      </ul>
      <button className="btn self-start" disabled={busy} onClick={run}>Run checks for this day</button>
    </div>
  );
  const Row = ({ name, good, detail }: { name: string; good: boolean; detail: string }) => (
    <div className="flex justify-between border-b border-slate-800/60 py-1">
      <span>{name}</span><span className={good ? "text-emerald-400" : "text-rose-400"}>{good ? "✓ pass" : "✗ FAIL"} <span className="text-xs text-slate-500">{detail}</span></span>
    </div>
  );
  return (
    <div className="flex flex-col gap-1">
      <div className="mb-1 text-xs text-slate-400">{checks.date} · {checks.events} events available during the day</div>
      <Row name="Invariants" good={checks.invariants.ok} detail={`${checks.invariants.violations.length} violations`} />
      <Row name="Determinism" good={checks.determinism.ok} detail="2 runs identical" />
      <Row name="No repaint" good={checks.no_repaint.ok} detail={`cuts ${checks.no_repaint.cuts.map(hhmm).join(", ")}`} />
      {checks.clock && <Row name="Clock (17:00 NY break)" good={checks.clock.ok}
        detail={checks.clock.breaks.length ? checks.clock.breaks.map((b) => `break at ${b.ny} NY`).join(", ") : "no daily break this day"} />}
      <Row name="Independent audit" good={checks.audit.ok} detail={`${checks.audit.checked} checked, ${checks.audit.failed} failed`} />
      {checks.invariants.violations.map((v, i) => <div key={i} className="text-xs text-rose-300">{v}</div>)}
      {Object.entries(checks.audit.examples).map(([k, v]) => <div key={k} className="text-xs text-rose-300">{k}: {v.join(" · ")}</div>)}
    </div>
  );
}

function MonthView({ date, days, open }: { date: string; days: string[]; open: (d: string) => void }) {
  const month = date.slice(0, 7);
  const mdays = days.filter((d) => d.startsWith(month)).sort();
  const [res, setRes] = useState<Record<string, DayChecks | string>>({});
  const [score, setScore] = useState<Scorecard | null>(null);
  const [running, setRunning] = useState(false);
  const stop = useRef(false);
  useEffect(() => {
    fetchScorecard(`${month}-01`, `${month}-31`).then(setScore).catch(() => setScore(null));
    setRes({});
  }, [month]);
  const runAll = async () => {
    setRunning(true); stop.current = false;
    for (const d of mdays) {
      if (stop.current) break;
      try { const c = await fetchChecks(d); setRes((r) => ({ ...r, [d]: c })); }
      catch (e) { setRes((r) => ({ ...r, [d]: String(e) })); }
    }
    setRunning(false);
  };
  const done = Object.values(res).filter((v) => typeof v !== "string") as DayChecks[];
  return (
    <div className="flex flex-col gap-3">
      <section>
        <div className="mb-1 flex items-center gap-2">
          <h4 className="text-xs font-semibold uppercase text-slate-400">Automatic checks · {month}</h4>
          {!running ? <button className="btn ml-auto" onClick={runAll}>Check all {mdays.length} days</button>
            : <button className="btn ml-auto" onClick={() => { stop.current = true; }}>stop</button>}
        </div>
        {done.length > 0 && (
          <div className="mb-1 text-xs text-slate-400">{done.filter(allOk).length}/{done.length} days fully passing · {done.reduce((s, c) => s + c.events, 0)} events</div>
        )}
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500"><th className="text-left">day</th><th>inv</th><th>det</th><th>repaint</th><th>audit</th><th>clock</th><th>events</th></tr></thead>
          <tbody>
            {mdays.map((d) => {
              const c = res[d];
              const cc = typeof c === "string" ? undefined : c;
              return (
                <tr key={d} className="cursor-pointer border-b border-slate-800/60 hover:bg-slate-800/40" onClick={() => open(d)}>
                  <td className="py-0.5">{d}</td>
                  {typeof c === "string" ? <td colSpan={6} className="text-rose-400">{c}</td> : <>
                    <td className="text-center">{ok(cc?.invariants.ok)}</td><td className="text-center">{ok(cc?.determinism.ok)}</td>
                    <td className="text-center">{ok(cc?.no_repaint.ok)}</td><td className="text-center">{ok(cc?.audit.ok)}</td><td className="text-center">{ok(cc?.clock?.ok)}</td>
                    <td className="text-center text-slate-400">{cc?.events ?? ""}</td></>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase text-slate-400">Your verdicts · {month} ({score?.days_reviewed ?? 0} days reviewed)</h4>
        {!score?.kinds.length ? <div className="text-xs text-slate-500">No verdicts yet: mark detections ✓ / ✗ on the check sheet.</div> : (
          <table className="w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left">kind</th><th>✓</th><th>✗</th><th>missed</th><th>precision</th><th>recall</th></tr></thead>
            <tbody>
              {score.kinds.map((k) => (
                <tr key={k.kind} className="border-b border-slate-800/60">
                  <td className="py-0.5">{k.kind}</td><td className="text-center text-emerald-400">{k.correct}</td>
                  <td className="text-center text-rose-400">{k.wrong}</td><td className="text-center text-amber-300">{k.missed}</td>
                  <td className="text-center">{k.precision === null ? "–" : `${Math.round(k.precision * 100)}%`}</td>
                  <td className="text-center">{k.recall === null ? "–" : `${Math.round(k.recall * 100)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-1 text-[11px] text-slate-500">precision = ✓ / (✓ + ✗): how often a detection is right. recall = ✓ / (✓ + missed): how much real structure it catches.</p>
      </section>
    </div>
  );
}
