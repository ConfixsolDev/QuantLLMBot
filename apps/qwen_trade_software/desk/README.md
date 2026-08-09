# GoldFlow Desk (source)

Editable React source for the IIS production bundle in `../website/`.

## Commands

```powershell
cd apps/qwen_trade_software/desk
npm install
npm run dev      # http://127.0.0.1:5173 with API proxy to :48632
npm run build    # writes static bundle to ../website/
```

## Layout

- `src/views/DashboardView.tsx` — main desk (chart map, Qwen card, trade idea, metrics)
- `src/views/SheetView.tsx` — printable chart detail sheet
- `src/views/CheatView.tsx` — all-timeframe level cheat sheet
- `src/components/PriceLadderChart.tsx` — shared CSS price-ladder chart
- `src/lib/api.ts` — `/snapshot` and `/deal-sheet` calls
- `src/index.css` — GoldFlow Desk styles (matches production bundle)

Deploy to IIS with `backend/install-iis-website.ps1` after `npm run build`.
