/**
 * The demo world: every instrument, index, portfolio and mutable store the
 * in-browser API serves from.
 *
 * Built once per page load and cached at module scope. That is deliberate - the
 * dashboard polls, React Query refetches, and a world rebuilt per request would
 * make prices twitch on every poll. One build means the numbers are stable for
 * the session, exactly as a real database would be.
 */

import type { MarketCode } from "@/types";

import {
  FACTOR_SEED_SUFFIX,
  HISTORY_SESSIONS,
  MARKET_CATALOG,
  MARKET_CODES,
  type CatalogMarket,
} from "./catalog";
import { computeIndicators, generateBars, type DemoBar, type IndicatorRow } from "./series";
import { makeRng, round, uniform, type Rng } from "./rng";

export interface DemoInstrument {
  id: string;
  symbol: string;
  name: string;
  sector: string;
  market: MarketCode;
  exchange: string;
  currency: string;
  marketCap: number;
  bars: DemoBar[];
  closes: number[];
  indicators: IndicatorRow[];
  lastPrice: number;
  previousClose: number;
  change: number;
  changePct: number;
  volume: number;
  avgVolume30d: number;
  weekHigh: number;
  weekLow: number;
  sparkline: number[];
  turnover: number;
}

export interface DemoIndex {
  symbol: string;
  name: string;
  market: MarketCode;
  level: number;
  previousClose: number;
  change: number;
  changePct: number;
  sparkline: number[];
  series: number[];
  constituentCount: number;
}

export interface DemoPosition {
  symbol: string;
  quantity: number;
  averageCost: number;
  realizedPnl: number;
  openedAt: string;
}

export interface DemoPortfolio {
  id: string;
  name: string;
  market: MarketCode;
  baseCurrency: string;
  benchmarkSymbol: string;
  cashBalance: number;
  isDefault: boolean;
  createdAt: string;
  positions: DemoPosition[];
}

export interface DemoTransaction {
  id: string;
  symbol: string;
  name: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  value: number;
  transaction_cost: number;
  slippage: number;
  status: "filled";
  is_simulated: boolean;
  notes: string | null;
  executed_at: string;
}

export interface DemoMarketWorld {
  catalog: CatalogMarket;
  instruments: DemoInstrument[];
  bySymbol: Record<string, DemoInstrument>;
  indices: DemoIndex[];
  portfolios: DemoPortfolio[];
  transactions: DemoTransaction[];
  watchlistItems: { symbol: string; alertAbove: number | null; alertBelow: number | null }[];
}

export interface DemoWorld {
  markets: Record<MarketCode, DemoMarketWorld>;
  /** Mutable stores - the demo API writes to these so the UI's mutations stick. */
  settings: Record<string, string | number | boolean>;
  reports: DemoReport[];
  documents: DemoDocument[];
  conversations: DemoConversation[];
  models: DemoModel[];
  predictions: DemoPrediction[];
  counters: { orders: number; reports: number; documents: number; queries: number };
  startedAt: number;
}

export interface DemoReport {
  id: string;
  report_type: string;
  report_format: string;
  title: string;
  portfolio_id: string | null;
  size_bytes: number;
  filename: string;
  download_url: string;
  created_at: string;
}

export interface DemoDocument {
  id: string;
  filename: string;
  document_type: string;
  page_count: number;
  chunk_count: number;
  size_bytes: number;
  stock_id: string | null;
  created_at: string;
}

export interface DemoMessage {
  id: string;
  conversation_id: string | null;
  question: string;
  answer: string;
  llm_provider: string;
  citations: {
    document_name: string;
    page_number: number;
    chunk_text: string;
    relevance_score: number;
  }[];
  latency_ms: number;
  generated_at: string;
}

export interface DemoConversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: DemoMessage[];
}

export interface DemoModel {
  id: string;
  name: string;
  version: number;
  task: string;
  algorithm: string;
  stage: string;
  symbol: string;
  metrics: Record<string, number>;
  hyperparameters: Record<string, number | string | boolean>;
  feature_count: number;
  trained_at: string;
}

export interface DemoPrediction {
  id: string;
  symbol: string;
  model_name: string;
  model_version: number;
  predicted_value: number;
  confidence: number;
  actual_direction: number | null;
  correct: boolean | null;
  generated_at: string;
}

const DAY = 86_400_000;

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * DAY).toISOString();
}

function isoMinutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function buildInstrument(catalog: CatalogMarket, index: number): DemoInstrument {
  const definition = catalog.stocks[index];
  const bars = generateBars({
    symbol: `${catalog.code}:${definition.symbol}`,
    basePrice: definition.basePrice,
    sessions: HISTORY_SESSIONS,
    factorKey: catalog.code + FACTOR_SEED_SUFFIX,
  });
  const closes = bars.map((bar) => bar.close);
  const indicators = computeIndicators(bars);
  const last = bars[bars.length - 1];
  const previous = bars[bars.length - 2];
  const yearBars = bars.slice(-252);
  const volumes = bars.slice(-30).map((bar) => bar.volume);

  const change = round(last.close - previous.close, 2);
  return {
    id: `stk-${catalog.code.toLowerCase()}-${definition.symbol.toLowerCase()}`,
    symbol: definition.symbol,
    name: definition.name,
    sector: definition.sector,
    market: catalog.code,
    exchange: catalog.exchange,
    currency: catalog.currency,
    marketCap: definition.marketCap,
    bars,
    closes,
    indicators,
    lastPrice: last.close,
    previousClose: previous.close,
    change,
    changePct: round(change / previous.close, 6),
    volume: last.volume,
    avgVolume30d: Math.round(volumes.reduce((total, value) => total + value, 0) / volumes.length),
    weekHigh: round(Math.max(...yearBars.map((bar) => bar.high)), 2),
    weekLow: round(Math.min(...yearBars.map((bar) => bar.low)), 2),
    sparkline: bars.slice(-32).map((bar) => round(bar.close, 2)),
    turnover: Math.round(last.close * last.volume),
  };
}

function buildIndex(
  catalog: CatalogMarket,
  definition: CatalogMarket["indices"][number],
  bySymbol: Record<string, DemoInstrument>,
): DemoIndex {
  const members = definition.constituents
    .map((symbol) => bySymbol[symbol])
    .filter((member): member is DemoInstrument => Boolean(member));

  const totalCap = members.reduce((total, member) => total + member.marketCap, 0) || 1;
  const length = members[0]?.closes.length ?? 0;
  const composite: number[] = [];
  for (let day = 0; day < length; day += 1) {
    let value = 0;
    for (const member of members) {
      // Cap-weighted index of NORMALIZED prices: weighting raw prices would let
      // MARUTI at Rs 12,450 dominate an index it is a small part of.
      value += (member.closes[day] / member.closes[0]) * (member.marketCap / totalCap);
    }
    composite.push(value);
  }

  const scale = definition.level / (composite[composite.length - 1] || 1);
  const series = composite.map((value) => round(value * scale, 2));
  const level = series[series.length - 1];
  const previousClose = series[series.length - 2] ?? level;
  const change = round(level - previousClose, 2);

  return {
    symbol: definition.symbol,
    name: definition.name,
    market: catalog.code,
    level,
    previousClose,
    change,
    changePct: round(change / previousClose, 6),
    sparkline: series.slice(-32),
    series,
    constituentCount: members.length,
  };
}

function buildPortfolio(
  catalog: CatalogMarket,
  bySymbol: Record<string, DemoInstrument>,
  rand: Rng,
): { portfolio: DemoPortfolio; transactions: DemoTransaction[] } {
  const positions: DemoPosition[] = [];
  const transactions: DemoTransaction[] = [];

  catalog.positions.forEach((position, index) => {
    const instrument = bySymbol[position.symbol];
    if (!instrument) return;
    // Entry taken from a real bar in the history rather than invented, so cost
    // basis is consistent with the chart the user is looking at.
    const entryOffset = 120 + Math.floor(rand() * 260);
    const entryIndex = Math.max(0, instrument.closes.length - entryOffset);
    const entryPrice = round(instrument.closes[entryIndex] * uniform(rand, 0.985, 1.015), 2);
    const openedAt = instrument.bars[entryIndex].timestamp;

    positions.push({
      symbol: position.symbol,
      quantity: position.quantity,
      averageCost: entryPrice,
      realizedPnl: index % 3 === 0 ? round(uniform(rand, -1, 3) * entryPrice * 0.4, 2) : 0,
      openedAt,
    });

    const value = round(entryPrice * position.quantity, 2);
    transactions.push({
      id: `txn-${catalog.code.toLowerCase()}-${position.symbol.toLowerCase()}-open`,
      symbol: position.symbol,
      name: instrument.name,
      side: "buy",
      quantity: position.quantity,
      price: entryPrice,
      value,
      transaction_cost: round(value * 0.0004, 2),
      slippage: round(value * 0.0001, 2),
      status: "filled",
      is_simulated: true,
      notes: "Opening position",
      executed_at: openedAt,
    });

    // A couple of top-ups and one trim per book, so the ledger is not a single
    // uniform block of opening buys.
    if (index % 2 === 0) {
      const topUpIndex = Math.min(instrument.closes.length - 3, entryIndex + 60);
      const topUpPrice = round(instrument.closes[topUpIndex], 2);
      const quantity = Math.max(1, Math.round(position.quantity * 0.25));
      transactions.push({
        id: `txn-${catalog.code.toLowerCase()}-${position.symbol.toLowerCase()}-add`,
        symbol: position.symbol,
        name: instrument.name,
        side: "buy",
        quantity,
        price: topUpPrice,
        value: round(topUpPrice * quantity, 2),
        transaction_cost: round(topUpPrice * quantity * 0.0004, 2),
        slippage: round(topUpPrice * quantity * 0.0001, 2),
        status: "filled",
        is_simulated: true,
        notes: "Averaging into weakness",
        executed_at: instrument.bars[topUpIndex].timestamp,
      });
    }
    if (index === 1 || index === 4) {
      const trimIndex = Math.min(instrument.closes.length - 2, entryIndex + 140);
      const trimPrice = round(instrument.closes[trimIndex], 2);
      const quantity = Math.max(1, Math.round(position.quantity * 0.2));
      transactions.push({
        id: `txn-${catalog.code.toLowerCase()}-${position.symbol.toLowerCase()}-trim`,
        symbol: position.symbol,
        name: instrument.name,
        side: "sell",
        quantity,
        price: trimPrice,
        value: round(trimPrice * quantity, 2),
        transaction_cost: round(trimPrice * quantity * 0.0004, 2),
        slippage: round(trimPrice * quantity * 0.00012, 2),
        status: "filled",
        is_simulated: true,
        notes: "Booking partial profit",
        executed_at: instrument.bars[trimIndex].timestamp,
      });
    }
  });

  transactions.sort((a, b) => (a.executed_at < b.executed_at ? 1 : -1));

  return {
    portfolio: {
      id: `pf-${catalog.code.toLowerCase()}-core`,
      name: catalog.code === "IN" ? "Core India Equity" : "Core US Equity",
      market: catalog.code,
      baseCurrency: catalog.currency,
      benchmarkSymbol: catalog.benchmarkSymbol,
      cashBalance: catalog.cash,
      isDefault: true,
      createdAt: isoDaysAgo(420),
      positions,
    },
    transactions,
  };
}

function buildMarketWorld(code: MarketCode): DemoMarketWorld {
  const catalog = MARKET_CATALOG[code];
  const rand = makeRng(`world:${code}`);
  const instruments = catalog.stocks.map((_, index) => buildInstrument(catalog, index));
  const bySymbol: Record<string, DemoInstrument> = {};
  for (const instrument of instruments) bySymbol[instrument.symbol] = instrument;

  const indices = catalog.indices.map((definition) => buildIndex(catalog, definition, bySymbol));
  const { portfolio, transactions } = buildPortfolio(catalog, bySymbol, rand);

  const satellite: DemoPortfolio = {
    id: `pf-${code.toLowerCase()}-satellite`,
    name: code === "IN" ? "Midcap Tactical" : "Growth Tactical",
    market: code,
    baseCurrency: catalog.currency,
    benchmarkSymbol: catalog.benchmarkSymbol,
    cashBalance: round(catalog.cash * 0.4, 2),
    isDefault: false,
    createdAt: isoDaysAgo(180),
    positions: portfolio.positions.slice(0, 3).map((position) => ({
      ...position,
      quantity: Math.max(1, Math.round(position.quantity * 0.4)),
    })),
  };

  return {
    catalog,
    instruments,
    bySymbol,
    indices,
    portfolios: [portfolio, satellite],
    transactions,
    watchlistItems: catalog.watchlist.map((symbol, index) => ({
      symbol,
      alertAbove: index === 0 ? round(bySymbol[symbol].lastPrice * 1.05, 2) : null,
      alertBelow: index === 1 ? round(bySymbol[symbol].lastPrice * 0.93, 2) : null,
    })),
  };
}

function buildModels(): DemoModel[] {
  const rand = makeRng("models");
  const specs: { symbol: string; task: string; algorithm: string; stage: string }[] = [
    { symbol: "RELIANCE", task: "trend_classification", algorithm: "xgboost", stage: "production" },
    { symbol: "TCS", task: "trend_classification", algorithm: "lightgbm", stage: "production" },
    { symbol: "HDFCBANK", task: "next_day_return", algorithm: "random_forest", stage: "staging" },
    { symbol: "AAPL", task: "trend_classification", algorithm: "xgboost", stage: "production" },
    { symbol: "NVDA", task: "volatility_prediction", algorithm: "lightgbm", stage: "staging" },
    { symbol: "MSFT", task: "trend_classification", algorithm: "xgboost", stage: "archived" },
  ];

  return specs.map((spec, index) => {
    const isRegression = spec.task !== "trend_classification";
    const accuracy = round(uniform(rand, 0.53, 0.64), 4);
    const metrics: Record<string, number> = isRegression
      ? {
          rmse: round(uniform(rand, 0.008, 0.021), 5),
          mae: round(uniform(rand, 0.006, 0.016), 5),
          r2: round(uniform(rand, 0.04, 0.19), 4),
          n_train_samples: 560,
          n_test_samples: 140,
          n_walk_forward_splits: 5,
        }
      : {
          accuracy,
          precision: round(accuracy + uniform(rand, -0.03, 0.04), 4),
          recall: round(accuracy + uniform(rand, -0.05, 0.03), 4),
          f1: round(accuracy + uniform(rand, -0.02, 0.02), 4),
          roc_auc: round(accuracy + uniform(rand, 0.01, 0.07), 4),
          n_train_samples: 560,
          n_test_samples: 140,
          n_walk_forward_splits: 5,
        };
    return {
      id: `mdl-${spec.symbol.toLowerCase()}-v${index + 1}`,
      name: `${spec.symbol}_${spec.task}`,
      version: 1 + (index % 3),
      task: spec.task,
      algorithm: spec.algorithm,
      stage: spec.stage,
      symbol: spec.symbol,
      metrics,
      hyperparameters: {
        n_estimators: 200 + index * 40,
        max_depth: 3 + (index % 4),
        learning_rate: round(uniform(rand, 0.02, 0.12), 3),
        subsample: round(uniform(rand, 0.7, 0.95), 2),
        objective: isRegression ? "reg:squarederror" : "binary:logistic",
      },
      feature_count: 24,
      trained_at: isoDaysAgo(2 + index * 3),
    };
  });
}

function buildPredictions(models: DemoModel[]): DemoPrediction[] {
  const rand = makeRng("predictions");
  const predictions: DemoPrediction[] = [];
  models.forEach((model, modelIndex) => {
    for (let index = 0; index < 8; index += 1) {
      const value = round(uniform(rand, 0.34, 0.72), 4);
      const settled = index > 1;
      const actual = settled ? (rand() > 0.45 ? 1 : -1) : null;
      predictions.push({
        id: `prd-${model.symbol.toLowerCase()}-${modelIndex}-${index}`,
        symbol: model.symbol,
        model_name: model.name,
        model_version: model.version,
        predicted_value: value,
        confidence: round(Math.abs(value - 0.5) * 2, 4),
        actual_direction: actual,
        correct: actual === null ? null : (value > 0.5 ? 1 : -1) === actual,
        generated_at: isoDaysAgo(index + 1),
      });
    }
  });
  return predictions;
}

function buildConversations(): DemoConversation[] {
  return [
    {
      id: "cnv-demo-1",
      title: "FY24 annual report walkthrough",
      created_at: isoDaysAgo(6),
      updated_at: isoDaysAgo(6),
      messages: [
        {
          id: "msg-demo-1",
          conversation_id: "cnv-demo-1",
          question: "Summarize the revenue performance described in the uploaded reports.",
          answer:
            "Consolidated revenue grew 11.4% year on year, led by the digital services segment (+18.2%) while the legacy hardware line contracted 3.1%. Management attributes the acceleration to a larger deal pipeline closing earlier than planned. Gross margin expanded 70 basis points despite higher input costs, because the revenue mix shifted toward higher-margin recurring contracts.",
          llm_provider: "extractive_fallback",
          citations: [
            {
              document_name: "FY24-annual-report.pdf",
              page_number: 34,
              chunk_text:
                "Consolidated revenue for the year stood at 11.4% above the prior year, with digital services contributing the majority of incremental growth.",
              relevance_score: 0.91,
            },
            {
              document_name: "FY24-annual-report.pdf",
              page_number: 37,
              chunk_text:
                "Gross margin improved by 70 bps on a favourable mix shift toward recurring contracts.",
              relevance_score: 0.84,
            },
          ],
          latency_ms: 620,
          generated_at: isoDaysAgo(6),
        },
      ],
    },
    {
      id: "cnv-demo-2",
      title: "Risk factor comparison",
      created_at: isoDaysAgo(2),
      updated_at: isoDaysAgo(2),
      messages: [],
    },
  ];
}

function buildDocuments(): DemoDocument[] {
  return [
    {
      id: "doc-demo-1",
      filename: "FY24-annual-report.pdf",
      document_type: "annual_report",
      page_count: 214,
      chunk_count: 1_842,
      size_bytes: 8_412_336,
      stock_id: null,
      created_at: isoDaysAgo(9),
    },
  ];
}

let cached: DemoWorld | null = null;

export function getWorld(): DemoWorld {
  if (cached) return cached;

  const markets = {} as Record<MarketCode, DemoMarketWorld>;
  for (const code of MARKET_CODES) markets[code] = buildMarketWorld(code);

  const models = buildModels();
  cached = {
    markets,
    settings: {
      theme: "dark",
      language: "en",
      default_market: "IN",
      default_dashboard: "dashboard",
      number_format: "auto",
      email_notifications: true,
      push_notifications: true,
      market_alerts: true,
      signal_alerts: true,
      price_alerts: true,
      weekly_digest: false,
      chart_type: "area",
      auto_refresh_seconds: 30,
      reduced_motion: false,
    },
    reports: [
      {
        id: "rpt-demo-1",
        report_type: "portfolio",
        report_format: "pdf",
        title: "Portfolio Report - Core India Equity",
        portfolio_id: "pf-in-core",
        size_bytes: 184_320,
        filename: "portfolio-report-core-india-equity.pdf",
        download_url: "/api/v1/reports/rpt-demo-1/download",
        created_at: isoDaysAgo(4),
      },
      {
        id: "rpt-demo-2",
        report_type: "risk",
        report_format: "excel",
        title: "Risk Report - Core India Equity",
        portfolio_id: "pf-in-core",
        size_bytes: 61_440,
        filename: "risk-report-core-india-equity.xlsx",
        download_url: "/api/v1/reports/rpt-demo-2/download",
        created_at: isoDaysAgo(11),
      },
    ],
    documents: buildDocuments(),
    conversations: buildConversations(),
    models,
    predictions: buildPredictions(models),
    counters: { orders: 0, reports: 2, documents: 1, queries: 14 },
    startedAt: Date.now(),
  };
  return cached;
}

export function marketWorld(code: MarketCode): DemoMarketWorld {
  return getWorld().markets[code] ?? getWorld().markets.IN;
}

export function findInstrument(symbol: string): DemoInstrument | null {
  const world = getWorld();
  const upper = symbol.toUpperCase();
  for (const code of MARKET_CODES) {
    const found = world.markets[code].bySymbol[upper];
    if (found) return found;
  }
  return null;
}

export function findIndex(symbol: string): DemoIndex | null {
  const world = getWorld();
  const upper = symbol.toUpperCase();
  for (const code of MARKET_CODES) {
    const found = world.markets[code].indices.find((entry) => entry.symbol === upper);
    if (found) return found;
  }
  return null;
}

export { isoDaysAgo, isoMinutesAgo };
