# StockVision Pro — Frontend

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind · React Query.

Dark theme only. **No authentication** — the app opens directly on the dashboard.

## Run it

Requires **Node 20+**. The backend must be running on `:8000` in another
terminal, or every card will show "Cannot reach the API".

```bash
npm install
npm run dev          # http://localhost:3000
```

Point it at the API with `NEXT_PUBLIC_API_URL` (see `.env.example`). Behind the
bundled NGINX use `/api/v1` so the browser makes no cross-origin request at all.

> `NEXT_PUBLIC_*` is compiled into the client bundle at **build** time. Changing
> it requires restarting the dev server, not just a page refresh.

### ...or run it without a backend

```bash
NEXT_PUBLIC_DEMO_MODE=true npm run dev
```

Demo mode hands axios an in-browser adapter, so the whole API surface is answered
from a generated dataset and no request leaves the page. It is on by default for
production builds (`.env.production`), which is what makes the Vercel deployment
usable on its own. Full explanation, including what is generated and what is
computed for real: [../DEMO_MODE.md](../DEMO_MODE.md).

## Layout

```
src/
├── app/
│   ├── (app)/          11 pages sharing the sidebar/topbar shell
│   ├── layout.tsx      root: fonts, providers, skip-link
│   ├── error.tsx       route error boundary
│   └── not-found.tsx
├── components/
│   ├── ui/             owned primitives (button, card, dialog, table, …)
│   ├── charts/         area, donut, gauge, sparkline, treemap, Monte Carlo,
│   │                   correlation matrix, candlestick
│   ├── layout/         sidebar, topbar, mobile nav, command palette
│   ├── dashboard/      stat card, signal panel, ticker strip
│   └── portfolio/      order and portfolio dialogs
├── context/            market provider (IN/US)
├── hooks/              React Query data layer, one file per domain
├── lib/                api client, formatting, query keys, navigation
│   └── demo/           in-browser API stand-in (see ../DEMO_MODE.md)
└── types/              the API contract, mirrored from the Pydantic schemas
```

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Dev server |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (flat config) |
| `npm run format` | Prettier |
| `npm run check:no-auth` | CI guard: assert auth has not returned |
| `npm run verify` | typecheck + lint + no-auth + build |

## Conventions

- **Query keys** are built in `lib/query-keys.ts`, never inlined — inline keys are
  how cache invalidation silently breaks.
- **The market is context**, not a prop. Every data hook reads it, so a page
  cannot request US data while the switcher says India.
- **Formatting is market-driven.** `formatNumber` picks Indian lakh/crore or
  western grouping from the market, not the browser locale.
- **Every data view** handles loading, error and empty states. `ErrorState`
  renders "nothing here yet" API codes as empty states, not as red errors.
- **`any` is a lint error.** Write a real type guard instead (see
  `isCandlestickSeries` in `components/charts/price-chart.tsx`).

## Notes on dependency choices

- **Next.js 16, not 15.** The project already ran 16.2.10 with React 19 and works;
  downgrading a working setup is a regression, not a modernization.
- **`@tanstack/react-virtual`, not `react-virtualized`.** The latter does not
  support React 19 at all.
- **Lightweight Charts, not a TradingView embed.** Same rendering engine, running
  locally — an embedded widget needs an outbound connection to tradingview.com and
  renders an empty box in a network-restricted deployment.
- **Hand-rolled SVG sparkline.** 40+ render per view; Recharts mounts a
  ResizeObserver per instance and at that count it is measurable scroll jank.
