/**
 * Machine state -> trader language, in one place.
 *
 * Why this exists
 * ---------------
 * The screen was showing its own internal vocabulary: "M15_PREVIOUS_HIGH_REJECTION",
 * "accepted_close_through_support", "H4 invalidated", "missing closed M15 response
 * at the mapped zone". Each is precise and each requires the reader to translate
 * it into a market fact before they can act on it.
 *
 * Every conversion lives here rather than being scattered through components, so
 * that the same enum never renders two different ways in two different cards --
 * which is how a screen starts contradicting itself.
 *
 * Rule: translate wording only. Nothing in this file may change meaning, invent
 * a level, or upgrade a state. The deterministic planner remains the only
 * authority on what is true.
 */

/** A named level id, e.g. "H1_PREVIOUS_LOW_ACCEPTANCE" -> "H1 previous low". */
export function levelName(id: string | null | undefined): string {
  if (!id) return "unnamed level";
  const raw = String(id);
  const tf = raw.match(/^(D1|H4|H1|M30|M15|M5|M1)_/)?.[1] ?? "";
  let rest = raw.replace(/^(D1|H4|H1|M30|M15|M5|M1)_/, "").toLowerCase();

  // The suffix says what price DID at the level, not what the level is.
  // Keep it out of the name; describeLevelEvent() renders it separately.
  rest = rest
    .replace(/_acceptance_invalidation$/, "")
    .replace(/_(acceptance|rejection|invalidation)$/, "")
    .replace(/_/g, " ")
    .replace(/\bpp\b/g, "pivot")
    .trim();

  return tf ? `${tf} ${rest}` : rest;
}

/** What price did at a level: the suffix half of the same id. */
export function levelEvent(id: string | null | undefined): string | null {
  if (!id) return null;
  const raw = String(id).toLowerCase();
  if (raw.endsWith("_acceptance_invalidation")) return "accepted through, invalidating it";
  if (raw.endsWith("_acceptance")) return "accepted through";
  if (raw.endsWith("_rejection")) return "rejected";
  if (raw.endsWith("_invalidation")) return "invalidated";
  return null;
}

const TRIGGERS: Record<string, string> = {
  accepted_close_through_support: "Close accepted through support",
  accepted_close_through_resistance: "Close accepted through resistance",
  accepted_close_through_level: "Close accepted through the level",
  rejected_at_support: "Rejection at support",
  rejected_at_resistance: "Rejection at resistance",
  wick_rejection_at_level: "Wick rejection at the level",
  wick_acceptance_at_level: "Wick acceptance at the level",
  entry_condition_met: "Entry condition met",
  entry_condition_not_met: "Entry condition not met yet",
  entry_trigger_missing: "Entry trigger has not appeared",
  entry_signal_missing: "No entry signal yet",
  entry_pending: "Entry still pending",
  missing_evidence: "Supporting evidence not there yet",
  missing_response: "No reaction at the level yet",
  missing_acceptance: "Price has not accepted through the level",
  missing_target_response: "No reaction at the target yet",
  missing_closed_m15_response: "M15 has not closed to show how price reacted",
  waiting_for_trigger: "Waiting for its trigger",
  reached_final_target: "Reached final target",
  new_opportunity: "A fresh opportunity",
  no_conflict: "No conflicting signal",
};

/** First letter upper; keeps the rest as written. */
function sentenceCase(text: string): string {
  const t = text.trim();
  if (!t) return t;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Trigger / reason codes -> a phrase a trader can read at a glance. */
export function describeTrigger(code: string | null | undefined): string {
  if (!code) return "—";
  const raw = String(code).trim();
  const key = raw.toLowerCase().replace(/\s+/g, "_");
  if (TRIGGERS[key]) return TRIGGERS[key];
  // Free prose from the model comes through unchanged -- it is already readable.
  if (/\s/.test(raw)) return sentenceCase(raw);
  return sentenceCase(key.replace(/_/g, " "));
}

/**
 * Evidence / note lines that mix codes and prose.
 * "M15 accepted close through support" -> "M15: close accepted through support"
 */
export function describeEvidence(line: string | null | undefined): string {
  if (!line) return "—";
  const raw = String(line).trim();

  // Exact trigger code
  const asCode = raw.toLowerCase().replace(/\s+/g, "_");
  if (TRIGGERS[asCode]) return TRIGGERS[asCode];

  const EVIDENCE_PROSE: Record<string, string> = {
    "accepted close through support": "close accepted through support",
    "accepted close through resistance": "close accepted through resistance",
    "wick rejection at level": "wick rejection at the level",
    "wick acceptance at level": "wick acceptance at the level",
    "pivot pp support": "pivot support",
    "pivot pp resistance": "pivot resistance",
  };

  const tfMatch = raw.match(/^(D1|H4|H1|M30|M15|M5|M1)\s+(.+)$/i);
  if (tfMatch) {
    const tf = tfMatch[1].toUpperCase();
    const rest = tfMatch[2].trim().toLowerCase();
    const mapped = EVIDENCE_PROSE[rest] ?? rest.replace(/\bpp\b/g, "pivot");
    return `${tf}: ${mapped}`;
  }

  const prose = EVIDENCE_PROSE[raw.toLowerCase()];
  if (prose) return sentenceCase(prose);

  // Snake_case leftovers
  if (!/\s/.test(raw) && /_/.test(raw)) return describeTrigger(raw);

  // Common free-prose notes that still start with a known code phrase.
  const knownPrefix = Object.keys(TRIGGERS).sort((a, b) => b.length - a.length);
  const spaced = raw.toLowerCase();
  for (const key of knownPrefix) {
    const phrase = key.replace(/_/g, " ");
    if (spaced === phrase || spaced.startsWith(`${phrase} `) || spaced.startsWith(`${phrase};`) || spaced.startsWith(`${phrase},`)) {
      let rest = raw.slice(phrase.length).replace(/^[\s;,\-–—]+/, "").trim();
      rest = rest.replace(/^at the mapped zone[;,\s]*/i, "").trim();
      return rest ? `${TRIGGERS[key]}; ${sentenceCase(rest)}` : TRIGGERS[key];
    }
  }

  return sentenceCase(raw.replace(/\bpp\b/gi, "pivot"));
}

/** Layer status chip wording. */
export function describeLayerStatus(status: string | null | undefined): string {
  switch (String(status ?? "").toLowerCase()) {
    case "on_track":
      return "on track";
    case "drifting":
      return "drifting";
    case "invalidated":
      return "done";
    case "pending":
      return "pending";
    case "active":
      return "active";
    case "revised":
      return "revised";
    default:
      return String(status ?? "—").replace(/_/g, " ");
  }
}

/**
 * Branch state -> what the trader should do.
 *
 * This is the spec's core separation: bias and readiness are different claims.
 * A branch can be bullish AND not tradeable, which is the single most common
 * confusion the old screen created.
 */
export type TradeStatus = "WAIT" | "READY" | "ENTER" | "MANAGE" | "AVOID" | "CANCELLED";

export function tradeStatusFor(state: string | null | undefined): TradeStatus {
  switch (String(state)) {
    case "confirmed":
      return "READY";
    case "likely":
    case "armed":
      return "WAIT";
    case "invalidated":
      return "CANCELLED";
    case "spent":
      return "AVOID";
    default:
      return "WAIT";
  }
}

export const TRADE_STATUS_TEXT: Record<TradeStatus, string> = {
  WAIT: "Wait — no valid entry right now",
  READY: "Setup confirmed — entry conditions met",
  ENTER: "Entry live",
  MANAGE: "Position open — managing",
  AVOID: "Stand aside — this move is already spent",
  CANCELLED: "Plan cancelled — the idea was invalidated",
};

/** Branch state -> plain description, for the plan cards. */
export function describeState(state: string | null | undefined): string {
  switch (String(state)) {
    case "armed":
      return "Set up and waiting for its trigger";
    case "likely":
      return "Building — evidence is accumulating";
    case "confirmed":
      return "Confirmed";
    case "spent":
      return "Already played out";
    case "invalidated":
      return "No longer valid";
    default:
      return String(state ?? "unknown");
  }
}

/** Hourly plan_status -> what it means for the plan, not for the enum. */
export function describeHourOutcome(status: string | null | undefined): string {
  switch (String(status)) {
    case "on_track":
      return "The hour behaved as the plan expected";
    case "drifting":
      return "The hour drifted from what the plan expected";
    case "invalidated":
      return "The hour did not behave as the plan expected";
    case "pending":
      return "This hour has not closed yet";
    default:
      return "No read on this hour";
  }
}

export type ChangeSeverity = "NONE" | "MINOR" | "MODERATE" | "MAJOR" | "INVALIDATED";

/** Confidence delta + plan status -> how much the picture actually moved. */
export function changeSeverity(
  status: string | null | undefined,
  delta: number | null | undefined,
): ChangeSeverity {
  if (String(status) === "invalidated") return "INVALIDATED";
  const size = Math.abs(Number(delta ?? 0));
  if (size === 0) return "NONE";
  if (size < 10) return "MINOR";
  if (size < 25) return "MODERATE";
  return "MAJOR";
}

export type ConfidenceLabel = "VERY_LOW" | "LOW" | "MODERATE" | "HIGH" | "VERY_HIGH";

/**
 * A score becomes a word.
 *
 * The bands are anchored on MIN_ENTRY_CONFIDENCE = 51, the threshold the backend
 * actually trades on -- so "MODERATE" begins exactly where a trade becomes
 * possible, rather than at an arbitrary round number.
 */
export function confidenceLabel(score: number | null | undefined): ConfidenceLabel {
  const value = Number(score ?? 0);
  if (value < 25) return "VERY_LOW";
  if (value < 51) return "LOW";
  if (value < 70) return "MODERATE";
  if (value < 85) return "HIGH";
  return "VERY_HIGH";
}

export const CONFIDENCE_TEXT: Record<ConfidenceLabel, string> = {
  VERY_LOW: "Very low",
  LOW: "Low — below the entry threshold",
  MODERATE: "Moderate",
  HIGH: "High",
  VERY_HIGH: "Very high",
};

/** Timeframe -> the job it does in the top-down read. */
export const TIMEFRAME_ROLE: Record<string, string> = {
  D1: "Context",
  H4: "Structure",
  H1: "Setup",
  M15: "Trigger",
};

export const TIMEFRAME_ROLE_EXPLAINER: Record<string, string> = {
  D1: "Which way the day leans",
  H4: "Where the auction is building or failing",
  H1: "The zone a trade would be taken from",
  M15: "The closed response that starts the trade",
};

/** "buy" -> "BUY". Keeps side rendering identical everywhere. */
export function sideLabel(side: string | null | undefined): "BUY" | "SELL" | "NONE" {
  const value = String(side ?? "").toLowerCase();
  if (value === "buy") return "BUY";
  if (value === "sell") return "SELL";
  return "NONE";
}

export function biasLabel(side: string | null | undefined): "BULLISH" | "BEARISH" | "NEUTRAL" {
  const value = String(side ?? "").toLowerCase();
  if (value === "buy" || value === "bullish") return "BULLISH";
  if (value === "sell" || value === "bearish") return "BEARISH";
  return "NEUTRAL";
}

/** Price, rendered the same way on every card. */
export function price(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

export function priceRange(
  low: number | null | undefined,
  high: number | null | undefined,
): string {
  if (low == null || high == null) return "—";
  return `${price(low)}–${price(high)}`;
}
