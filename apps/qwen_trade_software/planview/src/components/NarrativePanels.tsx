"use client";

import type { PlanViewModel } from "@/lib/viewModel";
import { TIMEFRAME_ROLE_EXPLAINER, price as fmt } from "@/lib/translate";

/**
 * The explanation half of the screen: location, what would change the read,
 * the top-down narrative, the last closed hour, and the technical panels.
 *
 * Everything here is derived in the ViewModel. These components render and do
 * not compute, which is what stops two panels disagreeing about the same fact.
 */

export function PriceLocationStrip({ vm }: { vm: PlanViewModel }) {
  const { location } = vm;
  if (location.price == null) return null;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <h3 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">
        Where price is
      </h3>

      <div className="flex items-end justify-between gap-3 text-sm">
        <div className="text-center">
          <div className="text-[11px] text-zinc-500">Support</div>
          <div className="font-mono text-rose-300">{fmt(location.nearestSupport)}</div>
          {location.distanceFromSupport != null && (
            <div className="text-[11px] text-zinc-600">
              {location.distanceFromSupport.toFixed(2)} away
            </div>
          )}
        </div>

        <div className="flex-1 relative h-8">
          <div className="absolute inset-x-0 top-1/2 h-px bg-zinc-700" />
          <div className="absolute left-1/2 -translate-x-1/2 -top-1 text-center">
            <div className="font-mono text-zinc-100">{fmt(location.price)}</div>
            <div className="w-px h-3 bg-zinc-400 mx-auto" />
          </div>
        </div>

        <div className="text-center">
          <div className="text-[11px] text-zinc-500">Resistance</div>
          <div className="font-mono text-emerald-300">{fmt(location.nearestResistance)}</div>
          {location.distanceToResistance != null && (
            <div className="text-[11px] text-zinc-600">
              {location.distanceToResistance.toFixed(2)} away
            </div>
          )}
        </div>
      </div>

      <p className="mt-3 pt-3 border-t border-zinc-800 text-sm text-zinc-300">
        {location.explanation}
      </p>
    </section>
  );
}

export function ChangeMyMindCard({ vm }: { vm: PlanViewModel }) {
  const { changeMyMind } = vm;
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <h3 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">
        What would change my mind
      </h3>

      <div className="text-sm text-zinc-300 mb-3">{changeMyMind.thesis}</div>

      <div className="rounded border border-rose-900/60 bg-rose-950/20 px-3 py-2 mb-3">
        <div className="text-[11px] uppercase tracking-wide text-rose-400/80 mb-0.5">
          Kills the idea
        </div>
        <div className="text-sm text-zinc-200">{changeMyMind.hardInvalidation}</div>
      </div>

      {changeMyMind.warnings.length > 0 && (
        <div className="mb-3">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
            Weakening it now
          </div>
          <ul className="space-y-0.5">
            {changeMyMind.warnings.map((w) => (
              <li key={w} className="text-sm text-amber-300/80 flex gap-2">
                <span className="mt-[2px]">!</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="text-[11px] text-zinc-500">
        Opposite case activates: <span className="text-zinc-400">{changeMyMind.oppositeActivation}</span>
      </div>
    </section>
  );
}

export function TimeframeNarrative({ vm }: { vm: PlanViewModel }) {
  if (!vm.timeframes.length) return null;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <h3 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">
        Top-down read
      </h3>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {vm.timeframes.map((tf) => {
          // Colour the whole card by side, not just the label -- the lean is
          // the fact worth seeing from across the room.
          const tone =
            tf.bias === "BULLISH"
              ? "border-emerald-800/70 bg-emerald-950/25"
              : tf.bias === "BEARISH"
                ? "border-rose-800/70 bg-rose-950/25"
                : "border-zinc-800 bg-zinc-900/20";
          const label =
            tf.bias === "BULLISH"
              ? "text-emerald-300"
              : tf.bias === "BEARISH"
                ? "text-rose-300"
                : "text-zinc-500";
          return (
            <div key={tf.timeframe} className={`rounded border p-3 ${tone}`}>
              <div className="flex items-baseline justify-between mb-1">
                <span className="font-semibold text-zinc-100">{tf.timeframe}</span>
                <span className={`text-xs font-semibold ${label}`}>
                  {tf.bias === "NEUTRAL" ? "no lean" : tf.bias}
                </span>
              </div>
              {/*
                Role only. The planner's own note already restates the
                explainer, so appending it produced "Bias — which way the day
                leans and the levels that matter — Which way the day leans".
              */}
              <div className="text-[11px] text-zinc-500 mb-1">
                {tf.role}
                {TIMEFRAME_ROLE_EXPLAINER[tf.timeframe]
                  ? ` — ${TIMEFRAME_ROLE_EXPLAINER[tf.timeframe]}`
                  : ""}
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-3 pt-3 border-t border-zinc-800 text-sm text-zinc-300">
        {vm.timeframeInterpretation}
      </p>
    </section>
  );
}

const SEVERITY_TONE: Record<string, string> = {
  NONE: "text-zinc-500",
  MINOR: "text-zinc-300",
  MODERATE: "text-amber-300",
  MAJOR: "text-orange-300",
  INVALIDATED: "text-rose-300",
};

export function LastHourReview({ vm }: { vm: PlanViewModel }) {
  const hour = vm.lastHour;
  if (!hour) return null;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm uppercase tracking-wide text-zinc-500">Last closed hour</h3>
        <span className={`text-xs font-medium ${SEVERITY_TONE[hour.severity]}`}>
          {hour.severity === "NONE" ? "no material change" : hour.severity.toLowerCase()}
          {hour.confidenceDelta !== 0 && (
            <span className="text-zinc-600 ml-2 font-mono">
              {hour.confidenceDelta > 0 ? "+" : ""}
              {hour.confidenceDelta}
            </span>
          )}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 mb-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-zinc-500">Expected</div>
          <div className="text-sm text-zinc-300">{hour.expected}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-zinc-500">What happened</div>
          <div className="text-sm text-zinc-300">{hour.observed}</div>
        </div>
      </div>

      {hour.ohlc && (
        <div className="text-xs font-mono text-zinc-500 mb-3">
          O {fmt(hour.ohlc.o)} · H {fmt(hour.ohlc.h)} · L {fmt(hour.ohlc.l)} · C{" "}
          {fmt(hour.ohlc.c)}
        </div>
      )}

      {hour.levelsTouched.length > 0 && (
        <div className="mb-3">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
            Levels tested
          </div>
          <ul className="space-y-0.5">
            {hour.levelsTouched.map((l) => (
              <li key={l} className="text-sm text-zinc-400">
                {l}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-sm text-zinc-300 pt-3 border-t border-zinc-800">
        {hour.interpretation}. {hour.nextConfirmation}
      </p>
    </section>
  );
}

export function ConfidencePanel({ vm }: { vm: PlanViewModel }) {
  const plan = vm.primary;
  if (!plan) return null;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <h3 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">
        Why this confidence
      </h3>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-emerald-500/70 mb-1">
            Supporting
          </div>
          {vm.confidencePositives.length ? (
            <ul className="space-y-0.5">
              {vm.confidencePositives.map((p) => (
                <li key={p} className="text-sm text-zinc-300 flex gap-2">
                  <span className="text-emerald-500 mt-[2px]">+</span>
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-600">Nothing recorded.</p>
          )}
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-rose-500/70 mb-1">
            Against
          </div>
          {vm.confidenceNegatives.length ? (
            <ul className="space-y-0.5">
              {vm.confidenceNegatives.map((n) => (
                <li key={n} className="text-sm text-zinc-300 flex gap-2">
                  <span className="text-rose-500 mt-[2px]">−</span>
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-600">Nothing counting against it.</p>
          )}
        </div>
      </div>
    </section>
  );
}

export function DoDontCard({ vm }: { vm: PlanViewModel }) {
  if (!vm.doList.length && !vm.dontList.length) return null;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-emerald-500/70 mb-1">Do</div>
          <ul className="space-y-1">
            {vm.doList.map((d) => (
              <li key={d} className="text-sm text-zinc-300 flex gap-2">
                <span className="text-emerald-500 mt-[2px]">✓</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-rose-500/70 mb-1">Don&apos;t</div>
          <ul className="space-y-1">
            {vm.dontList.map((d) => (
              <li key={d} className="text-sm text-zinc-400 flex gap-2">
                <span className="text-rose-500 mt-[2px]">×</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/**
 * Technical details, always open and written in English.
 *
 * The first version hid the raw panels behind a toggle, which solved the wrong
 * problem: the issue was never that the information was present, it was that it
 * was written in the system's vocabulary. Hidden jargon is still jargon.
 *
 * So this stays visible and explains, in order: what the plan expected, what
 * price actually did, and where the two parted company. The raw panels sit
 * underneath for when a number needs checking.
 */
export function TechnicalDetails({
  vm,
  children,
}: {
  vm: PlanViewModel;
  children?: React.ReactNode;
}) {
  const hour = vm.lastHour;

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 h-full">
      <h3 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">
        Plan versus reality
      </h3>

      {hour ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-zinc-500">
                We expected
              </div>
              <div className="text-sm text-zinc-300">{hour.expected}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-zinc-500">
                What happened
              </div>
              <div className="text-sm text-zinc-300">{hour.observed}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-zinc-500">
                Effect on the plan
              </div>
              <div className={`text-sm ${SEVERITY_TONE[hour.severity]}`}>
                {hour.severity === "NONE"
                  ? "No material change"
                  : hour.severity === "INVALIDATED"
                    ? "The plan was invalidated"
                    : `${hour.severity.toLowerCase()} change`}
                {hour.confidenceDelta !== 0 && (
                  <span className="text-zinc-500 font-mono ml-2">
                    {hour.confidenceDelta > 0 ? "+" : ""}
                    {hour.confidenceDelta} confidence
                  </span>
                )}
              </div>
            </div>
          </div>

          {hour.levelsTouched.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
                Levels price tested
              </div>
              <ul className="space-y-0.5">
                {hour.levelsTouched.map((l) => (
                  <li key={l} className="text-sm text-zinc-400">
                    {l}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hour.ohlc && (
            <div className="text-xs font-mono text-zinc-600">
              hour O {fmt(hour.ohlc.o)} · H {fmt(hour.ohlc.h)} · L {fmt(hour.ohlc.l)} · C{" "}
              {fmt(hour.ohlc.c)}
            </div>
          )}

          <p className="text-sm text-zinc-300 pt-2 border-t border-zinc-800">
            {hour.nextConfirmation}
          </p>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">No closed hour to review yet.</p>
      )}

      {children ? <div className="mt-4 space-y-4">{children}</div> : null}
    </section>
  );
}
