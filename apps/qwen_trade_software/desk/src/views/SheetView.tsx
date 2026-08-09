import { PriceLadderChart } from "@/components/PriceLadderChart";
import { PageFooter, SheetActions } from "@/components/Layout";
import {
  formatPrice,
  nearestResistance,
  nearestSupport,
} from "@/lib/chart";
import type { Snapshot, Timeframe } from "@/lib/types";

interface SheetViewProps {
  snapshot: Snapshot;
  timeframe: Timeframe;
  onBack: () => void;
}

export function SheetView({ snapshot, timeframe, onBack }: SheetViewProps) {
  const levels = snapshot.levels[timeframe] ?? [];
  const plan = snapshot.qwen.execution_plan;
  const ready = plan?.status === "ready";
  const support = nearestSupport(levels, snapshot.price);
  const resistance = nearestResistance(levels, snapshot.price);

  return (
    <main className="sheetPage">
      <SheetActions
        backLabel="← Back to desk"
        printLabel="Print chart sheet"
        onBack={onBack}
        onPrint={() => window.print()}
      />

      <article className="detailSheet">
        <header className="sheetHeader">
          <div>
            <span className="kicker">GOLDFLOW · CHART DETAIL SHEET</span>
            <h1>{timeframe} structure map</h1>
            <p>
              One timeframe map · named levels only · local MT5 data
            </p>
          </div>
          <div className="sheetQuote">
            <span>CURRENT PRICE</span>
            <strong>{formatPrice(snapshot.price)}</strong>
            <small>{snapshot.symbol}</small>
          </div>
        </header>

        <section className="sheetChartSection">
          <PriceLadderChart
            levels={levels}
            price={snapshot.price}
            qwen={snapshot.qwen}
            chartClassName="sheetChart"
            showAxes={false}
            showPathLabels
          />
          <aside className="chartLegend">
            <div className="legendNow">
              <i />
              <div>
                <b>Live price</b>
                <span>Current market quote</span>
              </div>
            </div>
            <div className="legendResistance">
              <i />
              <div>
                <b>Resistance</b>
                <span>Level above current price</span>
              </div>
            </div>
            <div className="legendSupport">
              <i />
              <div>
                <b>Support</b>
                <span>Level below current price</span>
              </div>
            </div>
            <div className="legendHistory">
              <i />
              <div>
                <b>D1 context</b>
                <span>Historical map shown only on D1</span>
              </div>
            </div>
          </aside>
        </section>

        <section className="sheetPlan">
          <div className="planCell">
            <span>MARKET STATE</span>
            <strong>{snapshot.qwen.bias}</strong>
            <p>{snapshot.qwen.summary}</p>
          </div>
          <div className="planCell">
            <span>NEAREST SUPPORT</span>
            <strong>
              {support ? formatPrice(support.price) : "Not available"}
            </strong>
            <p>{support?.role ?? "Switch timeframe to calculate."}</p>
          </div>
          <div className="planCell">
            <span>NEAREST RESISTANCE</span>
            <strong>
              {resistance ? formatPrice(resistance.price) : "Not available"}
            </strong>
            <p>{resistance?.role ?? "Switch timeframe to calculate."}</p>
          </div>
          <div className="planCell dangerCell">
            <span>THESIS INVALIDATION</span>
            <strong>Exit the idea</strong>
            <p>{snapshot.qwen.invalidation}</p>
          </div>
        </section>

        <section className="qwenInstruction">
          <span>WHAT QWEN THINKS</span>
          <strong>
            {ready && plan?.side === "buy"
              ? "Buy only if price reacts and holds above mapped support."
              : ready && plan?.side === "sell"
                ? "Sell or take profit near mapped resistance."
                : snapshot.qwen.summary}
          </strong>
          <p>{snapshot.qwen.invalidation}</p>
        </section>

        <section className="tradeTable">
          <div className="tradeTableHead">
            <span>QUICK BASKET TRADE IDEA</span>
            <b>Qwen-reviewed · broker validation required</b>
          </div>
          <div className="tradeTableRow">
            <span>Entry reference</span>
            <b>
              {ready
                ? `${formatPrice(plan?.entry_low)}–${formatPrice(plan?.entry_high)}`
                : "—"}
            </b>
            <small>Reaction above support</small>
          </div>
          <div className="tradeTableRow">
            <span>Umbrella protection</span>
            <b>{ready ? formatPrice(plan?.stop_loss) : "—"}</b>
            <small>M5 basket boundary</small>
          </div>
          <div className="tradeTableRow">
            <span>First objective</span>
            <b>{ready ? formatPrice(plan?.take_profit) : "—"}</b>
            <small>Nearest active resistance</small>
          </div>
          <div className="tradeTableRow">
            <span>Basket handling</span>
            <b>One thesis</b>
            <small>Manage all tickets as one thesis</small>
          </div>
        </section>

        <section className="dailyStrip">
          <div>
            <span>D1 HISTORICAL CONTEXT</span>
            <b>{(snapshot.levels.D1 ?? []).length} levels loaded</b>
          </div>
          {(snapshot.levels.D1 ?? []).slice(0, 4).map((level) => (
            <div key={level.id}>
              <span>{level.role}</span>
              <b>{formatPrice(level.price)}</b>
            </div>
          ))}
        </section>

        <footer className="sheetFooter">
          <span>Research sheet · not a prediction guarantee</span>
          <span>{snapshot.model}</span>
        </footer>
      </article>

      <PageFooter />
    </main>
  );
}
