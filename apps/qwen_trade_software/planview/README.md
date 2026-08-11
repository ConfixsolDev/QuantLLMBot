# GoldFlow Plan View

Sole local UI for the session-hierarchy planner and live chart map.

## Prerequisites

- Backend running: `software_runtime.py` (reviewer API on `:48632`, planner on lock `:48634`)
- Node.js 20+

## Development

```powershell
cd apps/qwen_trade_software/planview
npm install
npm run dev
```

Open http://localhost:3000 — polls `GET /plan` (15s) and `GET /candles` (30s).

Optional: set `NEXT_PUBLIC_API_BASE=http://127.0.0.1:48632` in `.env.local`.

## Production (IIS static export)

```powershell
# From backend/ as Administrator:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install-planview-iis.ps1
```

Serves the built `out/` folder at http://127.0.0.1:8088/ and http://127.0.0.1/  
(also removes the stock Default Web Site and the retired GoldFlow Desk site).

## UI panels

- Header clock (UTC, session, hour-of-session, next boundary countdown)
- Session timeline (Tokyo → London → Overlap → NY)
- Lightweight Charts candlestick (M5/M15/H1) with day levels and session zones
- Hour validation card (plan vs actual OHLC for selected closed hour)
- Day plan panel (both scenarios + validator verdict)
- On-chart Cheat sheet

## Pages

| Path | Purpose |
|------|---------|
| `/` | Chart, day branches, funnel, cheat sheet |
| `/ideas/` | Trade ideas with confidence &gt; 50%, stop/target distances, R:R, geometry skips |

## API endpoints (reviewer.py)

| Endpoint | Description |
|----------|-------------|
| `GET /plan` | Current `planner-state.json` |
| `GET /candles?tf=M15&count=200` | OHLC from cache SQLite |
| `GET /plan/history?date=YYYY-MM-DD` | Replay tick-data JSONL for a day |
| `GET /snapshot` | Merged entry + management dashboard |
| `GET /trade-ideas?min_confidence=50` | High-confidence ideas + geometry / R:R outcome |
