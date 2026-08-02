/**
 * The demo universe.
 *
 * These tables are a deliberate mirror of `stockvision-backend/scripts/seed_data.py`
 * - same symbols, same sectors, same base prices, same market-cap units (Rs crore
 * for India, $ billion for the US), same starting positions and the same news
 * corpus. Demo mode is therefore a faithful stand-in for a seeded backend rather
 * than a different application wearing its skin.
 *
 * If you change the Python seeder, change this file too.
 */

import type { MarketCode } from "@/types";

export interface CatalogStock {
  symbol: string;
  name: string;
  sector: string;
  basePrice: number;
  marketCap: number;
}

export interface CatalogIndex {
  symbol: string;
  name: string;
  level: number;
  constituents: string[];
}

export interface CatalogNews {
  headline: string;
  source: string;
  category: string;
  symbol: string | null;
  summary: string;
}

export interface CatalogMarket {
  code: MarketCode;
  name: string;
  currency: string;
  currencySymbol: string;
  digitGrouping: "indian" | "western";
  exchange: string;
  benchmarkSymbol: string;
  timezone: string;
  sessionOpen: string;
  sessionClose: string;
  stocks: CatalogStock[];
  indices: CatalogIndex[];
  positions: { symbol: string; quantity: number }[];
  watchlist: string[];
  news: CatalogNews[];
  cash: number;
  riskFreeRate: number;
}

const INDIA_STOCKS: CatalogStock[] = [
  { symbol: "RELIANCE", name: "Reliance Industries Ltd", sector: "Energy", basePrice: 2830, marketCap: 1_920_000 },
  { symbol: "TCS", name: "Tata Consultancy Services Ltd", sector: "Information Technology", basePrice: 3560, marketCap: 1_300_000 },
  { symbol: "HDFCBANK", name: "HDFC Bank Ltd", sector: "Financial Services", basePrice: 1690, marketCap: 1_280_000 },
  { symbol: "INFY", name: "Infosys Ltd", sector: "Information Technology", basePrice: 1510, marketCap: 625_000 },
  { symbol: "ICICIBANK", name: "ICICI Bank Ltd", sector: "Financial Services", basePrice: 1230, marketCap: 865_000 },
  { symbol: "SBIN", name: "State Bank of India", sector: "Financial Services", basePrice: 808, marketCap: 721_000 },
  { symbol: "BHARTIARTL", name: "Bharti Airtel Ltd", sector: "Telecommunications", basePrice: 1445, marketCap: 860_000 },
  { symbol: "ITC", name: "ITC Ltd", sector: "Consumer Staples", basePrice: 437, marketCap: 546_000 },
  { symbol: "LT", name: "Larsen & Toubro Ltd", sector: "Industrials", basePrice: 3640, marketCap: 500_000 },
  { symbol: "KOTAKBANK", name: "Kotak Mahindra Bank Ltd", sector: "Financial Services", basePrice: 1755, marketCap: 349_000 },
  { symbol: "AXISBANK", name: "Axis Bank Ltd", sector: "Financial Services", basePrice: 1160, marketCap: 358_000 },
  { symbol: "HINDUNILVR", name: "Hindustan Unilever Ltd", sector: "Consumer Staples", basePrice: 2470, marketCap: 580_000 },
  { symbol: "MARUTI", name: "Maruti Suzuki India Ltd", sector: "Consumer Discretionary", basePrice: 12_450, marketCap: 391_000 },
  { symbol: "SUNPHARMA", name: "Sun Pharmaceutical Industries", sector: "Healthcare", basePrice: 1785, marketCap: 428_000 },
  { symbol: "TITAN", name: "Titan Company Ltd", sector: "Consumer Discretionary", basePrice: 3380, marketCap: 300_000 },
  { symbol: "WIPRO", name: "Wipro Ltd", sector: "Information Technology", basePrice: 542, marketCap: 283_000 },
];

const US_STOCKS: CatalogStock[] = [
  { symbol: "AAPL", name: "Apple Inc.", sector: "Information Technology", basePrice: 228.5, marketCap: 3460 },
  { symbol: "MSFT", name: "Microsoft Corporation", sector: "Information Technology", basePrice: 441.2, marketCap: 3280 },
  { symbol: "NVDA", name: "NVIDIA Corporation", sector: "Information Technology", basePrice: 135.4, marketCap: 3330 },
  { symbol: "GOOGL", name: "Alphabet Inc.", sector: "Communication Services", basePrice: 186.3, marketCap: 2290 },
  { symbol: "AMZN", name: "Amazon.com, Inc.", sector: "Consumer Discretionary", basePrice: 201.7, marketCap: 2110 },
  { symbol: "META", name: "Meta Platforms, Inc.", sector: "Communication Services", basePrice: 598.4, marketCap: 1510 },
  { symbol: "TSLA", name: "Tesla, Inc.", sector: "Consumer Discretionary", basePrice: 345.2, marketCap: 1100 },
  { symbol: "JPM", name: "JPMorgan Chase & Co.", sector: "Financial Services", basePrice: 248.6, marketCap: 700 },
  { symbol: "JNJ", name: "Johnson & Johnson", sector: "Healthcare", basePrice: 157.9, marketCap: 380 },
  { symbol: "XOM", name: "Exxon Mobil Corporation", sector: "Energy", basePrice: 118.3, marketCap: 520 },
  { symbol: "V", name: "Visa Inc.", sector: "Financial Services", basePrice: 312.8, marketCap: 615 },
  { symbol: "WMT", name: "Walmart Inc.", sector: "Consumer Staples", basePrice: 92.4, marketCap: 745 },
  { symbol: "UNH", name: "UnitedHealth Group Inc.", sector: "Healthcare", basePrice: 592.1, marketCap: 545 },
  { symbol: "PG", name: "Procter & Gamble Company", sector: "Consumer Staples", basePrice: 168.7, marketCap: 397 },
];

const INDIA_NEWS: CatalogNews[] = [
  { headline: "RBI keeps repo rate unchanged, signals continued focus on growth", source: "Economic Times", category: "Monetary Policy", symbol: null, summary: "The Monetary Policy Committee voted to hold the repo rate steady, citing moderating inflation and robust domestic demand." },
  { headline: "Reliance beats quarterly estimates as retail and Jio margins expand", source: "Business Standard", category: "Earnings", symbol: "RELIANCE", summary: "Consolidated revenue rose sharply, with net profit exceeding street expectations on strong operating leverage." },
  { headline: "IT stocks rally as global deal pipeline shows recovery", source: "Mint", category: "Sector", symbol: "TCS", summary: "Large-cap IT names gained after commentary pointed to improving discretionary spending among US clients." },
  { headline: "TCS wins multi-year transformation mandate from European bank", source: "Moneycontrol", category: "Contracts", symbol: "TCS", summary: "The deal strengthens the order book and supports growth guidance for the coming quarters." },
  { headline: "HDFC Bank reports steady loan growth, asset quality stable", source: "Financial Express", category: "Earnings", symbol: "HDFCBANK", summary: "Advances grew in double digits while gross non-performing assets remained flat sequentially." },
  { headline: "Infosys downgraded on margin concerns despite revenue beat", source: "Reuters India", category: "Analyst", symbol: "INFY", summary: "Analysts flagged weakness in operating margins even as revenue exceeded guidance." },
  { headline: "Auto sales slump in festive quarter as rural demand weakens", source: "Economic Times", category: "Sector", symbol: "MARUTI", summary: "Passenger vehicle dispatches declined, with entry-level models seeing the sharpest fall." },
  { headline: "Banking stocks surge as credit growth accelerates", source: "Mint", category: "Sector", symbol: "ICICIBANK", summary: "Private lenders led gains on the back of improving net interest margins." },
  { headline: "ITC announces record dividend after strong FMCG performance", source: "Business Standard", category: "Corporate Action", symbol: "ITC", summary: "The board approved a higher payout, citing robust cash generation across segments." },
  { headline: "Sun Pharma faces regulatory probe over manufacturing practices", source: "Reuters India", category: "Regulatory", symbol: "SUNPHARMA", summary: "The company said it is cooperating fully and does not expect a material impact on supply." },
  { headline: "Nifty closes at record high on sustained foreign inflows", source: "Moneycontrol", category: "Markets", symbol: null, summary: "Benchmark indices extended gains for a fourth straight session as institutional buying continued." },
  { headline: "Crude oil volatility raises input cost concerns for manufacturers", source: "Financial Express", category: "Commodities", symbol: null, summary: "Sharp swings in Brent have made input planning difficult across industrial sectors." },
  { headline: "Larsen & Toubro order inflow hits multi-quarter high", source: "Mint", category: "Earnings", symbol: "LT", summary: "Infrastructure and hydrocarbon awards drove the strongest inflow in six quarters." },
  { headline: "Airtel ARPU improves after tariff revision flows through", source: "Economic Times", category: "Earnings", symbol: "BHARTIARTL", summary: "Average revenue per user rose sequentially as the headline tariff increase reached the subscriber base." },
  { headline: "Titan sees jewellery demand hold up despite gold price surge", source: "Business Standard", category: "Sector", symbol: "TITAN", summary: "Same-store growth stayed positive even as record bullion prices weighed on ticket volumes." },
  { headline: "Foreign portfolio investors turn net buyers after three months", source: "Moneycontrol", category: "Markets", symbol: null, summary: "Flows reversed as global risk appetite improved and the rupee stabilised." },
];

const US_NEWS: CatalogNews[] = [
  { headline: "Fed signals patience on rate cuts as inflation cools gradually", source: "Reuters", category: "Monetary Policy", symbol: null, summary: "Officials indicated no urgency to ease policy, pointing to a resilient labour market." },
  { headline: "Nvidia beats on data-centre revenue, raises guidance", source: "Bloomberg", category: "Earnings", symbol: "NVDA", summary: "Quarterly revenue surged well past estimates as AI infrastructure demand accelerated." },
  { headline: "Apple unveils expanded services tier, shares jump", source: "CNBC", category: "Product", symbol: "AAPL", summary: "The announcement was received positively, with analysts raising services revenue forecasts." },
  { headline: "Microsoft cloud growth strong but capex weighs on margins", source: "WSJ", category: "Earnings", symbol: "MSFT", summary: "Azure growth exceeded expectations while heavy infrastructure spending pressured operating margins." },
  { headline: "Tesla deliveries miss estimates amid softer EV demand", source: "Reuters", category: "Earnings", symbol: "TSLA", summary: "Quarterly deliveries fell short of consensus as competition intensified in key markets." },
  { headline: "JPMorgan profit rises on higher net interest income", source: "Bloomberg", category: "Earnings", symbol: "JPM", summary: "The bank reported stronger-than-expected results, helped by resilient consumer credit." },
  { headline: "Amazon expands logistics network, targeting same-day coverage", source: "CNBC", category: "Operations", symbol: "AMZN", summary: "The buildout is expected to lift fulfilment costs near term while improving delivery speed." },
  { headline: "Healthcare stocks decline on policy uncertainty", source: "WSJ", category: "Sector", symbol: "UNH", summary: "Managed care names weakened following commentary on potential reimbursement changes." },
  { headline: "Meta advertising revenue accelerates on AI-driven targeting", source: "Bloomberg", category: "Earnings", symbol: "META", summary: "Ad impressions and pricing both improved, driving a significant revenue beat." },
  { headline: "Energy sector slumps as crude retreats from highs", source: "Reuters", category: "Sector", symbol: "XOM", summary: "Integrated majors fell alongside a broad decline in oil benchmarks." },
  { headline: "S&P 500 notches fresh record as breadth improves", source: "CNBC", category: "Markets", symbol: null, summary: "Gains were broad-based, with advancing issues outpacing decliners by a wide margin." },
  { headline: "Investors rotate into defensives amid volatility concerns", source: "WSJ", category: "Markets", symbol: null, summary: "Staples and utilities outperformed as investors trimmed exposure to high-beta names." },
  { headline: "Visa payment volumes grow on resilient cross-border travel", source: "Bloomberg", category: "Earnings", symbol: "V", summary: "Cross-border volume growth outpaced domestic, supporting the fee take rate." },
  { headline: "Walmart raises full-year outlook on grocery share gains", source: "CNBC", category: "Earnings", symbol: "WMT", summary: "Management cited continued trade-down behaviour among higher-income households." },
];

export const MARKET_CATALOG: Record<MarketCode, CatalogMarket> = {
  IN: {
    code: "IN",
    name: "India",
    currency: "INR",
    currencySymbol: "₹",
    digitGrouping: "indian",
    exchange: "NSE",
    benchmarkSymbol: "NIFTY50",
    timezone: "Asia/Kolkata",
    sessionOpen: "09:15",
    sessionClose: "15:30",
    stocks: INDIA_STOCKS,
    indices: [
      { symbol: "NIFTY50", name: "NIFTY 50", level: 24_584, constituents: INDIA_STOCKS.map((s) => s.symbol) },
      { symbol: "SENSEX", name: "SENSEX", level: 80_457, constituents: ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", "ITC", "LT", "HINDUNILVR", "MARUTI"] },
      { symbol: "BANKNIFTY", name: "BANK NIFTY", level: 52_145, constituents: ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"] },
      { symbol: "NIFTYIT", name: "NIFTY IT", level: 35_645, constituents: ["TCS", "INFY", "WIPRO"] },
    ],
    positions: [
      { symbol: "RELIANCE", quantity: 25 },
      { symbol: "TCS", quantity: 25 },
      { symbol: "HDFCBANK", quantity: 18 },
      { symbol: "INFY", quantity: 40 },
      { symbol: "ICICIBANK", quantity: 30 },
      { symbol: "ITC", quantity: 120 },
      { symbol: "SUNPHARMA", quantity: 12 },
    ],
    watchlist: ["RELIANCE", "TCS", "HDFCBANK", "BHARTIARTL", "MARUTI", "TITAN"],
    news: INDIA_NEWS,
    cash: 145_000,
    riskFreeRate: 0.066,
  },
  US: {
    code: "US",
    name: "United States",
    currency: "USD",
    currencySymbol: "$",
    digitGrouping: "western",
    exchange: "NASDAQ",
    benchmarkSymbol: "SPX",
    timezone: "America/New_York",
    sessionOpen: "09:30",
    sessionClose: "16:00",
    stocks: US_STOCKS,
    indices: [
      { symbol: "SPX", name: "S&P 500", level: 5842, constituents: US_STOCKS.map((s) => s.symbol) },
      { symbol: "NDX", name: "NASDAQ 100", level: 20_650, constituents: ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"] },
      { symbol: "DJI", name: "DOW JONES", level: 43_280, constituents: ["JPM", "JNJ", "WMT", "UNH", "PG", "MSFT", "AAPL", "V"] },
      { symbol: "SOX", name: "SEMICONDUCTORS", level: 5120, constituents: ["NVDA", "AAPL", "MSFT"] },
    ],
    positions: [
      { symbol: "AAPL", quantity: 60 },
      { symbol: "MSFT", quantity: 25 },
      { symbol: "NVDA", quantity: 80 },
      { symbol: "GOOGL", quantity: 40 },
      { symbol: "AMZN", quantity: 30 },
      { symbol: "JPM", quantity: 20 },
      { symbol: "JNJ", quantity: 35 },
    ],
    watchlist: ["AAPL", "NVDA", "MSFT", "TSLA", "META", "AMZN"],
    news: US_NEWS,
    cash: 12_400,
    riskFreeRate: 0.045,
  },
};

export const MARKET_CODES: MarketCode[] = ["IN", "US"];

/** Sessions of history generated per instrument - matches `N_DAYS` in the seeder. */
export const HISTORY_SESSIONS = 780;

/**
 * Seed suffix for the shared market factor.
 *
 * The generator is deterministic, so this string picks WHICH three-year market
 * history the demo shows. It was chosen by inspecting several: this one gives a
 * modestly profitable book with one losing position, an up day in India against
 * a down day in the US, and cross-sectional correlations around 0.5 - i.e. a
 * representative market rather than a highlight reel where everything is green.
 */
export const FACTOR_SEED_SUFFIX = "-e";

export const SUGGESTED_PROMPTS = [
  { label: "Summarize revenue", prompt: "Summarize the revenue performance described in the uploaded reports.", category: "Financials" },
  { label: "Key risks", prompt: "What are the principal risk factors disclosed in these documents?", category: "Risk" },
  { label: "Margin trend", prompt: "How did operating margins move, and what explanation is given?", category: "Financials" },
  { label: "Segment breakdown", prompt: "Break down performance by business segment.", category: "Financials" },
  { label: "Management outlook", prompt: "What forward guidance does management provide?", category: "Outlook" },
  { label: "Capital allocation", prompt: "Describe capital allocation: capex, buybacks and dividends.", category: "Capital" },
];

export const INTEGRATIONS = [
  { provider: "openai", label: "OpenAI", configured: false, description: "Powers the AI Copilot's generated answers. Without it the copilot uses the extractive fallback engine." },
  { provider: "gemini", label: "Google Gemini", configured: false, description: "Alternative LLM backend for the Copilot, used when no OpenAI key is present." },
  { provider: "alpha_vantage", label: "Alpha Vantage", configured: false, description: "Live daily price refresh via the scheduled Celery task." },
  { provider: "polygon", label: "Polygon.io", configured: false, description: "Alternative market-data provider for the price refresh task." },
];

/** Historical shocks used by the stress-test endpoint, as market-wide moves. */
export const STRESS_SCENARIOS = [
  { scenario: "2008 Global Financial Crisis", shock: -0.38, volMultiplier: 3.1 },
  { scenario: "2020 COVID-19 Crash", shock: -0.34, volMultiplier: 3.6 },
  { scenario: "2013 Taper Tantrum", shock: -0.12, volMultiplier: 1.8 },
  { scenario: "2022 Rate-Hike Repricing", shock: -0.19, volMultiplier: 2.0 },
  { scenario: "Single-Session Flash Crash", shock: -0.07, volMultiplier: 4.2 },
  { scenario: "Mild Growth Scare", shock: -0.05, volMultiplier: 1.4 },
];
