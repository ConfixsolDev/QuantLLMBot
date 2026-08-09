import { PageFooter, SheetActions } from "@/components/Layout";
import {
  formatPrice,
  levelImportance,
  levelSide,
  nearestResistance,
  nearestSupport,
} from "@/lib/chart";
import type { Level, Snapshot, Timeframe } from "@/lib/types";
import { TIMEFRAME_LABELS, TIMEFRAMES } from "@/lib/types";

interface CheatViewProps {
  snapshot: Snapshot;
  timeframe: Timeframe;
  onBack: () => void;
}

export function CheatView({ snapshot, timeframe, onBack }: CheatViewProps) {
  const confluenceLevels = [
    ...(snapshot.levels.M30 ?? []),
    ...(snapshot.levels.H1 ?? []),
    ...(snapshot.levels.H4 ?? []),
  ];
  const supports = confluenceLevels
    .filter((level) => level.price < snapshot.price)
    .sort((a, b) => b.price - a.price)
    .slice(0, 3);
  const resistances = confluenceLevels
    .filter((level) => level.price > snapshot.price)
    .sort((a, b) => a.price - b.price)
    .slice(0, 3);

  return (
    <main className="sheetPage cheatPage">
      <SheetActions
        backLabel="← Back to desk"
        printLabel="Print cheat sheet"
        onBack={onBack}
        onPrint={() => window.print()}
      />

      <article className="detailSheet">
        <header className="sheetHeader">
          <div>
            <span className="kicker">GOLDFLOW · ALL-TIMEFRAME CHEAT SHEET</span>
            <h1>Named level matrix</h1>
            <p>Current and next strongest zones across all cached timeframes</p>
          </div>
          <div className="sheetQuote">
            <span>LIVE PRICE</span>
            <strong>{formatPrice(snapshot.price)}</strong>
            <small>{snapshot.symbol}</small>
          </div>
        </header>

        <section className="cheatSummary">
          <div>
            <span>DEFAULT TRADE VIEW</span>
            <b>{timeframe} umbrella</b>
          </div>
          <div>
            <span>MARKET STATE</span>
            <b>{snapshot.qwen.bias}</b>
          </div>
          <div>
            <span>CONFIDENCE</span>
            <b>{Math.max(50, snapshot.qwen.confidence || 50)}</b>
          </div>
          <div>
            <span>TIMEFRAMES</span>
            <b>{TIMEFRAMES.filter((tf) => snapshot.levels[tf]?.length).join(" · ")}</b>
          </div>
        </section>

        <section className="confluenceSection">
          <header>
            <div>
              <span className="kicker">M30 + H1 + H4 CONFLUENCE</span>
              <h2>Current and next strongest zones</h2>
            </div>
            <p>
              Support/resistance side is relative to the current live price and
              can change.
            </p>
          </header>
          <div className="zoneColumns">
            <article className="zoneColumn supportZone">
              <h3>Support zones</h3>
              {supports.length === 0 ? (
                <div className="zoneCard">
                  <span>CURRENT STRONG SUPPORT</span>
                  <strong>—</strong>
                  <small>Waiting for support levels below price.</small>
                </div>
              ) : (
                supports.map((level, index) => (
                  <ZoneCard
                    key={level.id}
                    level={level}
                    price={snapshot.price}
                    label={`NEXT SUPPORT ${index + 1}`}
                  />
                ))
              )}
            </article>
            <article className="zoneColumn resistanceZone">
              <h3>Resistance zones</h3>
              {resistances.length === 0 ? (
                <div className="zoneCard">
                  <span>CURRENT STRONG RESISTANCE</span>
                  <strong>—</strong>
                  <small>Waiting for resistance levels above price.</small>
                </div>
              ) : (
                resistances.map((level, index) => (
                  <ZoneCard
                    key={level.id}
                    level={level}
                    price={snapshot.price}
                    label={`NEXT RESISTANCE ${index + 1}`}
                  />
                ))
              )}
            </article>
          </div>
        </section>

        <section className="cheatTimeframes">
          {TIMEFRAMES.map((tf) => (
            <TimeframeSheet
              key={tf}
              timeframe={tf}
              levels={snapshot.levels[tf] ?? []}
              price={snapshot.price}
              highlighted={tf === timeframe}
            />
          ))}
        </section>

        <footer className="sheetFooter">
          <span>
            Support/resistance side is relative to the current live price and can
            change.
          </span>
          <span>{snapshot.model}</span>
        </footer>
      </article>

      <PageFooter />
    </main>
  );
}

function ZoneCard({
  level,
  price,
  label,
}: {
  level: Level;
  price: number;
  label: string;
}) {
  return (
    <div className="zoneCard">
      <span>{label}</span>
      <strong>{formatPrice(level.price)}</strong>
      <small>
        {level.role}
        <b>{levelSide(level.price, price)}</b>
      </small>
    </div>
  );
}

function TimeframeSheet({
  timeframe,
  levels,
  price,
  highlighted,
}: {
  timeframe: Timeframe;
  levels: Level[];
  price: number;
  highlighted: boolean;
}) {
  const support = nearestSupport(levels, price);
  const resistance = nearestResistance(levels, price);

  return (
    <article className="timeframeSheet">
      <header>
        <div>
          <span>{timeframe}</span>
          <b>{TIMEFRAME_LABELS[timeframe]}</b>
        </div>
        <small>{highlighted ? "Default umbrella view" : "Reference map"}</small>
      </header>
      <div className="levelMatrix">
        <div className="levelMatrixHead">
          <span>LEVEL</span>
          <span>PRICE</span>
          <span>SIDE NOW</span>
          <span>IMPORTANCE &amp; REASON</span>
        </div>
        {levels.length === 0 ? (
          <p className="noLevels">Waiting for live {timeframe} levels.</p>
        ) : (
          levels.map((level) => {
            const side = levelSide(level.price, price);
            return (
              <div key={level.id} className="levelMatrixRow">
                <span>
                  <b>{level.role}</b>
                  <small>{level.id}</small>
                </span>
                <code>{formatPrice(level.price)}</code>
                <em className={side === "support" ? "supportText" : "resistanceText"}>
                  {side === "support" ? "Support" : "Resistance"}
                </em>
                <p>
                  <b>{side === "support" ? "Support" : "Resistance"}</b>
                  {levelImportance(level, timeframe, price)}
                </p>
              </div>
            );
          })
        )}
      </div>
      <div className="dailyStrip">
        <div>
          <span>NEAREST SUPPORT</span>
          <b>{support ? formatPrice(support.price) : "—"}</b>
        </div>
        <div>
          <span>NEAREST RESISTANCE</span>
          <b>{resistance ? formatPrice(resistance.price) : "—"}</b>
        </div>
      </div>
    </article>
  );
}
