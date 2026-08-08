# GoldFlow Plan View

Next.js single-page app for the session-hierarchy planner. Source lives in
this repo (unlike the legacy compiled `website/` bundle).

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
.\install-planview-iis.ps1
```

Serves the built `out/` folder at http://127.0.0.1:8088/

## UI panels

- Header clock (UTC, session, hour-of-session, next boundary countdown)
- Session timeline (Tokyo → London → Overlap → NY)
- Lightweight Charts candlestick (M5/M15/H1) with day levels and session zones
- Hour validation card (plan vs actual OHLC for selected closed hour)
- Day plan panel (both scenarios + validator verdict)

## API endpoints (reviewer.py)

| Endpoint | Description |
|----------|-------------|
| `GET /plan` | Current `planner-state.json` |
| `GET /candles?tf=M15&count=200` | OHLC from cache SQLite |
| `GET /plan/history?date=YYYY-MM-DD` | Replay tick-data JSONL for a day |
