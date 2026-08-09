import { useCallback, useEffect, useState } from "react";
import { fetchSnapshot, requestDealSheet } from "@/lib/api";
import type { DeskView, Snapshot, Timeframe } from "@/lib/types";
import { DEFAULT_SNAPSHOT } from "@/lib/types";
import { DashboardView } from "@/views/DashboardView";
import { SheetView } from "@/views/SheetView";
import { CheatView } from "@/views/CheatView";

const SNAPSHOT_POLL_MS = 10_000;
const DEAL_SHEET_POLL_MS = 60_000;

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot>(DEFAULT_SNAPSHOT);
  const [view, setView] = useState<DeskView>("dashboard");
  const [timeframe, setTimeframe] = useState<Timeframe>("M15");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async () => {
    try {
      const data = await fetchSnapshot();
      setSnapshot(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reviewer unavailable");
    }
  }, []);

  const generateDealSheet = useCallback(async () => {
    setGenerating(true);
    try {
      const data = await requestDealSheet();
      setSnapshot(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deal sheet failed");
    } finally {
      setGenerating(false);
    }
  }, []);

  useEffect(() => {
    loadSnapshot();
    const timer = window.setInterval(loadSnapshot, SNAPSHOT_POLL_MS);
    return () => window.clearInterval(timer);
  }, [loadSnapshot]);

  useEffect(() => {
    const timer = window.setInterval(generateDealSheet, DEAL_SHEET_POLL_MS);
    return () => window.clearInterval(timer);
  }, [generateDealSheet]);

  if (view === "sheet") {
    return (
      <SheetView
        snapshot={snapshot}
        timeframe={timeframe}
        onBack={() => setView("dashboard")}
      />
    );
  }

  if (view === "cheat") {
    return (
      <CheatView
        snapshot={snapshot}
        timeframe={timeframe}
        onBack={() => setView("dashboard")}
      />
    );
  }

  return (
    <main>
      {error && (
        <p style={{ color: "var(--red)", fontSize: 12, paddingTop: 12 }}>
          {error} — ensure backend is running on :48632.
        </p>
      )}
      <DashboardView
        snapshot={snapshot}
        timeframe={timeframe}
        generating={generating}
        onTimeframeChange={setTimeframe}
        onGenerateDealSheet={generateDealSheet}
        onOpenSheet={() => setView("sheet")}
        onOpenCheat={() => setView("cheat")}
      />
    </main>
  );
}
