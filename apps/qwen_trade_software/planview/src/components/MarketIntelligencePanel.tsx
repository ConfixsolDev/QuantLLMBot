import type { MarketIntelligence, QwenTrace } from "@/lib/types";

function value(v: unknown) {
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

export function MarketIntelligencePanel({
  intelligence,
  trace,
  gate,
}: {
  intelligence?: MarketIntelligence | null;
  trace?: QwenTrace | null;
  gate?: { fingerprint?: string; called_at_epoch?: number; reason?: string } | null;
}) {
  const hierarchy = intelligence?.hierarchy ?? {};
  const dxy = intelligence?.dxy?.states ?? {};
  const retrievals = intelligence?.recent_retrievals ?? [];
  const graph = intelligence?.graph_context;
  const graphSymbol = Object.values(graph?.symbols ?? {})[0];
  const structureEvidence = graphSymbol?.structure_evidence ?? {};
  const recentStructure = Object.values(structureEvidence)
    .flat()
    .sort((a, b) => String(b.event_time_utc ?? "").localeCompare(String(a.event_time_utc ?? "")))
    .slice(0, 10);
  const temporalStructure = graph?.xauusd_all_timeframe_temporal_structure ?? [];
  const zonePositions = Object.entries(graph?.active_zone_positions ?? {})
    .filter(([key, zone]) => key !== "selection_rule" && zone && typeof zone === "object")
    .map(([key, zone]) => ({ key, zone: zone as Record<string, unknown> }));
  const zonePlan = graph?.active_zone_plan;
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
            <dt>Last trigger</dt><dd className="text-right text-slate-200">{value(gate?.reason)}</dd>
          </dl>
          <div className="mt-3 max-h-28 overflow-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-400">
            {trace?.raw_response || "No Qwen response recorded yet."}
          </div>
        </div>
      </div>

      <div className="rounded border border-slate-800 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-medium text-gold">Neo4j market explanation</h3>
            <p className="text-xs text-slate-500">
              Closed-candle evidence only · shadow analysis · no execution authority
            </p>
          </div>
          <span className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-400">
            Graph {value(graph?.status)} · {value(graph?.packet_bytes)} bytes · pending {value(graph?.projection?.pending)}
          </span>
        </div>
        {temporalStructure.length > 0 ? (
          <div className="mt-3 space-y-3">
            <div className="rounded border border-gold/40 bg-gold/5 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-semibold uppercase tracking-wide text-gold">Neutral zone relationships</div>
                <div className="text-slate-400">No directional authority · {value(zonePlan?.status)}</div>
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                <div><span className="text-slate-500">Focus: </span><span className="text-slate-100">{value(zonePlan?.focus_zone?.zone_low)}–{value(zonePlan?.focus_zone?.zone_high)}</span> <span className="text-slate-500">({value(zonePlan?.focus_zone?.primary_owning_timeframe)})</span></div>
                <div><span className="text-slate-500">Support below: </span><span className="text-slate-100">{value(zonePlan?.support_below?.zone_low)}–{value(zonePlan?.support_below?.zone_high)}</span></div>
                <div><span className="text-slate-500">Resistance above: </span><span className="text-slate-100">{value(zonePlan?.resistance_above?.zone_low)}–{value(zonePlan?.resistance_above?.zone_high)}</span></div>
              </div>
              <div className="mt-2 text-slate-500">Zones remain explicit bands. Distance is measured to the nearest boundary, never a midpoint.</div>
            </div>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              {temporalStructure.map((row) => (
                <div key={row.timeframe} className="rounded bg-slate-950/70 p-2 text-xs">
                  <div className="flex justify-between gap-2 text-slate-200">
                    <span className="font-medium">{value(row.timeframe)} · {value(row.trend_state)}</span>
                    <span className="text-slate-500">{value(row.freshness)}</span>
                  </div>
                  <div className="mt-1 text-slate-400">{value(row.auction_state)} · {value(row.range_location)}</div>
                  <div className="mt-1 text-slate-500">{value(row.latest_structure)} · volume ratio {value(row.volume_confirmation?.ratio)}</div>
                </div>
              ))}
            </div>
            <div className="grid gap-2 lg:grid-cols-3">
              {zonePositions.map(({ key, zone }) => (
                <div key={key} className="rounded border border-slate-800 bg-slate-950/50 p-2 text-xs">
                  <div className="font-medium text-slate-200">{key.replaceAll("_", " ")}</div>
                  <div className="mt-1 text-slate-400">
                    {value(zone.zone_low)}–{value(zone.zone_high)} · owner {value(zone.primary_owning_timeframe)}
                  </div>
                  <div className="mt-1 text-slate-500">{value(zone.structural_proof)} · {Array.isArray(zone.contributing_timeframes) ? zone.contributing_timeframes.join("/") : "—"}</div>
                </div>
              ))}
            </div>
          </div>
        ) : recentStructure.length > 0 ? (
          <div className="mt-3 grid gap-2 lg:grid-cols-2">
            {recentStructure.map((event) => (
              <div key={event.id} className="rounded bg-slate-950/70 p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-200">
                    {value(event.timeframe)} · {value(event.event_type)} {event.structure_label ? `· ${event.structure_label}` : ""}
                  </span>
                  <span className="text-slate-500">{value(event.status)}</span>
                </div>
                <div className="mt-1 text-slate-400">
                  {event.explanation || (event.zone_kind ? `${event.zone_kind} ${value(event.zone_low)}–${value(event.zone_high)}` : value(event.direction))}
                  {event.zone_status ? ` · ${event.zone_status}` : ""}
                </div>
                <div className="mt-1 truncate font-mono text-[10px] text-slate-600" title={event.evidence_id}>
                  {value(event.event_time_utc)} · {value(event.evidence_id)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs text-slate-500">
            No projected structure labels yet. The deterministic backfill remains dry-run until the current graph queue is safe to extend.
          </p>
        )}
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
