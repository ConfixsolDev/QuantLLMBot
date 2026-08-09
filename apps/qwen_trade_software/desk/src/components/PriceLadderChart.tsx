import type { Level, QwenState } from "@/lib/types";
import {
  formatPrice,
  getChartRange,
  levelSide,
  priceToTopPercent,
} from "@/lib/chart";

interface PriceLadderChartProps {
  levels: Level[];
  price: number;
  qwen: QwenState;
  chartClassName?: string;
  showAxes?: boolean;
  showProposal?: boolean;
  showTradeMarkers?: boolean;
  showPathLabels?: boolean;
  footerLeft?: string;
  footerRight?: string;
}

export function PriceLadderChart({
  levels,
  price,
  qwen,
  chartClassName = "chart",
  showAxes = true,
  showProposal = true,
  showTradeMarkers = true,
  showPathLabels = false,
  footerLeft,
  footerRight,
}: PriceLadderChartProps) {
  const plan = qwen.execution_plan;
  const ready = plan?.status === "ready";
  const range = getChartRange(levels, price, plan);
  const axisTicks = [range.max, (range.max + range.min) / 2, range.min];

  return (
    <>
      <div className={chartClassName}>
        <div className="grid" />
        {levels.map((level) => {
          const side = levelSide(level.price, price);
          return (
            <div
              key={level.id}
              className={`priceLevel ${side}`}
              style={{ top: `${priceToTopPercent(level.price, range.min, range.max)}%` }}
            >
              <span className="line" />
              <em>{level.role}</em>
              <b>{formatPrice(level.price)}</b>
            </div>
          );
        })}
        {Number.isFinite(price) && price > 0 && (
          <div
            className="currentPrice"
            style={{ top: `${priceToTopPercent(price, range.min, range.max)}%` }}
          >
            <span>{formatPrice(price)}</span>
            <b>NOW</b>
          </div>
        )}
        {showProposal &&
          qwen.proposal_id &&
          typeof qwen.proposal_price === "number" && (
            <div
              className="proposalMarker"
              style={{
                top: `${priceToTopPercent(qwen.proposal_price, range.min, range.max)}%`,
              }}
            >
              <strong>PAPER · {ready ? "READY" : "WAIT"}</strong>
              <b>{formatPrice(qwen.proposal_price)}</b>
              <code>{qwen.proposal_id}</code>
              <span title={qwen.summary}>{qwen.summary}</span>
            </div>
          )}
        {showTradeMarkers && ready && plan?.side === "buy" && (
          <div
            className="tradeMarker buyMarker"
            style={{
              top: `${priceToTopPercent(plan.entry_low ?? price, range.min, range.max)}%`,
            }}
          >
            <strong>BUY HERE</strong>
            <span>
              {formatPrice(plan.entry_low)}–{formatPrice(plan.entry_high)}
            </span>
          </div>
        )}
        {showTradeMarkers && ready && plan?.side === "sell" && (
          <div
            className="tradeMarker sellMarker"
            style={{
              top: `${priceToTopPercent(plan.entry_high ?? price, range.min, range.max)}%`,
            }}
          >
            <strong>SELL HERE</strong>
            <span>
              {formatPrice(plan.entry_low)}–{formatPrice(plan.entry_high)}
            </span>
          </div>
        )}
        {showPathLabels && (
          <>
            <div className="pathLabel pathUp">
              <b>PATH A · ACCEPTANCE</b>
              <span>
                Hold above current support, reclaim the next level, then test
                resistance.
              </span>
            </div>
            <div className="pathLabel pathDown">
              <b>PATH B · REJECTION</b>
              <span>
                Failure at resistance sends price back toward the nearest
                support.
              </span>
            </div>
          </>
        )}
        {showAxes && (
          <>
            <div className="priceAxis">
              <span className="axisTitle">PRICE</span>
              {axisTicks.map((tick) => (
                <b key={tick}>{formatPrice(tick)}</b>
              ))}
            </div>
            <div className="timeAxis">
              <span>-4h</span>
              <span>-2h</span>
              <span>NOW</span>
              <span>+2h</span>
            </div>
          </>
        )}
      </div>
      {(footerLeft || footerRight) && (
        <div className="chartFooter">
          <span>{footerLeft}</span>
          <span>{footerRight}</span>
        </div>
      )}
    </>
  );
}
