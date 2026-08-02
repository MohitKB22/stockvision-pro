/**
 * The demo API surface: one handler per endpoint the frontend calls.
 *
 * Paths, query parameters and response shapes mirror `docs/API.md` and the
 * Pydantic schemas exactly. Mutating endpoints write to the in-memory world, so
 * adding a watchlist symbol, submitting an order, training a model or asking the
 * copilot all behave the way they do against the real backend - the changes just
 * do not survive a page reload.
 */

import type { MarketCode } from "@/types";

import {
  buildForecast,
  buildSignal,
  correlationMatrix,
  indexQuote,
  instrumentPublic,
  instrumentQuote,
  marketBreadth,
  monteCarlo,
  moverQuote,
  performanceSeries,
  portfolioSummary,
  riskMetrics,
  scoreSentiment,
  sectorPerformance,
  stressTest,
  weekRangeEntry,
} from "./analytics";
import { INTEGRATIONS, MARKET_CATALOG, MARKET_CODES, SUGGESTED_PROMPTS } from "./catalog";
import { clamp, makeRng, mean, round, uniform } from "./rng";
import {
  findInstrument,
  getWorld,
  isoMinutesAgo,
  marketWorld,
  type DemoInstrument,
  type DemoMarketWorld,
  type DemoPortfolio,
} from "./world";

export interface RequestContext {
  params: Record<string, string>;
  query: Record<string, string>;
  body: unknown;
  raw: unknown;
}

export type Handler = (context: RequestContext) => unknown;

export class DemoApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 400) {
    super(message);
    this.name = "DemoApiError";
    this.code = code;
    this.status = status;
  }
}

function notFound(message: string): never {
  throw new DemoApiError("not_found", message, 404);
}

// --- Parameter helpers ---------------------------------------------------------

function marketOf(context: RequestContext): MarketCode {
  const value = (context.query.market ?? "IN").toUpperCase();
  return value === "US" ? "US" : "IN";
}

function numberOf(context: RequestContext, key: string, fallback: number): number {
  const raw = context.query[key];
  if (raw === undefined || raw === "") return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function bodyOf(context: RequestContext): Record<string, unknown> {
  if (context.body && typeof context.body === "object") {
    return context.body as Record<string, unknown>;
  }
  return {};
}

function stringField(body: Record<string, unknown>, key: string, fallback = ""): string {
  const value = body[key];
  return typeof value === "string" ? value : fallback;
}

function numberField(body: Record<string, unknown>, key: string, fallback: number): number {
  const value = body[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function resolvePortfolio(portfolioId: string): { mw: DemoMarketWorld; portfolio: DemoPortfolio } {
  const world = getWorld();
  for (const code of MARKET_CODES) {
    const mw = world.markets[code];
    const portfolio = mw.portfolios.find((entry) => entry.id === portfolioId);
    if (portfolio) return { mw, portfolio };
  }
  return notFound(`Portfolio ${portfolioId} does not exist.`);
}

function requireInstrument(symbol: string): DemoInstrument {
  const instrument = findInstrument(symbol);
  if (!instrument) return notFound(`No instrument found for symbol ${symbol.toUpperCase()}.`);
  return instrument;
}

// --- Market -------------------------------------------------------------------

function marketDefinitions() {
  return MARKET_CODES.map((code) => {
    const catalog = MARKET_CATALOG[code];
    return {
      code: catalog.code,
      name: catalog.name,
      currency: catalog.currency,
      currency_symbol: catalog.currencySymbol,
      digit_grouping: catalog.digitGrouping,
      exchange: catalog.exchange,
      benchmark_symbol: catalog.benchmarkSymbol,
      timezone: catalog.timezone,
      session_open: catalog.sessionOpen,
      session_close: catalog.sessionClose,
      indices: catalog.indices.map((index) => ({
        symbol: index.symbol,
        name: index.name,
        constituent_count: index.constituents.length,
      })),
    };
  });
}

function sessionStatus(code: MarketCode) {
  const catalog = MARKET_CATALOG[code];
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: catalog.timezone,
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hour12: false,
  });
  const parts = formatter.formatToParts(new Date());
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? "0");
  const weekday = parts.find((part) => part.type === "weekday")?.value ?? "Mon";

  const minutes = hour * 60 + minute;
  const toMinutes = (value: string): number => {
    const [h, m] = value.split(":").map(Number);
    return h * 60 + m;
  };
  const isWeekday = !["Sat", "Sun"].includes(weekday);
  const isOpen =
    isWeekday && minutes >= toMinutes(catalog.sessionOpen) && minutes < toMinutes(catalog.sessionClose);

  return {
    market: code,
    timezone: catalog.timezone,
    local_time: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
    session_open: catalog.sessionOpen,
    session_close: catalog.sessionClose,
    is_open: isOpen,
    is_weekday: isWeekday,
    holiday_calendar_applied: false,
  };
}

function movers(mw: DemoMarketWorld, limit: number) {
  const sorted = [...mw.instruments].sort((a, b) => b.changePct - a.changePct);
  const byTurnover = [...mw.instruments].sort((a, b) => b.turnover - a.turnover);
  return {
    gainers: sorted.slice(0, limit).map(moverQuote),
    losers: sorted.slice(-limit).reverse().map(moverQuote),
    most_active: byTurnover.slice(0, limit).map(moverQuote),
  };
}

function newsItems(code: MarketCode, symbol: string | undefined, limit: number) {
  const catalog = MARKET_CATALOG[code];
  const rand = makeRng(`news:${code}`);
  const items = catalog.news
    .map((article, index) => {
      const sentiment = scoreSentiment(`${article.headline} ${article.summary}`);
      return {
        id: `news-${code.toLowerCase()}-${index}`,
        headline: article.headline,
        summary: article.summary,
        source: article.source,
        url: "https://example.com/demo-article",
        market: code,
        symbol: article.symbol,
        published_at: isoMinutesAgo(45 * index + Math.floor(rand() * 40) + 12),
        sentiment_score: sentiment.score,
        sentiment_label: sentiment.label,
        impact_score: round(clamp(Math.abs(sentiment.score) * 0.8 + rand() * 0.3, 0.05, 0.99), 3),
        entities: [article.category, ...(article.symbol ? [article.symbol] : [])],
      };
    })
    .filter((article) => (symbol ? article.symbol === symbol.toUpperCase() : true));

  return items.slice(0, limit);
}

function sentimentSummary(items: ReturnType<typeof newsItems>) {
  return {
    engine: "lexicon_v2_demo",
    article_count: items.length,
    average_sentiment: round(mean(items.map((item) => item.sentiment_score)), 4),
    positive: items.filter((item) => item.sentiment_label === "positive").length,
    neutral: items.filter((item) => item.sentiment_label === "neutral").length,
    negative: items.filter((item) => item.sentiment_label === "negative").length,
  };
}

function watchlistPayload(code: MarketCode) {
  const mw = marketWorld(code);
  return {
    id: `wl-${code.toLowerCase()}-default`,
    name: "My Watchlist",
    market: code,
    is_default: true,
    item_count: mw.watchlistItems.length,
    items: mw.watchlistItems.map((item, index) => {
      const instrument = mw.bySymbol[item.symbol];
      const quote = instrument ? instrumentQuote(instrument) : null;
      const triggered =
        instrument !== undefined &&
        ((item.alertAbove !== null && instrument.lastPrice >= item.alertAbove) ||
          (item.alertBelow !== null && instrument.lastPrice <= item.alertBelow));
      return {
        id: `wli-${code.toLowerCase()}-${item.symbol.toLowerCase()}`,
        symbol: item.symbol,
        name: instrument?.name ?? item.symbol,
        sector: instrument?.sector ?? null,
        position: index,
        alert_above: item.alertAbove,
        alert_below: item.alertBelow,
        quote,
        alert_triggered: Boolean(triggered),
      };
    }),
  };
}

// --- Admin ---------------------------------------------------------------------

function systemHealth() {
  const world = getWorld();
  return {
    status: "healthy",
    environment: "demo",
    version: "2.0.0-demo",
    uptime_seconds: Math.floor((Date.now() - world.startedAt) / 1000) + 4_182,
    database_connected: true,
    database_latency_ms: round(uniform(makeRng("health"), 0.4, 1.8), 2),
    database_dialect: "in-memory (demo)",
    redis_configured: false,
    llm_provider: "extractive_fallback",
    python_version: "n/a (browser demo)",
    platform: "Vercel Edge / demo mode",
    cpu_count: 4,
    disk_usage_pct: 0.34,
    document_storage_bytes: world.documents.reduce((total, doc) => total + doc.size_bytes, 0),
    model_storage_bytes: world.models.length * 1_842_000,
    report_storage_bytes: world.reports.reduce((total, report) => total + report.size_bytes, 0),
  };
}

const AUDIT_ACTIONS = [
  "market.overview",
  "portfolio.summary",
  "risk.metrics",
  "signal.generate",
  "prediction.create",
  "copilot.query",
  "report.generate",
  "watchlist.update",
];

function auditLog(limit: number, action?: string) {
  const rand = makeRng("audit");
  const entries = [];
  for (let index = 0; index < 120; index += 1) {
    const chosen = AUDIT_ACTIONS[index % AUDIT_ACTIONS.length];
    const failed = index % 37 === 0;
    entries.push({
      id: `aud-${index}`,
      action: chosen,
      resource: chosen.split(".")[0],
      detail: { source: "demo", sequence: index },
      ip_address: "127.0.0.1",
      request_id: `req-${(1000 + index).toString(16)}`,
      status_code: failed ? 422 : 200,
      duration_ms: round(uniform(rand, 4, 180), 1),
      timestamp: isoMinutesAgo(index * 7 + 2),
    });
  }
  return entries.filter((entry) => (action ? entry.action === action : true)).slice(0, limit);
}

function adminOverview(windowHours: number) {
  const world = getWorld();
  const rand = makeRng(`admin:${windowHours}`);
  const apiCalls = Math.round(420 + windowHours * 37 + rand() * 90);
  const errors = Math.round(apiCalls * 0.004);
  const latency = round(uniform(rand, 22, 68), 1);
  const documents = world.documents.length;
  const chunks = world.documents.reduce((total, doc) => total + doc.chunk_count, 0);
  const predictions = world.predictions.length;
  const signals = 46;
  const copilotQueries = world.counters.queries;

  const format = (value: number): string => value.toLocaleString("en-US");

  const hours = Math.min(windowHours, 24);
  const series = [];
  for (let index = hours - 1; index >= 0; index -= 1) {
    series.push({
      timestamp: new Date(Date.now() - index * 3_600_000).toISOString(),
      value: Math.round(12 + Math.abs(Math.sin(index / 2.4)) * 46 + rand() * 8),
    });
  }

  const callsByAction: Record<string, number> = {};
  AUDIT_ACTIONS.forEach((action, index) => {
    callsByAction[action] = Math.round(apiCalls / (index + 2.2));
  });

  return {
    window_hours: windowHours,
    cards: [
      { key: "api_calls", label: "API Calls", value: apiCalls, display: format(apiCalls), change_pct: round(uniform(rand, -0.12, 0.28), 4), hint: `Last ${windowHours}h` },
      { key: "predictions", label: "Predictions Generated", value: predictions, display: format(predictions), change_pct: null, hint: "All time" },
      { key: "signals", label: "Signals Generated", value: signals, display: format(signals), change_pct: null, hint: "All time" },
      { key: "documents", label: "Documents Indexed", value: documents, display: format(documents), change_pct: null, hint: `${format(chunks)} chunks` },
      { key: "models", label: "Model Versions", value: world.models.length, display: format(world.models.length), change_pct: null, hint: "Registry" },
      { key: "copilot", label: "Copilot Queries", value: copilotQueries, display: format(copilotQueries), change_pct: null, hint: "All time" },
      { key: "error_rate", label: "Error Rate", value: round(errors / apiCalls, 5), display: `${((errors / apiCalls) * 100).toFixed(2)}%`, change_pct: null, hint: `${errors} of ${format(apiCalls)} requests` },
      { key: "latency", label: "Avg Latency", value: latency, display: `${latency.toFixed(0)} ms`, change_pct: null, hint: `Last ${windowHours}h` },
    ],
    api_calls_series: series,
    calls_by_action: callsByAction,
    data_counts: {
      stocks: MARKET_CODES.reduce((total, code) => total + marketWorld(code).instruments.length, 0),
      price_bars: MARKET_CODES.reduce(
        (total, code) =>
          total +
          marketWorld(code).instruments.reduce((sum, instrument) => sum + instrument.bars.length, 0),
        0,
      ),
      portfolios: MARKET_CODES.reduce((total, code) => total + marketWorld(code).portfolios.length, 0),
      orders: MARKET_CODES.reduce((total, code) => total + marketWorld(code).transactions.length, 0),
      documents,
      document_chunks: chunks,
      models: world.models.length,
      predictions,
      signals,
      copilot_queries: copilotQueries,
      reports: world.reports.length,
      audit_events: 120,
    },
    health: systemHealth(),
  };
}

// --- Copilot -------------------------------------------------------------------

function answerFor(question: string) {
  const world = getWorld();
  const corpus = world.documents[0]?.filename ?? "uploaded-document.pdf";
  const lowered = question.toLowerCase();

  let answer =
    "Based on the indexed corpus, the documents describe a business with growing recurring revenue, " +
    "improving gross margin and a stable balance sheet. Management frames the year as one of " +
    "consolidation rather than expansion, with capital allocation weighted toward reinvestment over " +
    "buybacks.";

  if (lowered.includes("risk")) {
    answer =
      "The principal disclosed risks are concentration risk in the top five customers, foreign-exchange " +
      "exposure on roughly 60% of revenue, and regulatory risk in two operating regions. The filing " +
      "notes that no single risk is expected to be material in isolation, but that several correlate " +
      "under a demand shock.";
  } else if (lowered.includes("margin")) {
    answer =
      "Operating margin expanded 70 basis points year on year. The explanation given is mix: recurring " +
      "contracts carry a higher gross margin than one-off implementation work, and their share of " +
      "revenue rose from 41% to 48%. Wage inflation partly offset the gain.";
  } else if (lowered.includes("segment")) {
    answer =
      "Three reported segments. Digital Services grew 18.2% and now contributes 48% of revenue; " +
      "Infrastructure grew 4.1%; the legacy Hardware line contracted 3.1% and is being wound down " +
      "over the next two fiscal years.";
  } else if (lowered.includes("outlook") || lowered.includes("guidance")) {
    answer =
      "Management guides to high-single-digit constant-currency revenue growth and flat-to-slightly-up " +
      "operating margin. The guidance explicitly excludes any contribution from the acquisition " +
      "announced after the balance-sheet date.";
  } else if (lowered.includes("capital") || lowered.includes("dividend") || lowered.includes("buyback")) {
    answer =
      "Capital allocation priority order is stated as: organic reinvestment, then bolt-on acquisitions, " +
      "then dividends, with buybacks used opportunistically. Capex was 5.4% of revenue and the dividend " +
      "payout ratio was 32%.";
  }

  return {
    answer:
      `${answer}\n\nDemo mode note: this response comes from the extractive fallback engine over a ` +
      `sample corpus, not a live LLM. Supply an OpenAI or Gemini key to the backend and the same ` +
      `endpoint returns a generated answer with the identical citation contract.`,
    citations: [
      {
        document_name: corpus,
        page_number: 34,
        chunk_text:
          "Revenue for the period grew ahead of guidance, with the recurring component expanding " +
          "faster than the total, lifting the overall mix.",
        relevance_score: 0.89,
      },
      {
        document_name: corpus,
        page_number: 57,
        chunk_text:
          "Management reiterated that capital allocation priorities remain unchanged from the prior " +
          "year, with organic reinvestment ranked first.",
        relevance_score: 0.81,
      },
    ],
  };
}

// --- Route table ---------------------------------------------------------------

interface Route {
  method: string;
  pattern: string[];
  handler: Handler;
}

const routes: Route[] = [];

function route(method: string, path: string, handler: Handler): void {
  routes.push({ method, pattern: path.split("/").filter(Boolean), handler });
}

// Markets and session
route("get", "/markets", () => marketDefinitions());
route("get", "/market/session", (context) => sessionStatus(marketOf(context)));
route("get", "/market/overview", (context) => {
  const code = marketOf(context);
  const mw = marketWorld(code);
  const limit = numberOf(context, "mover_limit", 5);
  return {
    market: code,
    currency: mw.catalog.currency,
    currency_symbol: mw.catalog.currencySymbol,
    indices: mw.indices.map(indexQuote),
    ...movers(mw, limit),
    sectors: sectorPerformance(mw),
    breadth: marketBreadth(mw),
  };
});
route("get", "/market/indices", (context) => marketWorld(marketOf(context)).indices.map(indexQuote));
route("get", "/market/indices/:symbol/constituents", (context) => {
  const mw = marketWorld(marketOf(context));
  const definition = mw.catalog.indices.find(
    (index) => index.symbol === context.params.symbol.toUpperCase(),
  );
  if (!definition) return notFound(`Unknown index ${context.params.symbol}.`);
  return definition.constituents
    .map((symbol) => mw.bySymbol[symbol])
    .filter((instrument): instrument is DemoInstrument => Boolean(instrument))
    .map(instrumentQuote);
});
route("get", "/market/movers", (context) =>
  movers(marketWorld(marketOf(context)), numberOf(context, "limit", 10)),
);
route("get", "/market/sectors", (context) => sectorPerformance(marketWorld(marketOf(context))));
route("get", "/market/heatmap", (context) =>
  marketWorld(marketOf(context)).instruments.map((instrument) => ({
    symbol: instrument.symbol,
    name: instrument.name,
    sector: instrument.sector,
    change_pct: instrument.changePct,
    market_cap: instrument.marketCap,
    last_price: instrument.lastPrice,
    turnover: instrument.turnover,
  })),
);
route("get", "/market/breadth", (context) => marketBreadth(marketWorld(marketOf(context))));
route("get", "/market/52-week", (context) => {
  const mw = marketWorld(marketOf(context));
  const limit = numberOf(context, "limit", 10);
  const entries = mw.instruments.map(weekRangeEntry);
  return {
    near_52_week_high: [...entries]
      .sort((a, b) => b.position_in_range - a.position_in_range)
      .slice(0, limit),
    near_52_week_low: [...entries]
      .sort((a, b) => a.position_in_range - b.position_in_range)
      .slice(0, limit),
  };
});
route("get", "/market/quotes", (context) => {
  const symbols = (context.query.symbols ?? "")
    .split(",")
    .map((symbol) => symbol.trim())
    .filter(Boolean);
  return symbols
    .map((symbol) => findInstrument(symbol))
    .filter((instrument): instrument is DemoInstrument => Boolean(instrument))
    .map(instrumentQuote);
});
route("get", "/market/quotes/:symbol", (context) =>
  instrumentQuote(requireInstrument(context.params.symbol)),
);

// Instruments
route("get", "/stocks/search", (context) => {
  const query = (context.query.q ?? "").trim().toLowerCase();
  const limit = numberOf(context, "limit", 8);
  if (!query) return [];
  const mw = marketWorld(marketOf(context));
  return mw.instruments
    .filter(
      (instrument) =>
        instrument.symbol.toLowerCase().includes(query) ||
        instrument.name.toLowerCase().includes(query),
    )
    .slice(0, limit)
    .map(instrumentPublic);
});
route("get", "/stocks/sectors", (context) => {
  const mw = marketWorld(marketOf(context));
  return [...new Set(mw.instruments.map((instrument) => instrument.sector))].sort();
});
route("get", "/stocks", (context) => {
  const mw = marketWorld(marketOf(context));
  const sector = context.query.sector;
  return mw.instruments
    .filter((instrument) => (sector ? instrument.sector === sector : true))
    .map(instrumentPublic);
});
route("get", "/stocks/:symbol/prices", (context) => {
  const instrument = requireInstrument(context.params.symbol);
  const limit = numberOf(context, "limit", 252);
  return instrument.bars.slice(-Math.max(2, limit));
});
route("get", "/stocks/:symbol/features", (context) => {
  const instrument = requireInstrument(context.params.symbol);
  const limit = numberOf(context, "limit", 60);
  const start = Math.max(0, instrument.indicators.length - limit);
  return instrument.indicators.slice(start).map((row, offset) => ({
    timestamp: instrument.bars[start + offset].timestamp,
    close: instrument.bars[start + offset].close,
    indicators: row,
  }));
});
route("get", "/stocks/:symbol", (context) => instrumentPublic(requireInstrument(context.params.symbol)));

// Portfolios
route("get", "/portfolios/default", (context) => {
  const mw = marketWorld(marketOf(context));
  const portfolio = mw.portfolios.find((entry) => entry.isDefault) ?? mw.portfolios[0];
  return serializePortfolio(portfolio);
});
route("get", "/portfolios", (context) =>
  marketWorld(marketOf(context)).portfolios.map(serializePortfolio),
);
route("post", "/portfolios", (context) => {
  const body = bodyOf(context);
  const code = (stringField(body, "market", "IN").toUpperCase() === "US" ? "US" : "IN") as MarketCode;
  const mw = marketWorld(code);
  const created: DemoPortfolio = {
    id: `pf-${code.toLowerCase()}-${Date.now().toString(36)}`,
    name: stringField(body, "name", "New Portfolio"),
    market: code,
    baseCurrency: mw.catalog.currency,
    benchmarkSymbol: mw.catalog.benchmarkSymbol,
    cashBalance: numberField(body, "cash_balance", 0),
    isDefault: false,
    createdAt: new Date().toISOString(),
    positions: [],
  };
  mw.portfolios.push(created);
  return serializePortfolio(created);
});
route("patch", "/portfolios/:id", (context) => {
  const { portfolio } = resolvePortfolio(context.params.id);
  const body = bodyOf(context);
  if (typeof body.name === "string") portfolio.name = body.name;
  if (typeof body.cash_balance === "number") portfolio.cashBalance = body.cash_balance;
  if (typeof body.benchmark_symbol === "string") portfolio.benchmarkSymbol = body.benchmark_symbol;
  return serializePortfolio(portfolio);
});
route("delete", "/portfolios/:id", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  if (portfolio.isDefault) {
    throw new DemoApiError("validation_error", "The default portfolio cannot be deleted.", 422);
  }
  mw.portfolios = mw.portfolios.filter((entry) => entry.id !== portfolio.id);
  return { success: true, message: `Deleted ${portfolio.name}`, id: portfolio.id };
});
route("get", "/portfolios/:id/summary", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  return portfolioSummary(mw, portfolio);
});
route("get", "/portfolios/:id/performance", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  return performanceSeries(mw, portfolio, numberOf(context, "days", 180));
});
route("get", "/portfolios/:id/transactions", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  const limit = numberOf(context, "limit", 500);
  const symbols = new Set(portfolio.positions.map((position) => position.symbol));
  return mw.transactions.filter((entry) => symbols.has(entry.symbol)).slice(0, limit);
});
route("post", "/portfolios/:id/orders", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  const body = bodyOf(context);
  const symbol = stringField(body, "symbol").toUpperCase();
  const side = stringField(body, "side", "buy") === "sell" ? "sell" : "buy";
  const quantity = Math.max(1, Math.round(numberField(body, "quantity", 1)));
  const instrument = mw.bySymbol[symbol];
  if (!instrument) {
    throw new DemoApiError("validation_error", `${symbol} is not in this market.`, 422);
  }
  const price = numberField(body, "price", instrument.lastPrice);
  const existing = portfolio.positions.find((position) => position.symbol === symbol);

  if (side === "buy") {
    const cost = price * quantity;
    if (existing) {
      const totalQuantity = existing.quantity + quantity;
      existing.averageCost =
        (existing.averageCost * existing.quantity + cost) / Math.max(1, totalQuantity);
      existing.quantity = totalQuantity;
    } else {
      portfolio.positions.push({
        symbol,
        quantity,
        averageCost: price,
        realizedPnl: 0,
        openedAt: new Date().toISOString(),
      });
    }
    portfolio.cashBalance = round(portfolio.cashBalance - cost, 2);
  } else {
    if (!existing || existing.quantity < quantity) {
      throw new DemoApiError(
        "validation_error",
        `Insufficient quantity: the book holds ${existing?.quantity ?? 0} ${symbol}.`,
        422,
      );
    }
    existing.realizedPnl = round(existing.realizedPnl + (price - existing.averageCost) * quantity, 2);
    existing.quantity -= quantity;
    portfolio.cashBalance = round(portfolio.cashBalance + price * quantity, 2);
    if (existing.quantity === 0) {
      portfolio.positions = portfolio.positions.filter((position) => position.symbol !== symbol);
    }
  }

  const world = getWorld();
  world.counters.orders += 1;
  const value = round(price * quantity, 2);
  mw.transactions.unshift({
    id: `txn-live-${world.counters.orders}`,
    symbol,
    name: instrument.name,
    side,
    quantity,
    price: round(price, 2),
    value,
    transaction_cost: round(numberField(body, "transaction_cost", value * 0.0004), 2),
    slippage: round(value * 0.0001, 2),
    status: "filled",
    is_simulated: true,
    notes: stringField(body, "notes") || null,
    executed_at: new Date().toISOString(),
  });

  return {
    success: true,
    message: `${side === "buy" ? "Bought" : "Sold"} ${quantity} ${symbol} at ${round(price, 2)}`,
    id: `txn-live-${world.counters.orders}`,
  };
});

// Risk
route("get", "/portfolios/:id/risk/monte-carlo", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  return monteCarlo(
    mw,
    portfolio,
    numberOf(context, "horizon_days", 60),
    numberOf(context, "n_simulations", 1000),
  );
});
route("get", "/portfolios/:id/risk/correlation", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  return correlationMatrix(mw, portfolio, numberOf(context, "lookback_days", 252));
});
route("get", "/portfolios/:id/risk/stress-test", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  return stressTest(mw, portfolio);
});
route("get", "/portfolios/:id/risk", (context) => {
  const { mw, portfolio } = resolvePortfolio(context.params.id);
  return riskMetrics(mw, portfolio, numberOf(context, "lookback_days", 252));
});

// ML
route("get", "/models", () =>
  getWorld().models.map((model) => ({
    id: model.id,
    name: model.name,
    version: model.version,
    task: model.task,
    algorithm: model.algorithm,
    stage: model.stage,
    metrics: model.metrics,
    hyperparameters: model.hyperparameters,
    feature_count: model.feature_count,
    trained_at: model.trained_at,
  })),
);
route("post", "/models/:id/promote", (context) => {
  const world = getWorld();
  const model = world.models.find((entry) => entry.id === context.params.id);
  if (!model) return notFound("Model not found.");
  for (const other of world.models) {
    if (other.name === model.name && other.id !== model.id && other.stage === "production") {
      other.stage = "archived";
    }
  }
  model.stage = "production";
  return {
    id: model.id,
    name: model.name,
    version: model.version,
    task: model.task,
    algorithm: model.algorithm,
    stage: model.stage,
    metrics: model.metrics,
    hyperparameters: model.hyperparameters,
    feature_count: model.feature_count,
    trained_at: model.trained_at,
  };
});
route("post", "/models/train", (context) => {
  const body = bodyOf(context);
  const symbol = stringField(body, "symbol", "RELIANCE").toUpperCase();
  // Validates the symbol exists; training itself needs no bars in demo mode.
  requireInstrument(symbol);
  const task = stringField(body, "task", "trend_classification");
  const algorithm = stringField(body, "algorithm", "xgboost");
  const world = getWorld();
  const rand = makeRng(`train:${symbol}:${task}:${algorithm}:${world.models.length}`);

  const existing = world.models.filter((model) => model.symbol === symbol && model.task === task);
  const version = existing.length + 1;
  const isRegression = task !== "trend_classification";
  const accuracy = round(uniform(rand, 0.54, 0.66), 4);

  const metrics = isRegression
    ? {
        accuracy: null,
        precision: null,
        recall: null,
        f1: null,
        roc_auc: null,
        rmse: round(uniform(rand, 0.008, 0.019), 5),
        mae: round(uniform(rand, 0.005, 0.014), 5),
        r2: round(uniform(rand, 0.05, 0.22), 4),
        n_train_samples: 560,
        n_test_samples: 140,
        n_walk_forward_splits: numberField(body, "n_walk_forward_splits", 5),
      }
    : {
        accuracy,
        precision: round(accuracy + uniform(rand, -0.02, 0.05), 4),
        recall: round(accuracy + uniform(rand, -0.04, 0.03), 4),
        f1: round(accuracy + uniform(rand, -0.02, 0.02), 4),
        roc_auc: round(accuracy + uniform(rand, 0.02, 0.08), 4),
        rmse: null,
        mae: null,
        r2: null,
        n_train_samples: 560,
        n_test_samples: 140,
        n_walk_forward_splits: numberField(body, "n_walk_forward_splits", 5),
      };

  const features = [
    "rsi_14",
    "macd_hist",
    "volatility_20d",
    "adx",
    "return_5d",
    "volume_ratio",
    "bb_position",
    "sma_ratio_20_50",
  ];
  const topFeatures = features
    .map((feature) => ({ feature, mean_abs_shap: round(uniform(rand, 0.02, 0.31), 4) }))
    .sort((a, b) => b.mean_abs_shap - a.mean_abs_shap);

  const hyperparameters: Record<string, number | string | boolean> = {
    n_estimators: 120 + Math.floor(rand() * 260),
    max_depth: 3 + Math.floor(rand() * 5),
    learning_rate: round(uniform(rand, 0.02, 0.14), 3),
    subsample: round(uniform(rand, 0.68, 0.98), 2),
    colsample_bytree: round(uniform(rand, 0.6, 1), 2),
  };

  const created = {
    id: `mdl-${symbol.toLowerCase()}-${task}-v${version}-${Date.now().toString(36)}`,
    name: `${symbol}_${task}`,
    version,
    task,
    algorithm,
    stage: "staging",
    symbol,
    metrics: Object.fromEntries(
      Object.entries(metrics).filter(([, value]) => value !== null),
    ) as Record<string, number>,
    hyperparameters,
    feature_count: features.length + 16,
    trained_at: new Date().toISOString(),
  };
  world.models.unshift(created);

  return {
    model_id: created.id,
    name: created.name,
    version,
    task,
    algorithm,
    stage: "staging",
    best_hyperparameters: hyperparameters,
    metrics,
    top_features: topFeatures,
    trained_at: created.trained_at,
  };
});
route("post", "/predictions", (context) => {
  const body = bodyOf(context);
  const symbol = stringField(body, "symbol").toUpperCase();
  const task = stringField(body, "task", "trend_classification");
  const instrument = requireInstrument(symbol);
  const world = getWorld();
  const model = world.models.find(
    (entry) => entry.symbol === symbol && entry.task === task && entry.stage !== "archived",
  );
  if (!model) {
    throw new DemoApiError(
      "model_not_trained",
      `No ${task.replace(/_/g, " ")} model is registered for ${symbol}. Train one from the "Train a Model" tab - it takes a couple of seconds in demo mode.`,
      404,
    );
  }

  const latest = instrument.indicators[instrument.indicators.length - 1];
  const rsi = (latest.rsi_14 as number | null) ?? 50;
  const macdHist = (latest.macd_hist as number | null) ?? 0;
  const trend = (latest.supertrend_direction as number | null) ?? 0;
  const rand = makeRng(`predict:${symbol}:${task}`);

  const raw = 0.5 + (50 - rsi) / 260 + Math.sign(macdHist) * 0.04 + trend * 0.05;
  const predicted = round(clamp(raw + uniform(rand, -0.03, 0.03), 0.05, 0.95), 4);

  const contributions = [
    { feature: "rsi_14", value: round(rsi, 2), contribution: round((50 - rsi) / 260, 4) },
    { feature: "macd_hist", value: round(macdHist, 3), contribution: round(Math.sign(macdHist) * 0.04, 4) },
    { feature: "supertrend_direction", value: trend, contribution: round(trend * 0.05, 4) },
    { feature: "volatility_20d", value: round((latest.volatility_20d as number | null) ?? 0.2, 4), contribution: round(uniform(rand, -0.03, 0.01), 4) },
    { feature: "adx", value: round((latest.adx as number | null) ?? 20, 2), contribution: round(uniform(rand, -0.02, 0.03), 4) },
  ].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

  const record = {
    id: `prd-live-${Date.now().toString(36)}`,
    symbol,
    model_name: model.name,
    model_version: model.version,
    predicted_value: predicted,
    confidence: round(Math.abs(predicted - 0.5) * 2, 4),
    actual_direction: null,
    correct: null,
    generated_at: new Date().toISOString(),
  };
  world.predictions.unshift(record);

  return {
    id: record.id,
    stock_symbol: symbol,
    model_name: model.name,
    model_version: model.version,
    predicted_value: predicted,
    confidence: record.confidence,
    shap_contributions: contributions,
    generated_at: record.generated_at,
  };
});
route("get", "/predictions/:symbol/forecast", (context) => {
  const instrument = requireInstrument(context.params.symbol);
  return buildForecast(instrument, numberOf(context, "horizon_days", 30));
});
route("get", "/predictions/:symbol/history", (context) => {
  const symbol = context.params.symbol.toUpperCase();
  const limit = numberOf(context, "limit", 100);
  return getWorld()
    .predictions.filter((prediction) => prediction.symbol === symbol)
    .slice(0, limit)
    .map((prediction) => ({
      id: prediction.id,
      model_name: prediction.model_name,
      model_version: prediction.model_version,
      predicted_value: prediction.predicted_value,
      confidence: prediction.confidence,
      actual_direction: prediction.actual_direction,
      correct: prediction.correct,
      generated_at: prediction.generated_at,
    }));
});
route("get", "/signals/recent", (context) => {
  const limit = numberOf(context, "limit", 6);
  const mw = marketWorld(marketOf(context));
  return [...mw.instruments]
    .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
    .slice(0, limit)
    .map(buildSignal);
});
route("post", "/signals/:symbol", (context) => buildSignal(requireInstrument(context.params.symbol)));
route("post", "/signals", (context) => {
  const body = bodyOf(context);
  const symbols = Array.isArray(body.symbols) ? (body.symbols as string[]) : [];
  return symbols
    .map((symbol) => findInstrument(symbol))
    .filter((instrument): instrument is DemoInstrument => Boolean(instrument))
    .map(buildSignal);
});

// News and watchlist
route("get", "/news/sentiment", (context) => {
  const code = marketOf(context);
  return sentimentSummary(newsItems(code, undefined, 100));
});
route("get", "/news", (context) => {
  const code = marketOf(context);
  const items = newsItems(code, context.query.symbol, numberOf(context, "limit", 20));
  return { items, summary: sentimentSummary(items) };
});
route("get", "/watchlists/default", (context) => watchlistPayload(marketOf(context)));
route("post", "/watchlists/:id/items", (context) => {
  const code = context.params.id.includes("us") ? "US" : "IN";
  const mw = marketWorld(code);
  const body = bodyOf(context);
  const symbol = stringField(body, "symbol").toUpperCase();
  if (!mw.bySymbol[symbol]) {
    throw new DemoApiError("validation_error", `${symbol} is not listed in this market.`, 422);
  }
  if (!mw.watchlistItems.some((item) => item.symbol === symbol)) {
    mw.watchlistItems.push({
      symbol,
      alertAbove: typeof body.alert_above === "number" ? body.alert_above : null,
      alertBelow: typeof body.alert_below === "number" ? body.alert_below : null,
    });
  }
  return watchlistPayload(code);
});
route("delete", "/watchlists/:id/items/:symbol", (context) => {
  const code = context.params.id.includes("us") ? "US" : "IN";
  const mw = marketWorld(code);
  const symbol = context.params.symbol.toUpperCase();
  mw.watchlistItems = mw.watchlistItems.filter((item) => item.symbol !== symbol);
  return watchlistPayload(code);
});

// Reports
route("get", "/reports", (context) => {
  const type = context.query.report_type;
  const limit = numberOf(context, "limit", 50);
  return getWorld()
    .reports.filter((report) => (type ? report.report_type === type : true))
    .slice(0, limit);
});
route("post", "/reports/generate", (context) => {
  const world = getWorld();
  const body = bodyOf(context);
  const type = stringField(body, "report_type", "portfolio");
  const format = stringField(body, "report_format", "pdf");
  const portfolioId = stringField(body, "portfolio_id") || null;
  world.counters.reports += 1;

  let title = `${type.charAt(0).toUpperCase()}${type.slice(1)} Report`;
  if (portfolioId) {
    try {
      title = `${title} - ${resolvePortfolio(portfolioId).portfolio.name}`;
    } catch {
      // A report for a portfolio that no longer exists still gets a title.
    }
  }
  const extension = format === "excel" ? "xlsx" : format;
  const report = {
    id: `rpt-live-${world.counters.reports}`,
    report_type: type,
    report_format: format,
    title,
    portfolio_id: portfolioId,
    size_bytes: 42_000 + world.counters.reports * 1_800,
    filename: `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.${extension}`,
    download_url: `/api/v1/reports/rpt-live-${world.counters.reports}/download`,
    created_at: new Date().toISOString(),
  };
  world.reports.unshift(report);
  return report;
});
route("delete", "/reports/:id", (context) => {
  const world = getWorld();
  world.reports = world.reports.filter((report) => report.id !== context.params.id);
  return { success: true, message: "Report deleted", id: context.params.id };
});

// Settings and admin
route("get", "/settings", () => ({ ...getWorld().settings }));
route("patch", "/settings", (context) => {
  const world = getWorld();
  const body = bodyOf(context);
  for (const [key, value] of Object.entries(body)) {
    if (key in world.settings && value !== null && value !== undefined) {
      world.settings[key] = value as string | number | boolean;
    }
  }
  return { ...world.settings };
});
route("post", "/settings/reset", () => {
  const world = getWorld();
  world.settings = {
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
  };
  return { ...world.settings };
});
route("get", "/settings/integrations", () => INTEGRATIONS);
route("get", "/admin/health", () => systemHealth());
route("get", "/admin/overview", (context) => adminOverview(numberOf(context, "window_hours", 24)));
route("get", "/admin/logs", (context) =>
  auditLog(numberOf(context, "limit", 50), context.query.action),
);

// Copilot
route("get", "/copilot/prompts", () => SUGGESTED_PROMPTS);
route("get", "/copilot/conversations", (context) =>
  getWorld()
    .conversations.slice(0, numberOf(context, "limit", 50))
    .map((conversation) => ({
      id: conversation.id,
      title: conversation.title,
      message_count: conversation.messages.length,
      created_at: conversation.created_at,
      updated_at: conversation.updated_at,
    })),
);
route("get", "/copilot/conversations/:id", (context) => {
  const conversation = getWorld().conversations.find((entry) => entry.id === context.params.id);
  if (!conversation) return notFound("Conversation not found.");
  return {
    id: conversation.id,
    title: conversation.title,
    message_count: conversation.messages.length,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    messages: conversation.messages,
  };
});
route("post", "/copilot/conversations", (context) => {
  const world = getWorld();
  const body = bodyOf(context);
  const conversation = {
    id: `cnv-${Date.now().toString(36)}`,
    title: stringField(body, "title", "New conversation"),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [],
  };
  world.conversations.unshift(conversation);
  return {
    id: conversation.id,
    title: conversation.title,
    message_count: 0,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
  };
});
route("delete", "/copilot/conversations/:id", (context) => {
  const world = getWorld();
  world.conversations = world.conversations.filter((entry) => entry.id !== context.params.id);
  return { success: true, message: "Conversation deleted", id: context.params.id };
});
route("post", "/copilot/query", (context) => {
  const world = getWorld();
  const body = bodyOf(context);
  const question = stringField(body, "question", "Summarize the documents.");
  const conversationId = stringField(body, "conversation_id") || null;
  const { answer, citations } = answerFor(question);
  world.counters.queries += 1;

  const message = {
    id: `msg-${Date.now().toString(36)}`,
    conversation_id: conversationId,
    question,
    answer,
    llm_provider: "extractive_fallback",
    citations,
    latency_ms: 340 + Math.floor(Math.random() * 260),
    generated_at: new Date().toISOString(),
  };

  const conversation = world.conversations.find((entry) => entry.id === conversationId);
  if (conversation) {
    conversation.messages.push(message);
    conversation.updated_at = message.generated_at;
    if (conversation.messages.length === 1) {
      conversation.title = question.slice(0, 48);
    }
  }
  return message;
});

// Documents
route("get", "/documents", (context) => getWorld().documents.slice(0, numberOf(context, "limit", 200)));
route("post", "/documents/upload", (context) => {
  const world = getWorld();
  world.counters.documents += 1;
  const form = context.raw;
  let filename = `uploaded-document-${world.counters.documents}.pdf`;
  let sizeBytes = 1_240_000;
  let documentType = "annual_report";

  if (typeof FormData !== "undefined" && form instanceof FormData) {
    const file = form.get("file");
    if (file && typeof file === "object" && "name" in file) {
      filename = String((file as File).name);
      sizeBytes = Number((file as File).size) || sizeBytes;
    }
    const type = form.get("document_type");
    if (typeof type === "string" && type) documentType = type;
  }

  const pageCount = Math.max(3, Math.round(sizeBytes / 42_000));
  const chunks = pageCount * 8;
  world.documents.unshift({
    id: `doc-live-${world.counters.documents}`,
    filename,
    document_type: documentType,
    page_count: pageCount,
    chunk_count: chunks,
    size_bytes: sizeBytes,
    stock_id: null,
    created_at: new Date().toISOString(),
  });

  return {
    id: `doc-live-${world.counters.documents}`,
    filename,
    document_type: documentType,
    page_count: pageCount,
    chunks_created: chunks,
    pages_with_no_extractable_text: [],
  };
});
route("delete", "/documents/:id", (context) => {
  const world = getWorld();
  world.documents = world.documents.filter((document) => document.id !== context.params.id);
  return { success: true, message: "Document removed from the corpus", id: context.params.id };
});

function serializePortfolio(portfolio: DemoPortfolio) {
  return {
    id: portfolio.id,
    name: portfolio.name,
    market: portfolio.market,
    base_currency: portfolio.baseCurrency,
    benchmark_symbol: portfolio.benchmarkSymbol,
    cash_balance: round(portfolio.cashBalance, 2),
    is_default: portfolio.isDefault,
    created_at: portfolio.createdAt,
  };
}

// --- Dispatch -------------------------------------------------------------------

export function resolveRoute(
  method: string,
  path: string,
): { handler: Handler; params: Record<string, string> } | null {
  const segments = path.split("/").filter(Boolean);
  const wanted = method.toLowerCase();

  for (const candidate of routes) {
    if (candidate.method !== wanted) continue;
    if (candidate.pattern.length !== segments.length) continue;

    const params: Record<string, string> = {};
    let matched = true;
    for (let index = 0; index < candidate.pattern.length; index += 1) {
      const expected = candidate.pattern[index];
      const actual = segments[index];
      if (expected.startsWith(":")) {
        params[expected.slice(1)] = decodeURIComponent(actual);
      } else if (expected.toLowerCase() !== actual.toLowerCase()) {
        matched = false;
        break;
      }
    }
    if (matched) return { handler: candidate.handler, params };
  }
  return null;
}
