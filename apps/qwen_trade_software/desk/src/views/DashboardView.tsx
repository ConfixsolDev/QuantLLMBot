import { PriceLadderChart } from "@/components/PriceLadderChart";
import { CardHeading, PageFooter, QuoteBlock, TopBar } from "@/components/Layout";
import { formatDuration, formatPrice, formatSigned } from "@/lib/chart";
import type { Snapshot, Timeframe } from "@/lib/types";
import { TIMEFRAME_LABELS, TIMEFRAMES } from "@/lib/types";

interface DashboardViewProps {
  snapshot: Snapshot;
  timeframe: Timeframe;
  generating: boolean;
  onTimeframeChange: (timeframe: Timeframe) => void;
  onGenerateDealSheet: () => void;
  onOpenSheet: () => void;
  onOpenCheat: () => void;
}

export function DashboardView({
  snapshot,
  timeframe,
  generating,
  onTimeframeChange,
  onGenerateDealSheet,
  onOpenSheet,
  onOpenCheat,
}: DashboardViewProps) {
  const levels = snapshot.levels[timeframe] ?? [];
  const plan = snapshot.qwen.execution_plan;
  const ready = plan?.status === "ready";
  const syncedAt = snapshot.qwen.updated_at
    ? new Date(snapshot.qwen.updated_at).toLocaleTimeString()
    : undefined;

  return (
    <>
      <TopBar
        connected={snapshot.connected}
        modelStatus={snapshot.model_status}
        generating={generating}
        onGenerateDealSheet={onGenerateDealSheet}
        onOpenSheet={onOpenSheet}
        onOpenCheat={onOpenCheat}
      />

      <section className="hero">
        <div>
          <div className="eyebrow">XAUUSD · BASKET SCALP MAP</div>
          <h1>
            One chart. One timeframe.
            <br />
            One clear trade thesis.
          </h1>
          <p>
            Local preview of named MT5 levels, Qwen deal sheets, and paper
            execution events. Switch timeframe to inspect structure before
            generating a basket plan.
          </p>
        </div>
        <QuoteBlock
          label={`${snapshot.symbol} · LIVE`}
          price={snapshot.price}
          syncedAt={syncedAt}
        />
      </section>

      <nav className="periods" aria-label="Chart timeframe">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            type="button"
            className={timeframe === tf ? "active" : ""}
            onClick={() => onTimeframeChange(tf)}
          >
            {tf}
            <small>{TIMEFRAME_LABELS[tf]}</small>
          </button>
        ))}
      </nav>

      <section className="workspace">
        <article className="chartCard">
          <CardHeading
            kicker="Historical cheat sheet"
            title={`${timeframe} structure map`}
            tag={<span className="minimalTag">Minimal view</span>}
          />
          <PriceLadderChart
            levels={levels}
            price={snapshot.price}
            qwen={snapshot.qwen}
            footerLeft="Qwen: wait for reaction at BUY/SELL level—do not enter in the middle."
            footerRight={`${levels.length} named levels · ${snapshot.symbol}`}
          />
        </article>

        <aside className="sideStack">
          <ExecutionCard snapshot={snapshot} />
          <QwenCard snapshot={snapshot} />
          <TradeIdeaCard snapshot={snapshot} ready={ready} plan={plan} />
        </aside>
      </section>

      <section className="metrics">
        <article>
          <span>Today net</span>
          <strong
            className={
              snapshot.today.net_profit >= 0 ? "positive" : "negative"
            }
          >
            {formatSigned(snapshot.today.net_profit)}
          </strong>
          <small>Closed executions</small>
        </article>
        <article>
          <span>Baskets</span>
          <strong>{snapshot.today.baskets}</strong>
          <small>Completed basket groups</small>
        </article>
        <article>
          <span>Median hold</span>
          <strong>{formatDuration(snapshot.today.median_hold_seconds)}</strong>
          <small>Quick-trade profile</small>
        </article>
        <article>
          <span>Win rate</span>
          <strong>{Math.round(snapshot.today.win_rate)}%</strong>
          <small>Closed basket outcomes</small>
        </article>
      </section>

      <section className="bottomGrid">
        <PositionsCard snapshot={snapshot} />
        <RulesCard />
      </section>

      <PageFooter />
    </>
  );
}

function ExecutionCard({ snapshot }: { snapshot: Snapshot }) {
  const event = snapshot.paper_execution;
  const active = Boolean(event?.fill);

  return (
    <article className="executionCard">
      <CardHeading
        compact
        kicker="PAPER ENGINE"
        title="Latest execution event"
        tag={
          <span className={`engineState${active ? " active" : ""}`}>
            {active ? "MONITORING" : "WAITING"}
          </span>
        }
      />
      {event ? (
        <div className="executionDetails">
          <code>{event.proposal_id ?? "paper-event"}</code>
          <strong>{event.event?.replaceAll("_", " ") ?? "Event"}</strong>
          {event.fill && (
            <>
              <span>
                Bucket {event.fill.bucket} · {event.fill.phase.replaceAll("_", " ")}
              </span>
              <span>{formatPrice(event.fill.price)}</span>
            </>
          )}
          {typeof event.gross_pnl === "number" && (
            <span>P&amp;L {formatSigned(event.gross_pnl)}</span>
          )}
          {event.reason && <small>{event.reason.replaceAll("_", " ")}</small>}
        </div>
      ) : (
        <p className="engineWaiting">Waiting for a validated ready proposal.</p>
      )}
    </article>
  );
}

function QwenCard({ snapshot }: { snapshot: Snapshot }) {
  const confidence = Math.max(50, snapshot.qwen.confidence || 50);
  return (
    <article className="qwenCard">
      <CardHeading
        compact
        kicker="QWEN DEAL SHEET"
        title={snapshot.qwen.bias}
        tag={
          <div className="confidence">
            {confidence}
            <small>confidence</small>
          </div>
        }
      />
      <p>{snapshot.qwen.summary}</p>
      <div className="scenario">
        <span>PRIMARY PATH</span>
        <strong>{snapshot.qwen.summary || "Waiting for a validated live plan."}</strong>
      </div>
      <div className="scenario danger">
        <span>INVALIDATION</span>
        <strong>{snapshot.qwen.invalidation}</strong>
      </div>
      <small className="modelNote">{snapshot.model}</small>
    </article>
  );
}

function TradeIdeaCard({
  snapshot,
  ready,
  plan,
}: {
  snapshot: Snapshot;
  ready: boolean;
  plan: Snapshot["qwen"]["execution_plan"];
}) {
  return (
    <article className="tradeIdea">
      <CardHeading
        compact
        kicker="UMBRELLA SMART TRADE"
        title="Basket plan"
        tag={<span className="riskBadge">QUICK</span>}
      />
      <div className="ideaRows">
        <div>
          <span>Status</span>
          <b>{ready ? "READY · PAPER" : "WAIT"}</b>
        </div>
        <div>
          <span>Bias</span>
          <b>{plan?.side ?? snapshot.qwen.bias}</b>
        </div>
        <div>
          <span>Entry zone</span>
          <b>
            {ready
              ? `${formatPrice(plan?.entry_low)}–${formatPrice(plan?.entry_high)}`
              : "No validated live zone"}
          </b>
        </div>
        <div>
          <span>Umbrella SL</span>
          <b>{ready ? formatPrice(plan?.stop_loss) : "—"}</b>
        </div>
        <div>
          <span>Basket target</span>
          <b>{ready ? formatPrice(plan?.take_profit) : "—"}</b>
        </div>
      </div>
      <p className="guardrail">
        {plan?.reason ??
          "Qwen must answer within 45 seconds or be discarded."}
      </p>
    </article>
  );
}

function PositionsCard({ snapshot }: { snapshot: Snapshot }) {
  return (
    <article className="positions">
      <CardHeading
        compact
        kicker="LIVE BASKET"
        title="Open positions"
        tag={
          <span className="count">
            {snapshot.positions.filter((p) => p.qwen_owned).length} Qwen
          </span>
        }
      />
      {snapshot.positions.length === 0 ? (
        <div className="empty">
          <b>No open positions</b>
          <span>The next basket will appear here automatically.</span>
        </div>
      ) : (
        snapshot.positions.map((position) => (
          <div key={position.ticket} className="positionRow">
            <span>{position.side.toUpperCase()}</span>
            <span>{position.volume.toFixed(2)} lots</span>
            <span>
              <strong>{formatPrice(position.open_price)}</strong>
              <span className={position.profit >= 0 ? "positive" : "negative"}>
                {formatSigned(position.profit)}
              </span>
            </span>
            <span>{position.comment ?? "—"}</span>
            <span
              className={`ownership${position.qwen_owned ? " owned" : ""}`}
            >
              {position.qwen_owned ? "Qwen managed" : "View only"}
            </span>
          </div>
        ))
      )}
    </article>
  );
}

function RulesCard() {
  return (
    <article className="rules">
      <span className="kicker">EXECUTION RULES</span>
      <ol>
        <li>
          <b>Map</b>
          <span>Use named levels only; do not invent prices off-chart.</span>
        </li>
        <li>
          <b>Protect</b>
          <span>Use the nearest valid named level for umbrella SL.</span>
        </li>
        <li>
          <b>Review</b>
          <span>Qwen must answer within 45 seconds or be discarded.</span>
        </li>
        <li>
          <b>Exit</b>
          <span>Close the basket as one idea, not unrelated tickets.</span>
        </li>
      </ol>
    </article>
  );
}
