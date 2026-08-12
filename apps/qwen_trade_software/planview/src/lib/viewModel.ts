/**
 * One builder. Every value the screen shows is computed here, once.
 *
 * Why this exists
 * ---------------
 * On 2026-08-12 the dashboard contradicted itself in three places at the same
 * time:
 *
 *   "2 trades closed · net +232.50"   beside a funnel reading  Filled 1
 *   "BUY — all timeframes agree"      beside D1/H1/M15 all reading  NO LEAN
 *   both branches "TARGET REACHED"    beside an hour reading  invalidated
 *
 * None of those were data problems. Each was two components deriving the same
 * fact from different places and disagreeing. A trader who catches a dashboard
 * lying once stops trusting all of it, which is worse than showing less.
 *
 * The rule this file enforces: ONE NUMBER, ONE OWNER. Components receive values
 * and render them. They never re-derive a figure a sibling also derives.
 *
 * This layer explains the planner. It never decides anything: bias, levels,
 * triggers, invalidation and readiness all come from the deterministic backend
 * exactly as given.
 */

import type {
  DayBranches,
  ExecutionFunnel,
  HourlyUpdate,
  PlanBranch,
  PlannerState,
  TradeIdeaStack,
} from "./types";
import {
  type ConfidenceLabel,
  type TradeStatus,
  biasLabel,
  changeSeverity,
  confidenceLabel,
  describeEvidence,
  describeHourOutcome,
  describeState,
  describeTrigger,
  levelEvent,
  levelName,
  tradeStatusFor,
} from "./translate";

export type LocationClass =
  | "AT_SUPPORT"
  | "NEAR_SUPPORT"
  | "MID_RANGE"
  | "NEAR_RESISTANCE"
  | "AT_RESISTANCE"
  | "INSIDE_ENTRY_ZONE"
  | "UNKNOWN";

export interface MarketBriefVM {
  symbol: string;
  price: number | null;
  session: string;
  sessionHour: number | null;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  tradeStatus: TradeStatus;
  location: LocationClass;
  confirmation: string;
  condition: string;
}

export interface PlanVM {
  direction: "BUY" | "SELL" | "NONE";
  state: string;
  stateText: string;
  thesis: string;
  trigger: string;
  triggerPrice: number | null;
  invalidation: number | null;
  targets: number[];
  evidence: string[];
  confidence: number;
  confidenceLabel: ConfidenceLabel;
  isActive: boolean;
  activationCondition?: string;
}

export interface PriceLocationVM {
  price: number | null;
  nearestSupport: number | null;
  nearestResistance: number | null;
  distanceFromSupport: number | null;
  distanceToResistance: number | null;
  entryZone: [number, number] | null;
  classification: LocationClass;
  explanation: string;
}

export interface RightNowVM {
  action: TradeStatus;
  headline: string;
  reason: string;
  waitingFor: string[];
  avoid: string[];
}

export interface TimeframeVM {
  timeframe: string;
  role: string;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  state: string;
  summary: string;
  level: number | null;
}

export interface LastHourVM {
  hourId: string;
  expected: string;
  observed: string;
  interpretation: string;
  ohlc: { o: number; h: number; l: number; c: number } | null;
  levelsTouched: string[];
  severity: ReturnType<typeof changeSeverity>;
  confidenceDelta: number;
  nextConfirmation: string;
}

export interface PlanViewModel {
  brief: MarketBriefVM;
  rightNow: RightNowVM;
  primary: PlanVM | null;
  alternative: PlanVM | null;
  location: PriceLocationVM;
  timeframes: TimeframeVM[];
  timeframeInterpretation: string;
  lastHour: LastHourVM | null;
  confidencePositives: string[];
  confidenceNegatives: string[];
  doList: string[];
  dontList: string[];
  changeMyMind: {
    thesis: string;
    hardInvalidation: string;
    warnings: string[];
    oppositeActivation: string;
  };
}

/** How close counts as "at" a level, in price units. Gold moves in dollars. */
const AT_LEVEL_DISTANCE = 1.5;
const NEAR_LEVEL_DISTANCE = 5.0;

function num(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Which branch leads.
 *
 * Deliberately NOT "the one with the higher confidence". A spent or invalidated
 * branch must never lead regardless of the number attached to it, and showing
 * two live branches at equal weight is the presentational error the spec calls
 * out: it implies two equally actionable trades when at most one is real.
 */
function choosePrimary(branches: DayBranches | null | undefined): {
  primary: PlanBranch | null;
  alternative: PlanBranch | null;
} {
  if (!branches) return { primary: null, alternative: null };
  const bull = branches.bullish ?? null;
  const bear = branches.bearish ?? null;
  if (!bull) return { primary: bear, alternative: null };
  if (!bear) return { primary: bull, alternative: null };

  const rank = (b: PlanBranch): number => {
    switch (String(b.state)) {
      case "confirmed":
        return 4;
      case "likely":
        return 3;
      case "armed":
        return 2;
      case "spent":
        return 1;
      default:
        return 0; // invalidated
    }
  };

  const bullRank = rank(bull);
  const bearRank = rank(bear);
  if (bullRank !== bearRank) {
    return bullRank > bearRank
      ? { primary: bull, alternative: bear }
      : { primary: bear, alternative: bull };
  }
  // Same state: fall back to the side the planner itself nominated, then
  // confidence. Never a coin toss in the component.
  const called = String(branches.callable_side ?? "").toLowerCase();
  if (called === "buy") return { primary: bull, alternative: bear };
  if (called === "sell") return { primary: bear, alternative: bull };
  return Number(bull.confidence ?? 0) >= Number(bear.confidence ?? 0)
    ? { primary: bull, alternative: bear }
    : { primary: bear, alternative: bull };
}

function toPlanVM(branch: PlanBranch | null, isPrimary: boolean): PlanVM | null {
  if (!branch) return null;
  const state = String(branch.state ?? "unknown");
  const confidence = Number(branch.confidence ?? 0);
  const direction = String(branch.side ?? "").toLowerCase() === "buy" ? "BUY" : "SELL";
  const active = state !== "invalidated" && state !== "spent";

  return {
    direction,
    state,
    stateText: describeState(state),
    thesis: String(branch.reason ?? "").trim() || describeState(state),
    trigger: describeTrigger(branch.trigger_text),
    triggerPrice: num(branch.trigger_price),
    invalidation: num(branch.invalidation),
    targets: Array.isArray(branch.targets)
      ? branch.targets.map((t) => Number(t)).filter((t) => Number.isFinite(t))
      : [],
    evidence: Array.isArray(branch.evidence)
      ? branch.evidence.map((e) => describeEvidence(String(e)))
      : [],
    confidence,
    confidenceLabel: confidenceLabel(confidence),
    isActive: active,
    activationCondition: isPrimary ? undefined : activationText(branch, state),
  };
}

/**
 * When the alternative case becomes a real plan.
 *
 * Deliberately does NOT synthesise a sentence from direction + trigger_price +
 * trigger_text. A first attempt did, and produced "Below 4397.50, after a close
 * decisively above resistance" for a sell branch -- two halves that contradict
 * each other, because the branch's own trigger text already describes the
 * direction and prefixing it with an inferred one reverses the meaning.
 *
 * The planner's own trigger wording is authoritative; the price is quoted
 * alongside it rather than folded into a phrase we invent.
 */
function activationText(branch: PlanBranch, state: string): string {
  if (state === "spent") {
    return "Already played out — this case needs a fresh setup, not a re-entry.";
  }
  if (state === "invalidated") {
    return "Invalidated — no longer available.";
  }
  const trigger = describeTrigger(branch.trigger_text);
  const level = num(branch.trigger_price);
  return level == null ? trigger : `${trigger}, at ${level.toFixed(2)}`;
}

/**
 * Where price sits relative to the levels the plan actually cares about.
 *
 * Uses only the branch's own levels -- targets and invalidation -- rather than
 * the full M1..D1 level map. The nearest level by raw distance is often an M1
 * artefact the plan has no opinion about, and calling that "resistance" would
 * be inventing significance the planner never claimed.
 */
function buildLocation(
  price: number | null,
  primary: PlanBranch | null,
  stack: TradeIdeaStack | undefined,
): PriceLocationVM {
  const zone = stack?.m15?.pullback_zone;
  const entryZone: [number, number] | null =
    Array.isArray(zone) && zone.length === 2 && zone.every((v) => Number.isFinite(Number(v)))
      ? [Number(zone[0]), Number(zone[1])]
      : null;

  if (price == null || !primary) {
    return {
      price,
      nearestSupport: null,
      nearestResistance: null,
      distanceFromSupport: null,
      distanceToResistance: null,
      entryZone,
      classification: "UNKNOWN",
      explanation: "Not enough level information to place price yet.",
    };
  }

  const marks: number[] = [
    ...(Array.isArray(primary.targets) ? primary.targets.map(Number) : []),
    Number(primary.invalidation),
    Number(primary.trigger_price),
    ...(entryZone ?? []),
  ].filter((v) => Number.isFinite(v));

  const below = marks.filter((m) => m <= price).sort((a, b) => b - a);
  const above = marks.filter((m) => m > price).sort((a, b) => a - b);
  const support = below.length ? below[0] : null;
  const resistance = above.length ? above[0] : null;

  const fromSupport = support == null ? null : Number((price - support).toFixed(2));
  const toResistance = resistance == null ? null : Number((resistance - price).toFixed(2));

  // A spent or invalidated plan has no levels that still matter. Ranking its
  // old targets as "support" and rendering an empty resistance half is honest
  // arithmetic and useless information -- price has already gone past all of
  // them, which is why the plan is spent.
  const planLive = String(primary.state) !== "spent" && String(primary.state) !== "invalidated";
  if (!planLive) {
    return {
      price,
      nearestSupport: null,
      nearestResistance: null,
      distanceFromSupport: null,
      distanceToResistance: null,
      entryZone,
      classification: "UNKNOWN",
      explanation:
        "This plan has finished, so its levels no longer describe where price is. Waiting for the next plan.",
    };
  }

  let classification: LocationClass = "MID_RANGE";
  let explanation = "Price is between the levels this plan cares about.";

  if (entryZone && price >= Math.min(...entryZone) && price <= Math.max(...entryZone)) {
    classification = "INSIDE_ENTRY_ZONE";
    explanation = "Price is inside the planned entry zone. Location is favourable.";
  } else if (toResistance != null && toResistance <= AT_LEVEL_DISTANCE) {
    classification = "AT_RESISTANCE";
    explanation = "Price is at resistance — a poor location to buy into.";
  } else if (fromSupport != null && fromSupport <= AT_LEVEL_DISTANCE) {
    classification = "AT_SUPPORT";
    explanation = "Price is at support — a poor location to sell into.";
  } else if (toResistance != null && toResistance <= NEAR_LEVEL_DISTANCE) {
    classification = "NEAR_RESISTANCE";
    explanation = "Price is approaching resistance. Entry quality is falling.";
  } else if (fromSupport != null && fromSupport <= NEAR_LEVEL_DISTANCE) {
    classification = "NEAR_SUPPORT";
    explanation = "Price is approaching support.";
  }

  return {
    price,
    nearestSupport: support,
    nearestResistance: resistance,
    distanceFromSupport: fromSupport,
    distanceToResistance: toResistance,
    entryZone,
    classification,
    explanation,
  };
}

function buildRightNow(
  status: TradeStatus,
  primary: PlanVM | null,
  location: PriceLocationVM,
): RightNowVM {
  const waitingFor: string[] = [];
  const avoid: string[] = [];

  if (primary && primary.isActive) {
    if (location.classification === "AT_RESISTANCE" && primary.direction === "BUY") {
      avoid.push("Buying directly into resistance");
    }
    if (location.classification === "AT_SUPPORT" && primary.direction === "SELL") {
      avoid.push("Selling directly into support");
    }
    if (location.entryZone) {
      waitingFor.push(
        `Price to reach ${location.entryZone[0].toFixed(2)}–${location.entryZone[1].toFixed(2)}`,
      );
    }
    if (status !== "READY") {
      waitingFor.push(`Confirmation: ${primary.trigger}`);
      avoid.push("Entering before the confirming candle closes");
    }
  }

  if (status === "CANCELLED") {
    avoid.push("Trading the cancelled idea");
    avoid.push("Taking the opposite side automatically — it needs its own trigger");
  }

  let headline: string;
  let reason: string;
  switch (status) {
    case "READY":
      headline = "Setup confirmed";
      reason = primary ? `${primary.direction} conditions are met.` : "Conditions are met.";
      break;
    case "CANCELLED":
      headline = "Plan cancelled";
      reason = "The idea was invalidated. Wait for a fresh plan.";
      break;
    case "AVOID":
      headline = "Stand aside";
      reason = "This move has already played out.";
      break;
    default:
      headline =
        location.classification === "AT_RESISTANCE" || location.classification === "AT_SUPPORT"
          ? "Do not chase this move"
          : "No valid entry right now";
      reason = location.explanation;
  }

  return { action: status, headline, reason, waitingFor, avoid };
}

function buildLastHour(update: HourlyUpdate | undefined): LastHourVM | null {
  if (!update) return null;
  const touched = Array.isArray(update.levels_touched) ? update.levels_touched : [];
  return {
    hourId: String(update.hourly_id ?? ""),
    expected: String(update.actual_vs_expected?.expected ?? "—"),
    observed: String(update.actual_vs_expected?.observed ?? "—"),
    interpretation: describeHourOutcome(update.plan_status),
    ohlc: update.hour_ohlc ?? null,
    levelsTouched: touched.map((t) => {
      const result = String(t.result ?? "").toLowerCase();
      const resultText =
        result === "broken_above"
          ? "broken above"
          : result === "broken_below"
            ? "broken below"
            : result === "held"
              ? "held"
              : levelEvent(t.label) ?? (result.replace(/_/g, " ") || "tested");
      return `${levelName(t.label)} at ${Number(t.price).toFixed(2)} — ${resultText}`;
    }),
    severity: changeSeverity(update.plan_status, update.confidence_delta),
    confidenceDelta: Number(update.confidence_delta ?? 0),
    nextConfirmation:
      describeEvidence(String(update.note ?? "").trim()) ||
      "No further note from this hour.",
  };
}

export function buildPlanViewModel(
  plan: PlannerState | null,
  snapshot: { symbol?: string; price?: number } | null,
  stack: TradeIdeaStack | undefined,
  lastUpdate: HourlyUpdate | undefined,
): PlanViewModel {
  const branches = plan?.day_branches;
  const { primary, alternative } = choosePrimary(branches);
  const primaryVM = toPlanVM(primary, true);
  const alternativeVM = toPlanVM(alternative, false);
  const price = num(snapshot?.price);
  const location = buildLocation(price, primary, stack);
  const status: TradeStatus = primary ? tradeStatusFor(primary.state) : "WAIT";

  // Location can veto readiness but never create it. The backend owns READY;
  // this only refuses to display it when price is in a poor place to act.
  const displayStatus: TradeStatus =
    status === "READY" &&
    (location.classification === "AT_RESISTANCE" || location.classification === "AT_SUPPORT")
      ? "WAIT"
      : status;

  const confirmation = stack?.layer_validation
    ? Object.entries(stack.layer_validation)
        .filter(([, v]) => String(v) !== "on_track")
        .map(([k]) => k.toUpperCase())
        .join(", ") || "All layers on track"
    : "No layer validation yet";

  // Each ladder pair holds BOTH branches plus the side the planner nominated.
  // `side` is null when neither branch has earned a lean -- rendered as NEUTRAL
  // rather than silently defaulting to one direction.
  const timeframes: TimeframeVM[] = (plan?.timeframe_ladder?.pairs ?? []).map((pair) => {
    const leading = pair.side === "buy" ? pair.bull : pair.side === "sell" ? pair.bear : null;
    return {
      timeframe: String(pair.timeframe),
      role: String(pair.role ?? ""),
      bias: biasLabel(pair.side),
      state: String(leading?.state ?? ""),
      summary: String(pair.note ?? leading?.reason ?? ""),
      level: num(leading?.invalidation),
    };
  });

  const positives = primaryVM?.evidence ?? [];
  const negatives: string[] = [];
  if (location.classification === "AT_RESISTANCE") negatives.push("Price is at resistance");
  if (location.classification === "AT_SUPPORT") negatives.push("Price is at support");
  if (lastUpdate && String(lastUpdate.plan_status) === "invalidated") {
    negatives.push("The last closed hour did not behave as expected");
  }

  const doList: string[] = [];
  const dontList: string[] = [];
  if (primaryVM?.isActive) {
    if (location.entryZone) {
      doList.push(
        `Watch ${location.entryZone[0].toFixed(2)}–${location.entryZone[1].toFixed(2)} for a reaction`,
      );
    }
    doList.push("Require a closed candle before acting");
    doList.push("Recalculate risk and reward at the trigger, not now");
    dontList.push("Treat a directional bias as an automatic entry signal");
    dontList.push("Enter on an unfinished candle");
  }
  dontList.push(...(buildRightNow(displayStatus, primaryVM, location).avoid ?? []));

  return {
    brief: {
      symbol: String(snapshot?.symbol ?? plan?.symbol ?? "—"),
      price,
      session: String(plan?.clock?.session ?? "—"),
      sessionHour: num(plan?.clock?.hour_of_session),
      bias: primaryVM ? biasLabel(primaryVM.direction) : "NEUTRAL",
      tradeStatus: displayStatus,
      location: location.classification,
      confirmation,
      // The one condition that decides whether the plan survives. This is the
      // whole of the old "What would change my mind" card reduced to a line:
      // the card restated the status, the thesis and the invalidation, all of
      // which already appear elsewhere, so it added length without adding a
      // fact. What was genuinely only there is the level -- kept here.
      condition: primaryVM
        ? primaryVM.isActive && primaryVM.invalidation != null
          ? `Valid while price holds ${
              primaryVM.direction === "BUY" ? "above" : "below"
            } ${primaryVM.invalidation.toFixed(2)}`
          : `${primaryVM.stateText} — waiting for a fresh setup`
        : "No active plan",
    },
    rightNow: buildRightNow(displayStatus, primaryVM, location),
    primary: primaryVM,
    alternative: alternativeVM,
    location,
    timeframes,
    timeframeInterpretation: buildTimeframeInterpretation(timeframes, primaryVM),
    lastHour: buildLastHour(lastUpdate),
    confidencePositives: positives,
    confidenceNegatives: negatives,
    doList,
    dontList: Array.from(new Set(dontList)),
    changeMyMind: {
      thesis: primaryVM
        ? `${biasLabel(primaryVM.direction)} — ${primaryVM.thesis}`
        : "No active thesis",
      hardInvalidation:
        primaryVM?.invalidation != null
          ? `A close through ${primaryVM.invalidation.toFixed(2)}`
          : "No invalidation level supplied",
      warnings: negatives,
      oppositeActivation:
        alternativeVM?.activationCondition ?? "The opposite case has no active trigger",
    },
  };
}

/**
 * One sentence describing how the frames interact.
 *
 * Deliberately refuses to claim agreement unless the frames that expressed a
 * lean actually agree. The old header read "BUY — all timeframes agree" while
 * three of four panels showed NO LEAN.
 */
function buildTimeframeInterpretation(
  frames: TimeframeVM[],
  primary: PlanVM | null,
): string {
  if (!frames.length) return "No timeframe read available.";
  const leaning = frames.filter((f) => f.bias !== "NEUTRAL");
  if (!leaning.length) return "No timeframe is expressing a lean yet.";

  const bulls = leaning.filter((f) => f.bias === "BULLISH").map((f) => f.timeframe);
  const bears = leaning.filter((f) => f.bias === "BEARISH").map((f) => f.timeframe);
  const silent = frames.filter((f) => f.bias === "NEUTRAL").map((f) => f.timeframe);
  const tail = silent.length ? ` ${silent.join(", ")} ${silent.length === 1 ? "has" : "have"} no lean yet.` : "";

  if (bulls.length && bears.length) {
    return `${bulls.join(", ")} lean bullish while ${bears.join(", ")} lean bearish — the lower frame is pulling back against the higher one, which is a pullback rather than a conflict.${tail}`;
  }
  const side = bulls.length ? "bullish" : "bearish";
  const names = bulls.length ? bulls : bears;
  const agreement =
    names.length === frames.length
      ? `All timeframes lean ${side}.`
      : `${names.join(", ")} lean ${side}.`;
  const note = primary
    ? ` That favours waiting for a ${primary.direction === "BUY" ? "pullback" : "bounce"} rather than entering at current price.`
    : "";
  return `${agreement}${tail}${note}`;
}
