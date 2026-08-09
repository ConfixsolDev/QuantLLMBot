import type { ReactNode } from "react";

interface TopBarProps {
  connected: boolean;
  modelStatus: string;
  generating: boolean;
  onGenerateDealSheet: () => void;
  onOpenSheet: () => void;
  onOpenCheat: () => void;
}

export function TopBar({
  connected,
  modelStatus,
  generating,
  onGenerateDealSheet,
  onOpenSheet,
  onOpenCheat,
}: TopBarProps) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brandMark">GF</span>
        <div>
          <strong>GoldFlow Desk</strong>
          <small>Local market-structure command center</small>
        </div>
      </div>
      <div className="statusRow">
        <span className={`status ${connected ? "online" : ""}`}>
          <i />
          {connected ? "MT5 connected" : "MT5 offline"}
        </span>
        <span className="status model">
          <i />
          {modelStatus}
        </span>
        <button type="button" className="ghost" onClick={onOpenSheet}>
          Print sheet
        </button>
        <button type="button" className="ghost" onClick={onOpenCheat}>
          All-timeframe cheat sheet
        </button>
        <button
          type="button"
          className="primary"
          disabled={generating}
          onClick={onGenerateDealSheet}
        >
          {generating ? "Generating…" : "Generate deal sheet"}
        </button>
      </div>
    </header>
  );
}

export function PageFooter() {
  return (
    <footer>
      <span>GoldFlow Desk · Local only</span>
      <span>Research and execution support · No prediction certainty</span>
    </footer>
  );
}

export function SheetActions({
  backLabel,
  printLabel,
  onBack,
  onPrint,
}: {
  backLabel: string;
  printLabel: string;
  onBack: () => void;
  onPrint: () => void;
}) {
  return (
    <div className="sheetActions">
      <button type="button" className="ghost" onClick={onBack}>
        {backLabel}
      </button>
      <button type="button" className="primary" onClick={onPrint}>
        {printLabel}
      </button>
    </div>
  );
}

export function QuoteBlock({
  label,
  price,
  syncedAt,
}: {
  label: string;
  price: number;
  syncedAt?: string;
}) {
  return (
    <div className="quote">
      <span>{label}</span>
      <strong>{price > 0 ? price.toFixed(3) : "Waiting"}</strong>
      {syncedAt ? <small>Synced {syncedAt}</small> : null}
    </div>
  );
}

export function CardHeading({
  kicker,
  title,
  tag,
  compact = false,
}: {
  kicker: string;
  title: string;
  tag?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`cardHeading${compact ? " compact" : ""}`}>
      <div>
        <span className="kicker">{kicker}</span>
        <h2>{title}</h2>
      </div>
      {tag}
    </div>
  );
}
