/**
 * API contract types.
 *
 * These mirror the Pydantic schemas in stockvision-backend/app/schemas/. They are
 * hand-maintained rather than generated, and `scripts/verify-api-contract.mjs`
 * checks them against the live OpenAPI document so drift is caught in CI rather
 * than at runtime.
 */

export type MarketCode = "IN" | "US";
export type DigitGrouping = "indian" | "western";
export type SignalAction = "strong_buy" | "buy" | "hold" | "sell" | "strong_sell";
export type OrderSide = "buy" | "sell";
export type OrderStatus = "filled" | "pending" | "cancelled" | "rejected";
export type ModelTask =
  | "trend_classification"
  | "next_day_return"
  | "volatility_prediction"
  | "regime_detection";
export type ModelAlgorithm = "xgboost" | "lightgbm" | "random_forest";
export type ModelStage = "staging" | "production" | "archived";
export type DocumentType =
  | "annual_report"
  | "quarterly_report"
  | "earnings_call"
  | "research_report";
export type SentimentLabel = "positive" | "neutral" | "negative";
export type ReportType = "portfolio" | "risk" | "prediction" | "tax";
export type ReportFormat = "pdf" | "csv" | "excel";

// --- Errors -------------------------------------------------------------
export interface ApiErrorBody {
  code: string;
  message: string;
  status: number;
  context?: Record<string, unknown>;
  request_id?: string;
}
export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

// --- Markets -------------------------------------------------------------
export interface IndexDefinition {
  symbol: string;
  name: string;
  constituent_count: number;
}
export interface MarketDefinition {
  code: MarketCode;
  name: string;
  currency: string;
  currency_symbol: string;
  digit_grouping: DigitGrouping;
  exchange: string;
  benchmark_symbol: string;
  timezone: string;
  session_open: string;
  session_close: string;
  indices: IndexDefinition[];
}
export interface SessionStatus {
  market: MarketCode;
  timezone: string;
  local_time: string;
  session_open: string;
  session_close: string;
  is_open: boolean;
  is_weekday: boolean;
  holiday_calendar_applied: boolean;
}

// --- Instruments & prices -------------------------------------------------
export interface StockPublic {
  id: string;
  symbol: string;
  name: string;
  exchange: string;
  market: MarketCode;
  sector: string | null;
  industry: string | null;
  currency: string;
  is_index: boolean;
  market_cap: number | null;
}
export interface PriceBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
}
export interface FeatureSnapshot {
  timestamp: string;
  close: number;
  indicators: Record<string, number | null>;
}
export interface StockQuote {
  stock_id: string;
  symbol: string;
  name: string;
  exchange: string;
  market: MarketCode;
  sector: string | null;
  currency: string;
  last_price: number;
  previous_close: number;
  change: number;
  change_pct: number;
  volume: number;
  avg_volume_30d: number;
  week_52_high: number;
  week_52_low: number;
  market_cap: number | null;
  sparkline: number[];
}
export interface IndexQuote {
  symbol: string;
  name: string;
  market: MarketCode;
  level: number;
  previous_close: number;
  change: number;
  change_pct: number;
  sparkline: number[];
  constituent_count: number;
  is_synthetic: boolean;
}
export interface MoverQuote {
  symbol: string;
  name: string;
  sector: string | null;
  last_price: number;
  change: number;
  change_pct: number;
  volume: number;
  turnover: number;
  sparkline: number[];
}
export interface SectorPerformance {
  sector: string;
  change_pct: number;
  advancers: number;
  decliners: number;
  constituent_count: number;
  total_turnover: number;
  market_cap: number;
  top_symbol: string;
  bottom_symbol: string;
}
export interface MarketBreadth {
  market: MarketCode;
  total: number;
  advancers: number;
  decliners: number;
  unchanged: number;
  advance_decline_ratio: number;
  new_highs: number;
  new_lows: number;
  above_avg_volume: number;
  total_turnover: number;
}
export interface WeekRangeEntry {
  symbol: string;
  name: string;
  last_price: number;
  week_52_high: number;
  week_52_low: number;
  pct_from_high: number;
  pct_from_low: number;
  position_in_range: number;
}
export interface HeatmapEntry {
  symbol: string;
  name: string;
  sector: string;
  change_pct: number;
  market_cap: number;
  last_price: number;
  turnover: number;
}
export interface MarketOverview {
  market: MarketCode;
  currency: string;
  currency_symbol: string;
  indices: IndexQuote[];
  gainers: MoverQuote[];
  losers: MoverQuote[];
  most_active: MoverQuote[];
  sectors: SectorPerformance[];
  breadth: MarketBreadth;
}
export interface MoversResponse {
  gainers: MoverQuote[];
  losers: MoverQuote[];
  most_active: MoverQuote[];
}
export interface WeekRangeResponse {
  near_52_week_high: WeekRangeEntry[];
  near_52_week_low: WeekRangeEntry[];
}

// --- Portfolio ---------------------------------------------------------------
export interface Portfolio {
  id: string;
  name: string;
  market: MarketCode;
  base_currency: string;
  benchmark_symbol: string;
  cash_balance: number;
  is_default: boolean;
  created_at: string;
}
export interface Holding {
  stock_id: string;
  symbol: string;
  name: string;
  sector: string | null;
  quantity: number;
  average_cost: number;
  current_price: number;
  previous_close: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl: number;
  day_change: number;
  day_change_pct: number;
  weight_pct: number;
}
export interface AllocationSlice {
  label: string;
  value: number;
  weight_pct: number;
}
export interface PerformancePoint {
  timestamp: string;
  value: number;
  return_pct: number;
}
export interface PortfolioSummary {
  portfolio_id: string;
  name: string;
  market: MarketCode;
  base_currency: string;
  benchmark_symbol: string;
  cash_balance: number;
  total_market_value: number;
  total_value: number;
  total_cost_basis: number;
  total_unrealized_pnl: number;
  total_unrealized_pnl_pct: number;
  total_realized_pnl: number;
  day_change: number;
  day_change_pct: number;
  holding_count: number;
  holdings: Holding[];
  sector_exposure: AllocationSlice[];
  asset_allocation: AllocationSlice[];
}
export interface Transaction {
  id: string;
  symbol: string;
  name: string;
  side: OrderSide;
  quantity: number;
  price: number;
  value: number;
  transaction_cost: number;
  slippage: number;
  status: OrderStatus;
  is_simulated: boolean;
  notes: string | null;
  executed_at: string;
}

// --- Risk ------------------------------------------------------------------------
export interface DrawdownPoint {
  timestamp: string;
  drawdown: number;
}
export interface RiskMetrics {
  portfolio_id: string;
  lookback_days: number;
  observations: number;
  portfolio_value: number;
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  value_at_risk_95_historical: number;
  value_at_risk_95_parametric: number;
  value_at_risk_95_monte_carlo: number;
  expected_shortfall_95: number;
  value_at_risk_amount: number;
  beta: number | null;
  alpha: number | null;
  benchmark_symbol: string;
  return_distribution: number[];
  drawdown_series: DrawdownPoint[];
}
export interface MonteCarloResult {
  portfolio_id: string;
  horizon_days: number;
  n_simulations: number;
  initial_value: number;
  percentiles: Record<string, number[]>;
  sample_paths: number[][];
  terminal: {
    mean: number;
    median: number;
    std: number;
    p5: number;
    p95: number;
    probability_of_loss: number;
    expected_return_pct: number;
  };
}
export interface CorrelationMatrix {
  portfolio_id: string;
  lookback_days: number;
  labels: string[];
  matrix: number[][];
  average_correlation: number | null;
}
export interface StressScenario {
  scenario: string;
  market_shock_pct: number;
  portfolio_impact_pct: number;
  portfolio_impact_value: number;
  resulting_value: number;
  stressed_daily_volatility: number;
  stressed_annual_volatility: number;
  beta_used: number;
  beta_assumed: boolean;
}
export interface StressTestResult {
  portfolio_id: string;
  portfolio_value: number;
  benchmark_symbol: string;
  scenarios: StressScenario[];
}

// --- ML -------------------------------------------------------------------------
export interface ShapContribution {
  feature: string;
  value: number;
  contribution: number;
}
export interface ModelMetrics {
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  roc_auc: number | null;
  rmse: number | null;
  mae: number | null;
  r2: number | null;
  n_train_samples: number;
  n_test_samples: number;
  n_walk_forward_splits: number;
}
export interface ModelPublic {
  id: string;
  name: string;
  version: number;
  task: ModelTask;
  algorithm: ModelAlgorithm;
  stage: ModelStage;
  metrics: Partial<ModelMetrics>;
  hyperparameters: Record<string, number | string | boolean>;
  feature_count: number;
  trained_at: string;
}
export interface TrainModelResponse {
  model_id: string;
  name: string;
  version: number;
  task: ModelTask;
  algorithm: ModelAlgorithm;
  stage: ModelStage;
  best_hyperparameters: Record<string, number | string | boolean>;
  metrics: ModelMetrics;
  top_features: { feature: string; mean_abs_shap: number }[];
  trained_at: string;
}
export interface PredictionResponse {
  id: string;
  stock_symbol: string;
  model_name: string;
  model_version: number;
  predicted_value: number;
  confidence: number;
  shap_contributions: ShapContribution[];
  generated_at: string;
}
export interface PredictionHistoryEntry {
  id: string;
  model_name: string;
  model_version: number;
  predicted_value: number;
  confidence: number;
  actual_direction: number | null;
  correct: boolean | null;
  generated_at: string;
}
export interface ForecastPoint {
  day: number;
  expected: number;
  lower: number;
  upper: number;
}
export interface ForecastResponse {
  symbol: string;
  last_price: number;
  horizon_days: number;
  model_informed: boolean;
  probability_up: number | null;
  daily_volatility: number;
  annualized_volatility: number;
  expected_return_pct: number;
  expected_price: number;
  historical: { timestamp: string; close: number }[];
  forecast: ForecastPoint[];
}
export interface SignalResponse {
  id: string;
  stock_symbol: string;
  action: SignalAction;
  confidence: number;
  risk_score: number;
  supporting_indicators: Record<string, number>;
  explanation: string;
  llm_explanation: string | null;
  shap_contributions: ShapContribution[];
  generated_at: string;
}

// --- News --------------------------------------------------------------------------
export interface NewsArticle {
  id: string;
  headline: string;
  summary: string | null;
  source: string;
  url: string;
  market: MarketCode;
  symbol: string | null;
  published_at: string;
  sentiment_score: number | null;
  sentiment_label: SentimentLabel;
  impact_score: number | null;
  entities: string[];
}
export interface SentimentSummary {
  engine: string;
  article_count: number;
  average_sentiment: number;
  positive: number;
  neutral: number;
  negative: number;
}
export interface NewsFeed {
  items: NewsArticle[];
  summary: SentimentSummary;
}

// --- Watchlist -----------------------------------------------------------------------
export interface WatchlistItem {
  id: string;
  symbol: string;
  name: string;
  sector: string | null;
  position: number;
  alert_above: number | null;
  alert_below: number | null;
  quote: StockQuote | null;
  alert_triggered: boolean;
}
export interface Watchlist {
  id: string;
  name: string;
  market: MarketCode;
  is_default: boolean;
  item_count: number;
  items: WatchlistItem[];
}

// --- Copilot --------------------------------------------------------------------------
export interface Citation {
  document_name: string;
  page_number: number;
  chunk_text: string;
  relevance_score: number;
}
export interface CopilotMessage {
  id: string;
  conversation_id: string | null;
  question: string;
  answer: string;
  llm_provider: string;
  citations: Citation[];
  latency_ms: number | null;
  generated_at: string;
}
export interface Conversation {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}
export interface ConversationDetail extends Conversation {
  messages: CopilotMessage[];
}
export interface SuggestedPrompt {
  label: string;
  prompt: string;
  category: string;
}
export interface DocumentPublic {
  id: string;
  filename: string;
  document_type: DocumentType;
  page_count: number | null;
  chunk_count: number;
  size_bytes: number | null;
  stock_id: string | null;
  created_at: string;
}
export interface DocumentUploadResponse {
  id: string;
  filename: string;
  document_type: DocumentType;
  page_count: number;
  chunks_created: number;
  pages_with_no_extractable_text: number[];
}

// --- Reports -----------------------------------------------------------------------------
export interface GeneratedReport {
  id: string;
  report_type: ReportType;
  report_format: ReportFormat;
  title: string;
  portfolio_id: string | null;
  size_bytes: number;
  filename: string;
  download_url: string;
  created_at: string;
}

// --- Settings / admin ----------------------------------------------------------------------
export interface AppSettings {
  theme: "dark" | "midnight" | "system";
  language: string;
  default_market: MarketCode;
  default_dashboard: string;
  number_format: "auto" | "indian" | "western";
  email_notifications: boolean;
  push_notifications: boolean;
  market_alerts: boolean;
  signal_alerts: boolean;
  price_alerts: boolean;
  weekly_digest: boolean;
  chart_type: "area" | "line" | "candlestick";
  auto_refresh_seconds: number;
  reduced_motion: boolean;
}
export interface IntegrationStatus {
  provider: string;
  label: string;
  configured: boolean;
  description: string;
}
export interface StatCard {
  key: string;
  label: string;
  value: number;
  display: string;
  change_pct: number | null;
  hint: string;
}
export interface SystemHealth {
  status: string;
  environment: string;
  version: string;
  uptime_seconds: number;
  database_connected: boolean;
  database_latency_ms: number;
  database_dialect: string;
  redis_configured: boolean;
  llm_provider: string;
  python_version: string;
  platform: string;
  cpu_count: number;
  disk_usage_pct: number;
  document_storage_bytes: number;
  model_storage_bytes: number;
  report_storage_bytes: number;
}
export interface AdminOverview {
  window_hours: number;
  cards: StatCard[];
  api_calls_series: { timestamp: string; value: number }[];
  calls_by_action: Record<string, number>;
  data_counts: Record<string, number>;
  health: SystemHealth;
}
export interface AuditEntry {
  id: string;
  action: string;
  resource: string;
  detail: Record<string, unknown>;
  ip_address: string | null;
  request_id: string | null;
  status_code: number | null;
  duration_ms: number | null;
  timestamp: string;
}

export interface OperationResult {
  success: boolean;
  message: string;
  id: string | null;
}
