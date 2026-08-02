import type { ModelAlgorithm, ModelTask, SignalAction } from "@/types";

/** Presentation metadata for a signal. Colour is derived here, once, so a BUY pill
 *  can never be green in one component and blue in another. */
export const SIGNAL_META: Record<SignalAction, { label: string; tone: "gain" | "loss" | "flat" }> =
  {
    strong_buy: { label: "STRONG BUY", tone: "gain" },
    buy: { label: "BUY", tone: "gain" },
    hold: { label: "HOLD", tone: "flat" },
    sell: { label: "SELL", tone: "loss" },
    strong_sell: { label: "STRONG SELL", tone: "loss" },
  };

export const MODEL_TASKS: { value: ModelTask; label: string; description: string }[] = [
  {
    value: "trend_classification",
    label: "Trend Classification",
    description: "Predicts the probability that the next session closes higher.",
  },
  {
    value: "next_day_return",
    label: "Next-Day Return",
    description: "Regresses the magnitude of the next session's return.",
  },
  {
    value: "volatility_prediction",
    label: "Volatility Prediction",
    description: "Forecasts near-term realized volatility.",
  },
  {
    value: "regime_detection",
    label: "Regime Detection",
    description: "Classifies the prevailing market regime.",
  },
];

export const MODEL_ALGORITHMS: { value: ModelAlgorithm; label: string }[] = [
  { value: "xgboost", label: "XGBoost" },
  { value: "lightgbm", label: "LightGBM" },
  { value: "random_forest", label: "Random Forest" },
];

export const TIMEFRAMES = [
  { value: "1W", label: "1W", bars: 5 },
  { value: "1M", label: "1M", bars: 22 },
  { value: "3M", label: "3M", bars: 66 },
  { value: "6M", label: "6M", bars: 126 },
  { value: "1Y", label: "1Y", bars: 252 },
  { value: "MAX", label: "MAX", bars: 2000 },
] as const;

export type TimeframeValue = (typeof TIMEFRAMES)[number]["value"];

/** Sequential palette for allocation donuts and category charts. Ordered so
 *  adjacent slices stay distinguishable, including for the most common forms of
 *  colour-vision deficiency. */
export const CHART_PALETTE = [
  "hsl(217 91% 60%)",
  "hsl(262 83% 66%)",
  "hsl(158 74% 45%)",
  "hsl(38 92% 55%)",
  "hsl(199 89% 55%)",
  "hsl(330 81% 60%)",
  "hsl(173 80% 40%)",
  "hsl(280 65% 60%)",
  "hsl(25 95% 53%)",
  "hsl(190 90% 50%)",
];

export const DOCUMENT_TYPES = [
  { value: "annual_report", label: "Annual Report" },
  { value: "quarterly_report", label: "Quarterly Report (10-Q)" },
  { value: "earnings_call", label: "Earnings Call Transcript" },
  { value: "research_report", label: "Research Report" },
] as const;
