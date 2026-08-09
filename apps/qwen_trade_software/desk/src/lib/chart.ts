import type { ExecutionPlan, Level } from "./types";

export function priceToTopPercent(
  price: number,
  min: number,
  max: number,
): number {
  if (max <= min) return 50;
  return ((max - price) / (max - min)) * 100;
}

export function getChartRange(
  levels: Level[],
  price: number,
  plan?: ExecutionPlan,
): { min: number; max: number } {
  const prices = levels.map((level) => level.price);
  if (Number.isFinite(price) && price > 0) prices.push(price);
  if (plan?.status === "ready") {
    for (const value of [
      plan.entry_low,
      plan.entry_high,
      plan.stop_loss,
      plan.take_profit,
    ]) {
      if (typeof value === "number" && Number.isFinite(value)) {
        prices.push(value);
      }
    }
  }
  if (prices.length === 0) {
    return { min: price - 5, max: price + 5 };
  }
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const pad = Math.max((max - min) * 0.08, 1);
  return { min: min - pad, max: max + pad };
}

export function nearestSupport(
  levels: Level[],
  price: number,
): Level | null {
  return (
    [...levels]
      .filter((level) => level.price < price)
      .sort((a, b) => b.price - a.price)[0] ?? null
  );
}

export function nearestResistance(
  levels: Level[],
  price: number,
): Level | null {
  return (
    [...levels]
      .filter((level) => level.price > price)
      .sort((a, b) => a.price - b.price)[0] ?? null
  );
}

export function formatPrice(value?: number, digits = 3): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

export function formatSigned(value: number, digits = 2): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

export function formatDuration(seconds: number): string {
  if (!seconds) return "0s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

export function levelSide(
  levelPrice: number,
  currentPrice: number,
): "support" | "resistance" {
  return levelPrice <= currentPrice ? "support" : "resistance";
}

export function levelImportance(
  level: Level,
  timeframe: string,
  currentPrice: number,
): string {
  if (timeframe === "D1") {
    return level.role.includes("Pivot")
      ? "Daily projected pivot with historical pivot significance."
      : level.role.includes("R1") || level.role.includes("S1")
        ? `Daily projected ${level.role.toLowerCase()} with historical pivot significance.`
        : `${level.role} named structure level used for reaction and invalidation context.`;
  }
  return levelSide(level.price, currentPrice) === "support"
    ? `${level.role} active low; current-session support until broken.`
    : `${level.role} active high; current-session resistance until accepted.`;
}
