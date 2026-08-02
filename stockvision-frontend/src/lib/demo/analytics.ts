/**
 * Derived analytics for demo mode.
 *
 * Everything here is computed from the generated price history rather than
 * hardcoded: VaR comes from the actual return distribution, correlations from
 * the actual holdings' returns, beta from a regression against the actual
 * benchmark series. The prices are synthetic, but the analytics ON them are the
 * real calculations - so the numbers move together the way they should, and a
 * reviewer poking at the risk page finds it internally consistent.
 */

import {
  clamp,
  correlation,
  gaussian,
  makeRng,
  mean,
  percentile,
  round,
  stdev,
  toReturns,
} from "./rng";
import { positionInRange } from "./series";
import { STRESS_SCENARIOS } from "./catalog";
import type { DemoInstrument, DemoMarketWorld, DemoPortfolio } from "./world";

const TRADING_DAYS = 252;

export function instrumentQuote(instrument: DemoInstrument) {
  return {
    stock_id: instrument.id,
    symbol: instrument.symbol,
    name: instrument.name,
    exchange: instrument.exchange,
    market: instrument.market,
    sector: instrument.sector,
    currency: instrument.currency,
    last_price: instrument.lastPrice,
    previous_close: instrument.previousClose,
    change: instrument.change,
    change_pct: instrument.changePct,
    volume: instrument.volume,
    avg_volume_30d: instrument.avgVolume30d,
    week_52_high: instrument.weekHigh,
    week_52_low: instrument.weekLow,
    market_cap: instrument.marketCap,
    sparkline: instrument.sparkline,
  };
}

export function instrumentPublic(instrument: DemoInstrument) {
  return {
    id: instrument.id,
    symbol: instrument.symbol,
    name: instrument.name,
    exchange: instrument.exchange,
    market: instrument.market,
    sector: instrument.sector,
    industry: instrument.sector,
    currency: instrument.currency,
    is_index: false,
    market_cap: instrument.marketCap,
  };
}

export function moverQuote(instrument: DemoInstrument) {
  return {
    symbol: instrument.symbol,
    name: instrument.name,
    sector: instrument.sector,
    last_price: instrument.lastPrice,
    change: instrument.change,
    change_pct: instrument.changePct,
    volume: instrument.volume,
    turnover: instrument.turnover,
    sparkline: instrument.sparkline,
  };
}

export function indexQuote(index: DemoMarketWorld["indices"][number]) {
  return {
    symbol: index.symbol,
    name: index.name,
    market: index.market,
    level: index.level,
    previous_close: index.previousClose,
    change: index.change,
    change_pct: index.changePct,
    sparkline: index.sparkline,
    constituent_count: index.constituentCount,
    is_synthetic: true,
  };
}

// --- Market aggregates --------------------------------------------------------

export function sectorPerformance(mw: DemoMarketWorld) {
  const bySector = new Map<string, DemoInstrument[]>();
  for (const instrument of mw.instruments) {
    const bucket = bySector.get(instrument.sector) ?? [];
    bucket.push(instrument);
    bySector.set(instrument.sector, bucket);
  }

  return [...bySector.entries()]
    .map(([sector, members]) => {
      const totalCap = members.reduce((total, member) => total + member.marketCap, 0) || 1;
      const weighted = members.reduce(
        (total, member) => total + member.changePct * (member.marketCap / totalCap),
        0,
      );
      const sorted = [...members].sort((a, b) => b.changePct - a.changePct);
      return {
        sector,
        change_pct: round(weighted, 6),
        advancers: members.filter((member) => member.changePct > 0).length,
        decliners: members.filter((member) => member.changePct < 0).length,
        constituent_count: members.length,
        total_turnover: members.reduce((total, member) => total + member.turnover, 0),
        market_cap: totalCap,
        top_symbol: sorted[0].symbol,
        bottom_symbol: sorted[sorted.length - 1].symbol,
      };
    })
    .sort((a, b) => b.change_pct - a.change_pct);
}

export function marketBreadth(mw: DemoMarketWorld) {
  const instruments = mw.instruments;
  const advancers = instruments.filter((item) => item.changePct > 0).length;
  const decliners = instruments.filter((item) => item.changePct < 0).length;
  const unchanged = instruments.length - advancers - decliners;
  return {
    market: mw.catalog.code,
    total: instruments.length,
    advancers,
    decliners,
    unchanged,
    advance_decline_ratio: round(advancers / Math.max(decliners, 1), 2),
    new_highs: instruments.filter((item) => item.lastPrice >= item.weekHigh * 0.995).length,
    new_lows: instruments.filter((item) => item.lastPrice <= item.weekLow * 1.005).length,
    above_avg_volume: instruments.filter((item) => item.volume > item.avgVolume30d).length,
    total_turnover: instruments.reduce((total, item) => total + item.turnover, 0),
  };
}

export function weekRangeEntry(instrument: DemoInstrument) {
  return {
    symbol: instrument.symbol,
    name: instrument.name,
    last_price: instrument.lastPrice,
    week_52_high: instrument.weekHigh,
    week_52_low: instrument.weekLow,
    pct_from_high: round(instrument.lastPrice / instrument.weekHigh - 1, 6),
    pct_from_low: round(instrument.lastPrice / instrument.weekLow - 1, 6),
    position_in_range: round(
      positionInRange(instrument.lastPrice, instrument.weekLow, instrument.weekHigh),
      4,
    ),
  };
}

// --- Portfolio ----------------------------------------------------------------

export function portfolioHoldings(mw: DemoMarketWorld, portfolio: DemoPortfolio) {
  const priced = portfolio.positions
    .map((position) => {
      const instrument = mw.bySymbol[position.symbol];
      if (!instrument) return null;
      const marketValue = instrument.lastPrice * position.quantity;
      const costBasis = position.averageCost * position.quantity;
      return { position, instrument, marketValue, costBasis };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  const totalValue = priced.reduce((total, entry) => total + entry.marketValue, 0) || 1;

  return priced.map(({ position, instrument, marketValue, costBasis }) => {
    const unrealized = marketValue - costBasis;
    const dayChange = instrument.change * position.quantity;
    return {
      stock_id: instrument.id,
      symbol: instrument.symbol,
      name: instrument.name,
      sector: instrument.sector,
      quantity: position.quantity,
      average_cost: round(position.averageCost, 2),
      current_price: instrument.lastPrice,
      previous_close: instrument.previousClose,
      market_value: round(marketValue, 2),
      cost_basis: round(costBasis, 2),
      unrealized_pnl: round(unrealized, 2),
      unrealized_pnl_pct: round(unrealized / (costBasis || 1), 6),
      realized_pnl: round(position.realizedPnl, 2),
      day_change: round(dayChange, 2),
      day_change_pct: instrument.changePct,
      weight_pct: round(marketValue / totalValue, 6),
    };
  });
}

/** Portfolio value replayed over the last `days` sessions at constant holdings. */
export function portfolioValueSeries(mw: DemoMarketWorld, portfolio: DemoPortfolio, days: number) {
  const reference = mw.instruments[0];
  const length = Math.min(days, reference?.closes.length ?? 0);
  if (!length) return { timestamps: [] as string[], values: [] as number[] };

  const timestamps: string[] = [];
  const values: number[] = [];
  const offset = (reference.closes.length ?? 0) - length;

  for (let step = 0; step < length; step += 1) {
    const dayIndex = offset + step;
    let value = portfolio.cashBalance;
    for (const position of portfolio.positions) {
      const instrument = mw.bySymbol[position.symbol];
      if (instrument) value += instrument.closes[dayIndex] * position.quantity;
    }
    timestamps.push(reference.bars[dayIndex].timestamp);
    values.push(round(value, 2));
  }
  return { timestamps, values };
}

export function portfolioSummary(mw: DemoMarketWorld, portfolio: DemoPortfolio) {
  const holdings = portfolioHoldings(mw, portfolio);
  const totalMarketValue = holdings.reduce((total, holding) => total + holding.market_value, 0);
  const totalCost = holdings.reduce((total, holding) => total + holding.cost_basis, 0);
  const dayChange = holdings.reduce((total, holding) => total + holding.day_change, 0);
  const totalValue = totalMarketValue + portfolio.cashBalance;
  const previousValue = totalValue - dayChange;

  const bySector = new Map<string, number>();
  for (const holding of holdings) {
    const key = holding.sector ?? "Unclassified";
    bySector.set(key, (bySector.get(key) ?? 0) + holding.market_value);
  }

  const sectorExposure = [...bySector.entries()]
    .map(([label, value]) => ({
      label,
      value: round(value, 2),
      weight_pct: round(value / (totalMarketValue || 1), 6),
    }))
    .sort((a, b) => b.value - a.value);

  return {
    portfolio_id: portfolio.id,
    name: portfolio.name,
    market: portfolio.market,
    base_currency: portfolio.baseCurrency,
    benchmark_symbol: portfolio.benchmarkSymbol,
    cash_balance: round(portfolio.cashBalance, 2),
    total_market_value: round(totalMarketValue, 2),
    total_value: round(totalValue, 2),
    total_cost_basis: round(totalCost, 2),
    total_unrealized_pnl: round(totalMarketValue - totalCost, 2),
    total_unrealized_pnl_pct: round((totalMarketValue - totalCost) / (totalCost || 1), 6),
    total_realized_pnl: round(
      holdings.reduce((total, holding) => total + holding.realized_pnl, 0),
      2,
    ),
    day_change: round(dayChange, 2),
    day_change_pct: round(dayChange / (previousValue || 1), 6),
    holding_count: holdings.length,
    holdings,
    sector_exposure: sectorExposure,
    asset_allocation: [
      {
        label: "Equity",
        value: round(totalMarketValue, 2),
        weight_pct: round(totalMarketValue / (totalValue || 1), 6),
      },
      {
        label: "Cash",
        value: round(portfolio.cashBalance, 2),
        weight_pct: round(portfolio.cashBalance / (totalValue || 1), 6),
      },
    ],
  };
}

export function performanceSeries(mw: DemoMarketWorld, portfolio: DemoPortfolio, days: number) {
  const { timestamps, values } = portfolioValueSeries(mw, portfolio, days);
  const base = values[0] || 1;
  return timestamps.map((timestamp, index) => ({
    timestamp,
    value: values[index],
    return_pct: round(values[index] / base - 1, 6),
  }));
}

// --- Risk ---------------------------------------------------------------------

export function riskMetrics(mw: DemoMarketWorld, portfolio: DemoPortfolio, lookbackDays: number) {
  const { values } = portfolioValueSeries(mw, portfolio, lookbackDays);
  const returns = toReturns(values);
  const averageReturn = mean(returns);
  const volatility = stdev(returns);
  const annualReturn = averageReturn * TRADING_DAYS;
  const annualVol = volatility * Math.sqrt(TRADING_DAYS);
  const riskFree = mw.catalog.riskFreeRate;

  const downside = returns.filter((value) => value < 0);
  const downsideDeviation = stdev(downside) * Math.sqrt(TRADING_DAYS);

  // Drawdown from the running peak of the value series.
  let peak = values[0] ?? 0;
  let maxDrawdown = 0;
  const drawdownSeries = values.map((value, index) => {
    peak = Math.max(peak, value);
    const drawdown = peak > 0 ? value / peak - 1 : 0;
    maxDrawdown = Math.min(maxDrawdown, drawdown);
    return {
      timestamp: portfolioValueTimestamp(mw, lookbackDays, index),
      drawdown: round(drawdown, 6),
    };
  });

  const historicalVar = -percentile(returns, 0.05);
  const parametricVar = -(averageReturn - 1.645 * volatility);

  // Monte Carlo VaR: 20,000 draws from a normal fitted to the same returns.
  const rand = makeRng(`var:${portfolio.id}:${lookbackDays}`);
  const simulated: number[] = [];
  for (let index = 0; index < 20_000; index += 1) {
    simulated.push(averageReturn + volatility * gaussian(rand));
  }
  const monteCarloVar = -percentile(simulated, 0.05);

  const tail = [...returns].sort((a, b) => a - b).slice(0, Math.max(1, Math.floor(returns.length * 0.05)));
  const expectedShortfall = -mean(tail);

  const benchmark = mw.indices.find((index) => index.symbol === portfolio.benchmarkSymbol);
  let beta: number | null = null;
  let alpha: number | null = null;
  if (benchmark) {
    const benchmarkReturns = toReturns(benchmark.series.slice(-values.length));
    const length = Math.min(benchmarkReturns.length, returns.length);
    const left = returns.slice(returns.length - length);
    const right = benchmarkReturns.slice(benchmarkReturns.length - length);
    const benchmarkVariance = stdev(right) ** 2;
    if (benchmarkVariance > 0) {
      const meanLeft = mean(left);
      const meanRight = mean(right);
      let covariance = 0;
      for (let index = 0; index < length; index += 1) {
        covariance += (left[index] - meanLeft) * (right[index] - meanRight);
      }
      covariance /= Math.max(1, length - 1);
      beta = round(covariance / benchmarkVariance, 4);
      alpha = round(annualReturn - (riskFree + beta * (meanRight * TRADING_DAYS - riskFree)), 4);
    }
  }

  const portfolioValue = values[values.length - 1] ?? 0;

  return {
    portfolio_id: portfolio.id,
    lookback_days: lookbackDays,
    observations: returns.length,
    portfolio_value: round(portfolioValue, 2),
    annualized_return: round(annualReturn, 6),
    annualized_volatility: round(annualVol, 6),
    sharpe_ratio: round(annualVol > 0 ? (annualReturn - riskFree) / annualVol : 0, 4),
    sortino_ratio: round(
      downsideDeviation > 0 ? (annualReturn - riskFree) / downsideDeviation : 0,
      4,
    ),
    max_drawdown: round(maxDrawdown, 6),
    value_at_risk_95_historical: round(historicalVar, 6),
    value_at_risk_95_parametric: round(parametricVar, 6),
    value_at_risk_95_monte_carlo: round(monteCarloVar, 6),
    expected_shortfall_95: round(expectedShortfall, 6),
    value_at_risk_amount: round(historicalVar * portfolioValue, 2),
    beta,
    alpha,
    benchmark_symbol: portfolio.benchmarkSymbol,
    return_distribution: returns.map((value) => round(value, 6)),
    drawdown_series: drawdownSeries,
  };
}

function portfolioValueTimestamp(mw: DemoMarketWorld, lookbackDays: number, index: number): string {
  const reference = mw.instruments[0];
  const length = Math.min(lookbackDays, reference.closes.length);
  const offset = reference.closes.length - length;
  return reference.bars[Math.min(reference.bars.length - 1, offset + index)].timestamp;
}

export function monteCarlo(
  mw: DemoMarketWorld,
  portfolio: DemoPortfolio,
  horizonDays: number,
  simulations: number,
) {
  const { values } = portfolioValueSeries(mw, portfolio, 252);
  const returns = toReturns(values);
  const drift = mean(returns);
  const volatility = stdev(returns);
  const initialValue = values[values.length - 1] ?? 0;
  const rand = makeRng(`mc:${portfolio.id}:${horizonDays}:${simulations}`);

  const runs = clamp(simulations, 200, 5_000);
  const paths: number[][] = [];
  for (let simulation = 0; simulation < runs; simulation += 1) {
    const path = [initialValue];
    let value = initialValue;
    for (let day = 1; day <= horizonDays; day += 1) {
      value *= 1 + drift + volatility * gaussian(rand);
      path.push(value);
    }
    paths.push(path);
  }

  const levels: [string, number][] = [
    ["p5", 0.05],
    ["p25", 0.25],
    ["p50", 0.5],
    ["p75", 0.75],
    ["p95", 0.95],
  ];
  const percentiles: Record<string, number[]> = {};
  for (const [key] of levels) percentiles[key] = [];
  for (let day = 0; day <= horizonDays; day += 1) {
    const slice = paths.map((path) => path[day]);
    for (const [key, level] of levels) {
      percentiles[key].push(round(percentile(slice, level), 2));
    }
  }

  const terminals = paths.map((path) => path[path.length - 1]);
  const sorted = [...terminals].sort((a, b) => a - b);

  return {
    portfolio_id: portfolio.id,
    horizon_days: horizonDays,
    n_simulations: runs,
    initial_value: round(initialValue, 2),
    percentiles,
    sample_paths: paths.slice(0, 40).map((path) => path.map((value) => round(value, 2))),
    terminal: {
      mean: round(mean(terminals), 2),
      median: round(sorted[Math.floor(sorted.length / 2)], 2),
      std: round(stdev(terminals), 2),
      p5: round(percentile(terminals, 0.05), 2),
      p95: round(percentile(terminals, 0.95), 2),
      probability_of_loss: round(
        terminals.filter((value) => value < initialValue).length / terminals.length,
        4,
      ),
      expected_return_pct: round(mean(terminals) / (initialValue || 1) - 1, 6),
    },
  };
}

export function correlationMatrix(
  mw: DemoMarketWorld,
  portfolio: DemoPortfolio,
  lookbackDays: number,
) {
  const members = portfolio.positions
    .map((position) => mw.bySymbol[position.symbol])
    .filter((instrument): instrument is DemoInstrument => Boolean(instrument));

  const seriesReturns = members.map((instrument) =>
    toReturns(instrument.closes.slice(-lookbackDays)),
  );

  const matrix = seriesReturns.map((left) =>
    seriesReturns.map((right) => round(correlation(left, right), 4)),
  );

  const offDiagonal: number[] = [];
  for (let row = 0; row < matrix.length; row += 1) {
    for (let column = row + 1; column < matrix.length; column += 1) {
      offDiagonal.push(matrix[row][column]);
    }
  }

  return {
    portfolio_id: portfolio.id,
    lookback_days: lookbackDays,
    labels: members.map((instrument) => instrument.symbol),
    matrix,
    average_correlation: offDiagonal.length ? round(mean(offDiagonal), 4) : null,
  };
}

export function stressTest(mw: DemoMarketWorld, portfolio: DemoPortfolio) {
  const metrics = riskMetrics(mw, portfolio, 252);
  const portfolioValue = metrics.portfolio_value;
  const beta = metrics.beta ?? 1;
  const betaAssumed = metrics.beta === null;
  const dailyVol = metrics.annualized_volatility / Math.sqrt(TRADING_DAYS);

  return {
    portfolio_id: portfolio.id,
    portfolio_value: portfolioValue,
    benchmark_symbol: portfolio.benchmarkSymbol,
    scenarios: STRESS_SCENARIOS.map((scenario) => {
      const impactPct = scenario.shock * beta;
      const impactValue = portfolioValue * impactPct;
      return {
        scenario: scenario.scenario,
        market_shock_pct: scenario.shock,
        portfolio_impact_pct: round(impactPct, 6),
        portfolio_impact_value: round(impactValue, 2),
        resulting_value: round(portfolioValue + impactValue, 2),
        stressed_daily_volatility: round(dailyVol * scenario.volMultiplier, 6),
        stressed_annual_volatility: round(
          metrics.annualized_volatility * scenario.volMultiplier,
          6,
        ),
        beta_used: round(beta, 4),
        beta_assumed: betaAssumed,
      };
    }),
  };
}

// --- Signals, forecasts, sentiment ----------------------------------------------

const SIGNAL_ORDER = ["strong_sell", "sell", "hold", "buy", "strong_buy"] as const;

export function buildSignal(instrument: DemoInstrument) {
  const latest = instrument.indicators[instrument.indicators.length - 1];
  const rsi = (latest.rsi_14 as number | null) ?? 50;
  const macdHist = (latest.macd_hist as number | null) ?? 0;
  const adx = (latest.adx as number | null) ?? 20;
  const trend = (latest.supertrend_direction as number | null) ?? 0;
  const sma20 = (latest.sma_20 as number | null) ?? instrument.lastPrice;
  const sma50 = (latest.sma_50 as number | null) ?? instrument.lastPrice;

  // Each indicator votes in [-1, 1]; the blend is a plain average so the
  // explanation below can name the specific contributors honestly.
  const votes: Record<string, number> = {
    rsi_14: clamp((50 - rsi) / 25, -1, 1),
    macd_hist: clamp(macdHist / (instrument.lastPrice * 0.01), -1, 1),
    trend: trend,
    price_vs_sma20: clamp((instrument.lastPrice / sma20 - 1) * 25, -1, 1),
    sma20_vs_sma50: clamp((sma20 / sma50 - 1) * 25, -1, 1),
    adx_strength: clamp((adx - 20) / 25, -1, 1) * (trend >= 0 ? 1 : -1),
  };

  const score = mean(Object.values(votes));
  const bucket =
    score > 0.45 ? 4 : score > 0.15 ? 3 : score > -0.15 ? 2 : score > -0.45 ? 1 : 0;
  const action = SIGNAL_ORDER[bucket];
  const confidence = round(clamp(Math.abs(score) * 1.35 + 0.18, 0.2, 0.95), 4);
  const volatility = (latest.volatility_20d as number | null) ?? 0.25;

  const drivers = Object.entries(votes)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 3)
    .map(([name, value]) => `${name} ${value >= 0 ? "supports" : "opposes"} the call`);

  return {
    id: `sig-${instrument.symbol.toLowerCase()}-${Math.floor(Date.now() / 60_000)}`,
    stock_symbol: instrument.symbol,
    action,
    confidence,
    risk_score: round(clamp(volatility * 2.1, 0.05, 0.98), 4),
    supporting_indicators: Object.fromEntries(
      Object.entries(votes).map(([name, value]) => [name, round(value, 3)]),
    ),
    explanation:
      `Blended technical read on ${instrument.symbol}: RSI at ${round(rsi, 1)}, ` +
      `ADX at ${round(adx, 1)} and the 20/50 SMA relationship ` +
      `${sma20 >= sma50 ? "positive" : "negative"}. ${drivers.join("; ")}. ` +
      `No trained model is registered for this symbol in demo mode, so this is an ` +
      `indicators-only call - the same degradation path the live engine takes.`,
    llm_explanation: null,
    shap_contributions: [],
    generated_at: new Date().toISOString(),
  };
}

export function buildForecast(instrument: DemoInstrument, horizonDays: number) {
  const closes = instrument.closes;
  const returns = toReturns(closes.slice(-252));
  const dailyVol = stdev(returns);
  const drift = mean(returns);
  const lastPrice = instrument.lastPrice;

  const forecast = [];
  for (let day = 1; day <= horizonDays; day += 1) {
    const expected = lastPrice * (1 + drift * day);
    const band = lastPrice * dailyVol * Math.sqrt(day) * 1.645;
    forecast.push({
      day,
      expected: round(expected, 2),
      lower: round(expected - band, 2),
      upper: round(expected + band, 2),
    });
  }

  const latest = instrument.indicators[instrument.indicators.length - 1];
  const rsi = (latest.rsi_14 as number | null) ?? 50;

  return {
    symbol: instrument.symbol,
    last_price: lastPrice,
    horizon_days: horizonDays,
    model_informed: false,
    probability_up: round(clamp(0.5 + (50 - rsi) / 400 + drift * 12, 0.15, 0.85), 4),
    daily_volatility: round(dailyVol, 6),
    annualized_volatility: round(dailyVol * Math.sqrt(TRADING_DAYS), 6),
    expected_return_pct: round(drift * horizonDays, 6),
    expected_price: round(lastPrice * (1 + drift * horizonDays), 2),
    historical: instrument.bars.slice(-120).map((bar) => ({
      timestamp: bar.timestamp,
      close: bar.close,
    })),
    forecast,
  };
}

const POSITIVE_TERMS = [
  "beat", "beats", "rally", "surge", "surged", "record", "strong", "rises", "rose",
  "expand", "expands", "wins", "improv", "gain", "gains", "accelerat", "raises",
  "recovery", "resilient", "outperform", "high", "growth", "steady", "upgrade",
];
const NEGATIVE_TERMS = [
  "miss", "misses", "slump", "decline", "declined", "downgrad", "probe", "concern",
  "weaken", "fell", "falls", "uncertainty", "retreat", "pressur", "crash", "risk",
  "cut", "shortfall", "loss", "slow", "worse", "volatil",
];

/** Deterministic lexicon sentiment - the same class of model the backend uses. */
export function scoreSentiment(text: string) {
  const lowered = text.toLowerCase();
  let positive = 0;
  let negative = 0;
  for (const term of POSITIVE_TERMS) if (lowered.includes(term)) positive += 1;
  for (const term of NEGATIVE_TERMS) if (lowered.includes(term)) negative += 1;
  const score = round(clamp((positive - negative) / (positive + negative + 1), -1, 1), 4);
  const label = score > 0.12 ? "positive" : score < -0.12 ? "negative" : "neutral";
  return { score, label };
}
