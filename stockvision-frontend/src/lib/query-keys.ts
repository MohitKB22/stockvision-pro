import type { MarketCode } from "@/types";

/**
 * Centralized React Query keys.
 *
 * Every key is built here rather than inlined at call sites. Inline keys are how
 * cache invalidation silently stops working: one file writes `["portfolio", id]`
 * and another invalidates `["portfolios", id]`, and the stale-data bug that
 * follows is nearly impossible to spot in review.
 */
export const queryKeys = {
  markets: ["markets"] as const,
  session: (market: MarketCode) => ["market", "session", market] as const,

  overview: (market: MarketCode) => ["market", "overview", market] as const,
  indices: (market: MarketCode) => ["market", "indices", market] as const,
  indexConstituents: (market: MarketCode, index: string) =>
    ["market", "indices", market, index, "constituents"] as const,
  movers: (market: MarketCode, limit: number) => ["market", "movers", market, limit] as const,
  sectors: (market: MarketCode) => ["market", "sectors", market] as const,
  heatmap: (market: MarketCode) => ["market", "heatmap", market] as const,
  breadth: (market: MarketCode) => ["market", "breadth", market] as const,
  weekRange: (market: MarketCode) => ["market", "52week", market] as const,
  quotes: (symbols: string[]) => ["market", "quotes", [...symbols].sort().join(",")] as const,
  quote: (symbol: string) => ["market", "quote", symbol] as const,

  stocks: (market: MarketCode | undefined, sector?: string) => ["stocks", market, sector] as const,
  stock: (symbol: string) => ["stocks", symbol] as const,
  stockSearch: (q: string, market: MarketCode) => ["stocks", "search", market, q] as const,
  stockSectors: (market: MarketCode) => ["stocks", "sectors", market] as const,
  prices: (symbol: string, limit: number) => ["prices", symbol, limit] as const,
  features: (symbol: string, limit: number) => ["features", symbol, limit] as const,

  portfolios: (market: MarketCode | undefined) => ["portfolios", market] as const,
  defaultPortfolio: (market: MarketCode) => ["portfolios", "default", market] as const,
  portfolio: (id: string) => ["portfolios", id] as const,
  portfolioSummary: (id: string) => ["portfolios", id, "summary"] as const,
  portfolioPerformance: (id: string, days: number) =>
    ["portfolios", id, "performance", days] as const,
  portfolioTransactions: (id: string) => ["portfolios", id, "transactions"] as const,

  risk: (id: string, lookback: number) => ["portfolios", id, "risk", lookback] as const,
  monteCarlo: (id: string, horizon: number, sims: number) =>
    ["portfolios", id, "risk", "monte-carlo", horizon, sims] as const,
  correlation: (id: string, lookback: number) =>
    ["portfolios", id, "risk", "correlation", lookback] as const,
  stressTest: (id: string) => ["portfolios", id, "risk", "stress"] as const,

  models: ["ml", "models"] as const,
  predictionHistory: (symbol: string) => ["ml", "predictions", symbol, "history"] as const,
  forecast: (symbol: string, horizon: number) => ["ml", "forecast", symbol, horizon] as const,
  recentSignals: (limit: number) => ["ml", "signals", "recent", limit] as const,

  news: (market: MarketCode | undefined, symbol: string | undefined, limit: number) =>
    ["news", market, symbol, limit] as const,
  sentiment: (market: MarketCode) => ["news", "sentiment", market] as const,

  watchlists: (market: MarketCode) => ["watchlists", market] as const,
  defaultWatchlist: (market: MarketCode) => ["watchlists", "default", market] as const,

  documents: ["copilot", "documents"] as const,
  conversations: ["copilot", "conversations"] as const,
  conversation: (id: string) => ["copilot", "conversations", id] as const,
  copilotHistory: ["copilot", "history"] as const,
  copilotPrompts: ["copilot", "prompts"] as const,

  reports: (type?: string) => ["reports", type] as const,

  settings: ["settings"] as const,
  integrations: ["settings", "integrations"] as const,

  adminOverview: (hours: number) => ["admin", "overview", hours] as const,
  adminHealth: ["admin", "health"] as const,
  adminLogs: (limit: number, action?: string) => ["admin", "logs", limit, action] as const,
} as const;
