export interface StrategyCatalogEntry {
  strategy_id: string;
  version: string;
  pair: string;
  magic_number: number;
  trade_class: string;
  status: "registered" | "inactive";
  context_timeframes: string[];
  setup_timeframes: string[];
  execution_timeframes: string[];
  excluded_timeframes: string[];
  explanation: string;
  management: Record<string, number>;
}

// The catalog is deliberately explicit. A strategy must be registered here
// before the UI presents it as a selectable trading strategy.
export const STRATEGY_CATALOG: StrategyCatalogEntry[] = [
  {
    strategy_id: "XAU_M15_M1_STRUCTURE_SCALPER_50PT_V1",
    version: "1.0.0",
    pair: "XAUUSDr",
    magic_number: 3101,
    trade_class: "MICRO",
    status: "inactive",
    context_timeframes: ["D1", "H4", "H2", "H1"],
    setup_timeframes: ["M15"],
    execution_timeframes: ["M1"],
    excluded_timeframes: ["M5"],
    explanation: "A fail-closed M15 level and M1 structure scalper. It requires higher-timeframe context, an active M15 level, a confirmed M1 episode, and measurable target space before a candidate can exist.",
    management: {
      initial_check_seconds: 10,
      next_m1_check_seconds: 15,
      failed_check_wait_minutes: 1,
      break_even_atr_trigger: 1,
      break_even_offset_atr: 0.05,
      maximum_early_adverse_atr: 0.25,
    },
  },
];

export const strategyLabel = (strategyId?: string | null) =>
  strategyId || "Unassigned / legacy record";
