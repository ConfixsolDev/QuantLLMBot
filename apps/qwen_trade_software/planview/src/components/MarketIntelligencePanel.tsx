import type { MarketIntelligence, QwenTrace } from "@/lib/types";

function value(v: unknown) {
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

export function MarketIntelligencePanel({
  intelligence,
  trace,
}: {
  intelligence?: MarketIntelligence | null;
  trace?: QwenTrace | null;
}) {
  const hierarchy = intelligence?.hierarchy ?? {};
  const dxy = intelligence?.dxy?.states ?? {};
  const retrievals = intelligence?.recent_retrievals ?? [];
  return (
    <section className="space-y-3 rounded-lg border border-slate-700 bg-slate-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Qwen Market Memory</h2>
          <p className="text-xs text-slate-400">Persistent structure, DXY context, evidence retrieval and model trace</p>
        </div>
        <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">
          Collector {value(intelligence?.worker_health?.status)} · {value(intelligence?.relationship?.state)}
        </span>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <div className="rounded border border-slate-800 p-3">
          <h3 className="mb-2 text-sm font-medium text-gold">XAUUSD structure memory</h3>
          <div className="space-y-1 text-xs">
            {Object.entries(hierarchy).map(([tf, state]) => (
              <div key={tf} className="grid grid-cols-[42px_1fr_auto] gap-2 border-b border-slate-800 py-1">
                <span className="font-medium text-slate-200">{tf}</span>
                <span className="text-slate-400">{value(state.state)}</span>
                <span className="text-slate-300">{value(state.direction)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded border border-slate-800 p-3">
          <h3 className="mb-2 text-sm font-medium text-gold">DXY cross-market state</h3>
          <div className="space-y-1 text-xs">
            {Object.entries(dxy).map(([tf, state]) => (
              <div key={tf} className="grid grid-cols-[42px_1fr] gap-2 border-b border-slate-800 py-1">
                <span className="font-medium text-slate-200">{tf}</span>
                <span className="text-slate-400">{value(state.direction ?? state.status)}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">DXY changes confidence; XAUUSD remains execution authority.</p>
        </div>

        <div className="rounded border border-slate-800 p-3 text-xs">
          <h3 className="mb-2 text-sm font-medium text-gold">Inside Qwen</h3>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-slate-400">
            <dt>Model</dt><dd className="text-right text-slate-200">{value(trace?.model)}</dd>
            <dt>Contract</dt><dd className="text-right text-slate-200">{value(trace?.contract_version)}</dd>
            <dt>Prompt bytes</dt><dd className="text-right text-slate-200">{value(trace?.prompt_bytes)}</dd>
            <dt>Decision seconds</dt><dd className="text-right text-slate-200">{value(trace?.decision_wall_seconds)}</dd>
            <dt>Evidence cited</dt><dd className="text-right text-slate-200">{trace?.evidence_ids?.length ?? 0}</dd>
            <dt>Retrievals</dt><dd className="text-right text-slate-200">{trace?.retrieval_requests?.length ?? 0}</dd>
          </dl>
          <div className="mt-3 max-h-28 overflow-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-400">
            {trace?.raw_response || "No Qwen response recorded yet."}
          </div>
        </div>
      </div>

      {retrievals.length > 0 && (
        <div className="rounded border border-slate-800 p-3">
          <h3 className="mb-2 text-sm font-medium text-slate-200">Recent evidence requests</h3>
          <div className="space-y-1 text-xs text-slate-400">
            {retrievals.slice(0, 5).map((row) => (
              <div key={row.request_id} className="flex flex-wrap justify-between gap-2 border-b border-slate-800 py-1">
                <span>{value(row.request?.tool)} · {value(row.request?.symbol)} · {value(row.request?.timeframe)}</span>
                <span>{row.status} · {row.result?.row_count ?? 0} rows</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
