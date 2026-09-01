const $ = (id) => document.getElementById(id);
const value = (input, fallback = "—") => input === null || input === undefined || input === "" ? fallback : String(input);
const eventPayload = (event) => event?.payload ?? {};
const price = (input) => Number.isFinite(Number(input)) ? Number(input).toFixed(3) : "—";
const shortId = (input) => input ? `${String(input).slice(0, 11)}…${String(input).slice(-6)}` : "None";
const utcTime = (input, date = false) => input ? new Date(input).toLocaleString([], { timeZone: "UTC", hour12: false, ...(date ? {} : { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }) + " UTC" : "—";
const words = (input) => value(input).replaceAll("_", " ");
const put = (id, input, fallback) => { const node = $(id); if (node) node.textContent = value(input, fallback); };
let selectedTimeframe = "M15";
let chartState = { market: {}, plan: {}, risk: {} };
let tvChart = null;
let tvCandleSeries = null;
let tvZoneSeries = [];
let tvPriceLines = [];
let tvResizeObserver = null;

function routeName() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  return ({ "/": "market", "/operations": "operations", "/history": "history", "/trades": "trades" })[path] || "market";
}

function showRoute() {
  const route = routeName();
  document.querySelectorAll("[data-view]").forEach((node) => { node.hidden = node.dataset.view !== route; });
  document.querySelectorAll("[data-route]").forEach((node) => node.classList.toggle("active", node.dataset.route === route));
}

function setDot(id, state) {
  const node = $(id); if (!node) return;
  node.className = `dot ${state === true || state === "ok" ? "ok" : state === false || state === "down" ? "down" : "warn"}`;
}

function candleAge(bar) {
  return bar?.end_utc ? Math.max(0, Math.round((Date.now() - new Date(bar.end_utc).getTime()) / 1000)) : null;
}

function freshnessLabel(timeframe, bar) {
  if (!bar) return { stale: true, label: "Unavailable" };
  const limits = { D1: 259200, H4: 43200, H1: 10800, M30: 5400, M15: 2700 };
  const age = candleAge(bar);
  return { stale: age === null || age > limits[timeframe], label: age === null ? "Unknown" : age < 120 ? `${age}s ago` : age < 7200 ? `${Math.round(age / 60)}m ago` : `${Math.round(age / 3600)}h ago` };
}

function renderLadder(market, plan = {}, risk = {}) {
  const host = $("candle-ladder"); if (!host) return;
  const frames = ["D1", "H4", "H1", "M30", "M15"];
  const audit = market.timeframe_audit || {}, expectation = audit.expectation || {}, outcome = audit.outcome || {};
  const currentTarget = Number(plan.target || risk.target_price), planDirection = String(plan.direction || "").toLowerCase();
  host.replaceChildren(...frames.map((timeframe) => {
    const bars = market.timeframes?.[timeframe] || [], bar = bars.at(-1), forming = market.forming?.[timeframe], fresh = freshnessLabel(timeframe, bar);
    const direction = !bar ? "missing" : bar.close > bar.open ? "up" : bar.close < bar.open ? "down" : "flat";
    const relationship = (market.relationships || []).find((row) => row.child_timeframe === timeframe) || (timeframe === "D1" ? (market.relationships || []).find((row) => row.parent_timeframe === "D1") : null);
    const relation = relationship ? `${words(relationship.relationship)} · ${words(relationship.child_direction || relationship.parent_direction)}` : "No relationship read";
    const expected = expectation.frames?.[timeframe]?.expected_direction || "pending";
    const assessed = outcome.frames?.[timeframe] || {};
    const result = assessed.result || "PENDING";
    const actual = assessed.m15_contribution_direction || "awaiting next M15";
    const targetHit = Number.isFinite(currentTarget) && bar && (planDirection === "buy" ? Number(bar.high) >= currentTarget : planDirection === "sell" ? Number(bar.low) <= currentTarget : false);
    const distance = Number.isFinite(currentTarget) && bar ? Math.abs(currentTarget - Number(bar.close)).toFixed(3) : null;
    const card = document.createElement("article"); card.className = `ladder-card ${direction} ${fresh.stale ? "stale" : ""}`;
    const header = document.createElement("header"), title = document.createElement("h3"), badge = document.createElement("span"); title.textContent = timeframe; badge.textContent = !bar ? "NO BAR" : direction === "up" ? "UP CLOSE" : direction === "down" ? "DOWN CLOSE" : "FLAT"; header.append(title, badge);
    const grid = document.createElement("div"); grid.className = "ladder-ohlc";
    [["Open",price(bar?.open)],["High",price(bar?.high)],["Low",price(bar?.low)],["Close",price(bar?.close)]].forEach(([label,val]) => { const box=document.createElement("div"),a=document.createElement("span"),b=document.createElement("b");a.textContent=label;b.textContent=val;box.append(a,b);grid.append(box); });
    const auditGrid = document.createElement("div"); auditGrid.className = "ladder-audit";
    [["Building now", forming ? `${forming.close >= forming.open ? "UP" : "DOWN"} · ${price(forming.close)}` : "Unavailable", forming ? "forming active" : "forming"], ["Expected next", words(expected), `expectation ${expected}`], ["Last M15 result", `${words(result)} · ${words(actual)}`, `outcome ${result.toLowerCase()}`], ["Current plan target", Number.isFinite(currentTarget) ? `${price(currentTarget)} · ${targetHit ? "HIT" : `${distance} away`}` : "No active target", targetHit ? "target hit" : "target"]].forEach(([label,val,cls]) => { const row=document.createElement("div"),a=document.createElement("span"),b=document.createElement("b");a.textContent=label;b.textContent=val;b.className=cls;row.append(a,b);auditGrid.append(row); });
    const footer = document.createElement("footer"), relationNode = document.createElement("b"), age = document.createElement("small"); relationNode.textContent = relation; age.textContent = `${fresh.label} · ${bars.length} candles · next check ${utcTime(expectation.target_close_utc)}`; footer.append(relationNode, age); card.append(header, grid, auditGrid, footer); return card;
  }));
}

function chartPlanLines(plan, risk) {
  return [
    { label: "ENTRY", value: Number(plan.entry_price || risk.entry_price), color: "#d4a017" },
    { label: "STOP", value: Number(plan.stop || risk.stop_price), color: "#fb7185" },
    { label: "TARGET", value: Number(plan.target || risk.target_price), color: "#6ee7b7" },
  ].filter((line) => Number.isFinite(line.value));
}

function drawMarketChart() {
  const container = $("market-chart"); if (!container) return;
  const bars = (chartState.market.timeframes?.[selectedTimeframe] || []).slice(-120);
  const forming = chartState.market.forming?.[selectedTimeframe] || null;
  put("chart-timeframe", selectedTimeframe); put("chart-pair", chartState.market.pair, "XAUUSD");
  if (!window.LightweightCharts) {
    container.textContent = "TradingView chart library is unavailable.";
    put("chart-status", "Unavailable"); return;
  }
  if (!tvChart) {
    tvChart = LightweightCharts.createChart(container, {
      width: Math.max(300, container.clientWidth), height: 390,
      layout: { background: { type: LightweightCharts.ColorType.Solid, color: "#0b0f17" }, textColor: "#9aa9bd", fontSize: 15 },
      grid: { vertLines: { color: "#1b2533" }, horzLines: { color: "#1b2533" } },
      rightPriceScale: { borderColor: "#334155", scaleMargins: { top: .08, bottom: .08 } },
      timeScale: { borderColor: "#334155", timeVisible: true, secondsVisible: false, rightOffset: 3, barSpacing: 8 },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      localization: { priceFormatter: (number) => Number(number).toFixed(3) },
    });
    tvCandleSeries = tvChart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
      priceFormat: { type: "price", precision: 3, minMove: .001 },
    });
    tvResizeObserver = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width > 0) tvChart?.applyOptions({ width: Math.floor(width) });
    });
    tvResizeObserver.observe(container);
  }
  tvChart.applyOptions({ timeScale: { timeVisible: selectedTimeframe !== "D1" } });
  tvZoneSeries.forEach((series) => tvChart.removeSeries(series)); tvZoneSeries = [];
  tvPriceLines.forEach((line) => tvCandleSeries.removePriceLine(line)); tvPriceLines = [];
  if (!bars.length) {
    tvCandleSeries.setData([]);
    put("chart-caption",`V2 has not supplied a completed ${selectedTimeframe} candle yet.`);put("chart-close","—");put("chart-change","—");put("chart-range","—");put("chart-status","Unavailable");return;
  }
  const chartBars = forming && forming.start_utc !== bars.at(-1)?.start_utc ? [...bars, forming] : bars;
  const candles = chartBars.map((bar) => ({ time: Math.floor(new Date(bar.start_utc).getTime()/1000), open:Number(bar.open), high:Number(bar.high), low:Number(bar.low), close:Number(bar.close), ...(bar.is_forming ? {color:bar.close>=bar.open?"rgba(34,197,94,.48)":"rgba(239,68,68,.48)",borderColor:"#f0c95c",wickColor:"#f0c95c"}:{}) }));
  tvCandleSeries.setData(candles);
  const firstTime=candles[0].time,lastTime=candles.at(-1).time;
  (chartState.market.zones||[]).filter((zone)=>Number.isFinite(Number(zone.lower))&&Number.isFinite(Number(zone.upper))).slice(0,5).forEach((zone)=>{
    [Number(zone.lower),Number(zone.upper)].forEach((level,index)=>{const series=tvChart.addLineSeries({color:index?"rgba(125,211,252,.5)":"rgba(125,211,252,.32)",lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dotted,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false,title:index?"Zone high":"Zone low"});series.setData([{time:firstTime,value:level},{time:lastTime,value:level}]);tvZoneSeries.push(series)});
  });
  chartPlanLines(chartState.plan,chartState.risk).forEach((line)=>tvPriceLines.push(tvCandleSeries.createPriceLine({price:line.value,color:line.color,lineWidth:2,lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:true,title:line.label})));
  tvChart.timeScale().fitContent();
  let low=Math.min(...bars.map((bar)=>Number(bar.low))), high=Math.max(...bars.map((bar)=>Number(bar.high)));const rawRange=Math.max(.001,high-low);low-=rawRange*.08;high+=rawRange*.08;
  const last=bars.at(-1),move=Number(last.close)-Number(last.open),fresh=freshnessLabel(selectedTimeframe,last);put("chart-caption",`${bars.length} completed ${selectedTimeframe} candles · latest ended ${utcTime(last.end_utc)}${forming?` · FORMING ${price(forming.close)}`:" · forming unavailable"}`);put("chart-close",forming?`${price(last.close)} / ${price(forming.close)}`:price(last.close));put("chart-change",`${move>=0?"+":""}${move.toFixed(3)}`);put("chart-range",`${low.toFixed(2)} – ${high.toFixed(2)}`);put("chart-status",`${fresh.stale?"Stale":"Fresh"} · ${fresh.label}${forming?" · FORMING":""}`);
}

function renderMarketData(market={},plan={},risk={}) {
  chartState={market,plan,risk};renderLadder(market,plan,risk);drawMarketChart();
}

function eventSummary(event) {
  const data = eventPayload(event);
  return data.state || data.decision || data.status || data.reason || data.candidate_id || data.state_hash || event.pair || "Recorded";
}

function renderTimeline(events) {
  const host = $("today-timeline"); if (!host) return;
  const useful = (events || []).filter((event) => !["MAGIC_POSITION_SNAPSHOT", "PAIR_MARKET_STATE_COMPOSED"].includes(event.event_type)).slice(0, 6);
  if (!useful.length) { host.innerHTML = '<p class="empty">No decision events recorded today.</p>'; return; }
  host.replaceChildren(...useful.map((event) => {
    const item = document.createElement("div"); item.className = "timeline-item";
    const time = document.createElement("span"); time.textContent = utcTime(event.observed_at_utc);
    const name = document.createElement("b"); name.textContent = words(event.event_type);
    const note = document.createElement("small"); note.textContent = value(eventSummary(event));
    item.append(time, name, note); return item;
  }));
}

function renderEvents(events) {
  const host = $("events"); if (!host) return;
  host.replaceChildren(...(events || []).slice(0, 18).map((event) => {
    const li = document.createElement("li"), text = document.createElement("div"), title = document.createElement("b"), summary = document.createElement("small"), time = document.createElement("time");
    title.textContent = event.event_type; summary.textContent = value(eventSummary(event)); time.textContent = utcTime(event.observed_at_utc); text.append(title, summary); li.append(text, time); return li;
  }));
}

function renderHistory(history = {}) {
  const daily = history.daily || [], hourly = history.hourly || [];
  const totals = history.totals || {};
  const cards = [
    ["Ledger events", totals.events || 0, "Immutable records in selected history"],
    ["Candidates", totals.candidates || 0, "Strategy-created opportunities"],
    ["Risk approvals", totals.risk_approved || 0, "Passed the common risk gate"],
    ["Broker attempts", totals.orders || 0, "Submitted order records"],
  ];
  const host = $("history-cards"); if (host) host.replaceChildren(...cards.map(([label, number, note]) => {
    const card = document.createElement("article"); card.className = "history-card";
    const a = document.createElement("span"), b = document.createElement("strong"), c = document.createElement("small"); a.textContent = label; b.textContent = Number(number).toLocaleString(); c.textContent = note; card.append(a,b,c); return card;
  }));
  const chart = $("history-chart"); if (!chart) return;
  const points = hourly.length ? hourly : daily;
  if (!points.length) { chart.innerHTML = '<p class="empty">History will appear as V2 events accumulate.</p>'; return; }
  const max = Math.max(...points.map((row) => Number(row.events || 0)), 1);
  chart.replaceChildren(...points.slice(-24).map((row) => {
    const bar = document.createElement("div"); bar.className = "history-bar";
    const rail = document.createElement("i"), fill = document.createElement("b"), label = document.createElement("span"), count = document.createElement("small");
    fill.style.height = `${Math.max(2, Math.round(Number(row.events || 0) / max * 100))}%`; rail.append(fill);
    label.textContent = row.bucket ? utcTime(row.bucket).replace(/:\d{2} UTC$/, "") : row.day; count.textContent = `${row.events} events`;
    bar.append(rail,label,count); return bar;
  }));
}

function brokerMessage(record) {
  const raw = record.broker_result?.broker_response?.raw;
  return Array.isArray(raw) ? value(raw[7], "No broker comment") : value(record.broker_result?.message, "No broker comment");
}

function renderTrades(trades = {}) {
  const rows = trades.records || [], host = $("trade-list");
  put("trade-count", `${rows.length} records`);
  put("trade-scope-note", trades.scope_note, "V2 trade details are loading.");
  if (!host) return;
  if (!rows.length) { host.innerHTML = '<p class="empty">No V2 broker attempts have been recorded.</p>'; return; }
  host.replaceChildren(...rows.map((record) => {
    const order = record.order || {}, result = record.broker_result || {};
    const details = document.createElement("details"); details.className = "trade-card";
    const summary = document.createElement("summary");
    const fields = [
      ["Order", `${value(order.direction, "—").toUpperCase()} ${value(order.pair)}`, utcTime(record.observed_at_utc, true), "trade-main"],
      ["Entry", price(order.entry_price)], ["Stop / target", `${price(order.stop)} / ${price(order.target)}`],
      ["Volume", value(order.volume)], ["Broker state", value(result.state)],
    ];
    fields.forEach(([label, main, sub, cls]) => { const box=document.createElement("div"); if(cls) box.className=cls; const a=document.createElement("span"),b=document.createElement("b"); a.textContent=label;b.textContent=main;box.append(a,b);if(sub){const c=document.createElement("small");c.textContent=sub;box.append(c)}summary.append(box); });
    const arrow=document.createElement("span");arrow.textContent="Details ↓";summary.append(arrow);
    const body=document.createElement("div");body.className="trade-detail";const grid=document.createElement("div");grid.className="trade-detail-grid";
    [["Strategy",record.strategy_id],["Candidate",shortId(record.candidate_id)],["Magic",record.magic_number],["Order ID",order.order_id],["Risk hash",shortId(order.risk_hash)],["State hash",shortId(order.state_hash)],["Comment",record.comment],["Filled volume",result.filled_volume]].forEach(([label,val])=>{const box=document.createElement("div"),a=document.createElement("span"),b=document.createElement("b");a.textContent=label;b.textContent=value(val);box.append(a,b);grid.append(box)});
    const note=document.createElement("p");note.className="raw-note";note.textContent=`Broker response: ${brokerMessage(record)}`;body.append(grid,note);details.append(summary,body);return details;
  }));
}

function renderSystem(health = {}) {
  const services = health.services || {};
  const entries = Object.entries(services);
  const healthy = entries.filter(([, item]) => item.ok === true).length;
  put("system-summary", entries.length ? `${healthy}/${entries.length} services healthy` : "Health detail unavailable");
  setDot("system-dot", entries.length && healthy === entries.length ? true : healthy > 0 ? "warn" : false);
  const aliases = { model_host:["model-dot","model-short"], mt5:["mt5-dot","mt5-short"], timescale:["data-dot","data-short"] };
  Object.entries(aliases).forEach(([key,[dot,label]])=>{ const item=services[key]||{}; setDot(dot,item.ok); put(label,item.short,item.ok===true?"online":item.ok===false?"offline":"unknown"); });
  const grid=$("system-grid"); if (!grid) return;
  if (!entries.length) { grid.innerHTML='<p class="empty">Detailed health probes are not available yet.</p>'; return; }
  grid.replaceChildren(...entries.map(([key,item])=>{const card=document.createElement("article");card.className="system-item";const dot=document.createElement("span");dot.className=`dot ${item.ok===true?"ok":item.ok===false?"down":"warn"}`;const text=document.createElement("div"),title=document.createElement("b"),detail=document.createElement("small");title.textContent=item.label||words(key);detail.textContent=item.detail||item.short||"No detail";text.append(title,detail);card.append(dot,text);return card;}));
}

function render(data) {
  const latest=data.latest||{}, debug=eventPayload(latest.VNEXT_DEBUG_CYCLE), lifecycle=eventPayload(latest.STRATEGY_LIFECYCLE), qwen=eventPayload(latest.QWEN_ARBITRATION), market=eventPayload(latest.PAIR_MARKET_STATE_COMPOSED), broker=eventPayload(latest.MAGIC_POSITION_SNAPSHOT), risk=eventPayload(latest.RISK_DECISION), submitted=eventPayload(latest.ORDER_SUBMITTED), order=submitted.order||{}, result=submitted.broker_result||{};
  const positions=Array.isArray(broker.positions)?broker.positions:[], recovery=broker.recovery_plan||{}, blockers=debug.candidate_blockers||[];
  put("market-pair",latest.PAIR_MARKET_STATE_COMPOSED?.pair||order.pair||"XAUUSD");put("frontier",utcTime(market.timefrontier||debug.frontier_utc));
  put("market-posture",order.direction?`${order.direction.toUpperCase()} PLAN`:"OBSERVING");put("market-posture-note",order.direction?"Latest complete broker-bound geometry":"No directional geometry is currently recorded");
  put("opportunity-status",words(lifecycle.state),"NO STATE");put("opportunity-note",lifecycle.candidate_id?`Candidate ${shortId(lifecycle.candidate_id)}`:"Waiting for a strategy candidate");
  put("entry-status",blockers.length?"BLOCKED":debug.entry_gate_reason==="calendar_clear"?"CLEAR":"WAITING");put("entry-note",blockers.length?blockers.map(words).join(" · "):words(debug.entry_gate_reason),"No current gate result");
  put("positions",`${positions.length} open`);put("recovery",recovery.safe_to_resume===true?"Broker reconciliation clear":(recovery.reasons||[]).join(", "),"No recovery status");
  put("plan-state",value(result.state,lifecycle.state||"NO ACTIVE PLAN"));put("plan-direction",order.direction?order.direction.toUpperCase():"WAIT");put("plan-headline",order.direction?`${order.direction.toUpperCase()} ${order.pair} with fixed V2 geometry`:"No broker-bound plan yet");put("plan-reason",qwen.reason||debug.qwen_reason,"The app remains fail-closed until the strategy supplies complete geometry.");
  put("plan-entry",price(order.entry_price));put("plan-stop",price(order.stop||risk.stop_price));put("plan-target",price(order.target||risk.target_price));put("plan-volume",value(order.volume||risk.normalized_volume));put("right-now",blockers.length?`Waiting: ${blockers.map(words).join(" · ")}`:lifecycle.state?`Current lifecycle: ${words(lifecycle.state)}`:"Collecting completed market evidence");
  put("bars",`${value(market.completed_bars||debug.completed_m1_bars,0)} bars`);put("zones",debug.zone_count,0);put("structures",debug.structure_event_count,0);put("timeframes",(debug.story_timeframes||[]).join(" · "),"Not recorded");put("calendar-gate",words(debug.entry_gate_reason),"Not checked");
  $("zone-meter").style.width=`${Math.min(100,Number(debug.zone_count||0)*5)}%`;$("structure-meter").style.width=`${Math.min(100,Number(debug.structure_event_count||0))}%`;
  put("mode",debug.mode,"V2 LEDGER");put("lifecycle",words(lifecycle.state),"NO STATE");put("strategy",lifecycle.strategy_id||debug.strategy_id,"No strategy event");put("decision",qwen.decision||debug.qwen_decision,"NO DECISION");put("decision-reason",qwen.reason||debug.qwen_reason,"No recent strategy decision");put("risk-status",risk.approved===true?"APPROVED":risk.approved===false?"REJECTED":"NO DECISION");put("risk-note",risk.approved===true?`$${value(risk.risk_amount)} · ${value(risk.normalized_volume)} lots`:(risk.reasons||[]).join(", "),"No current risk record");put("order-status",result.state,"NO ORDER");put("order-note",order.order_id?`${shortId(order.order_id)} · ${brokerMessage(submitted)}`:"No current order record");
  put("flow-state",shortId(market.state_hash||debug.state_hash));put("flow-candidate",shortId(lifecycle.candidate_id||debug.candidate_id));put("flow-qwen",qwen.decision||debug.qwen_decision,"No decision");put("flow-order",order.order_id?`${result.state||"RECORDED"} · ${shortId(order.order_id)}`:risk.approved===true?"Risk approved":"No new order");put("ops-zones",debug.zone_count,0);put("ops-structures",debug.structure_event_count,0);put("entry-gate",words(debug.entry_gate_reason));put("event-total",Object.values(data.counts_24h||{}).reduce((sum,count)=>sum+Number(count),0).toLocaleString());
  const age=data.freshness_seconds;put("freshness",age===null?"No ledger data":age<=90?`Live · ${age}s`:`Stale · ${age}s`);put("generated",`Updated ${utcTime(data.generated_at_utc)}`);setDot("data-dot",age!==null&&age<=90);put("data-short",age===null?"empty":age<=90?"live":"stale");
  renderMarketData(data.market_data,order,risk);renderTimeline(data.recent_events);renderEvents(data.recent_events);renderHistory(data.history);renderTrades(data.trades);renderSystem(data.system_health);
}

async function refresh(){try{const response=await fetch("/api/status",{cache:"no-store"});if(!response.ok)throw new Error(`HTTP ${response.status}`);render(await response.json())}catch(error){put("freshness","Status unavailable");setDot("data-dot",false);const host=$("events");if(host){const item=document.createElement("li");item.className="empty";item.textContent=`Could not read the V2 ledger: ${error.message}`;host.replaceChildren(item)}}}
function tick(){put("clock",new Date().toLocaleString([],{timeZone:"UTC",hour12:false})+" UTC")}
const modal=$("system-modal");const openModal=()=>modal?.showModal();$("open-system")?.addEventListener("click",openModal);document.querySelectorAll("[data-open-system]").forEach(node=>node.addEventListener("click",openModal));$("close-system")?.addEventListener("click",()=>modal?.close());modal?.addEventListener("click",event=>{if(event.target===modal)modal.close()});$("refresh")?.addEventListener("click",refresh);
document.querySelectorAll("[data-timeframe]").forEach((button)=>button.addEventListener("click",()=>{selectedTimeframe=button.dataset.timeframe;document.querySelectorAll("[data-timeframe]").forEach((item)=>item.classList.toggle("active",item===button));drawMarketChart()}));
showRoute();tick();refresh();setInterval(tick,1000);setInterval(refresh,15000);
