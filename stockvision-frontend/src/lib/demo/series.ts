/**
 * Synthetic OHLCV and the technical indicators computed from it.
 *
 * The generator is geometric Brownian motion with regime-switching volatility -
 * the same model `scripts/generate_synthetic_data.py` uses server-side. The path
 * is rescaled at the end so the LAST close lands on the catalog's base price:
 * without that, three years of compounding drift puts RELIANCE at Rs 9,000 and
 * every screenshot looks wrong.
 *
 * Indicators are real implementations, not decorative noise. RSI and ATR use
 * Wilder smoothing, MACD uses proper EMAs, and ADX is derived from directional
 * movement rather than faked - so the signal engine downstream is reasoning over
 * numbers that behave like the real thing.
 */

import { clamp, gaussian, makeRng, round, type Rng } from "./rng";

export interface DemoBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
}

const MS_PER_DAY = 86_400_000;

/**
 * The most recent `count` weekday timestamps, oldest first.
 *
 * Anchored to midnight UTC of the current day so the whole series shifts
 * forward once per day rather than jittering with every request.
 */
export function sessionDates(count: number): string[] {
  const dates: string[] = [];
  const cursor = new Date(Math.floor(Date.now() / MS_PER_DAY) * MS_PER_DAY);
  while (dates.length < count) {
    const day = cursor.getUTCDay();
    if (day !== 0 && day !== 6) dates.push(cursor.toISOString());
    cursor.setUTCDate(cursor.getUTCDate() - 1);
  }
  return dates.reverse();
}

const factorCache = new Map<string, number[]>();

/**
 * The market factor: one shared daily log-return series per market.
 *
 * Without it every symbol is an independent random walk, and the consequences
 * show up immediately in the product - the correlation matrix comes out near
 * zero everywhere, portfolio beta lands around 0.3, and diversified risk looks
 * implausibly low. A single common factor with regime-switching volatility
 * gives cross-sectional correlations in the 0.3-0.6 range and market-wide
 * drawdowns where every name falls together, which is what an equity book
 * actually looks like.
 */
export function marketFactor(key: string, sessions: number): number[] {
  const cacheKey = `${key}:${sessions}`;
  const cached = factorCache.get(cacheKey);
  if (cached) return cached;

  const rand = makeRng(`factor:${key}`);
  const dt = 1 / 252;
  const annualDrift = 0.105;
  const baseVol = 0.15;
  let stressed = false;
  const series: number[] = [];

  for (let index = 0; index < sessions; index += 1) {
    // Calm regimes persist longer than stressed ones, which is what produces
    // volatility CLUSTERING rather than uniform noise.
    const switchProbability = stressed ? 0.06 : 0.011;
    if (rand() < switchProbability) stressed = !stressed;
    const vol = baseVol * (stressed ? 2.4 : 0.88);
    series.push((annualDrift - 0.5 * vol * vol) * dt + vol * Math.sqrt(dt) * gaussian(rand));
  }

  factorCache.set(cacheKey, series);
  return series;
}

interface SeriesOptions {
  symbol: string;
  basePrice: number;
  sessions: number;
  /** Market whose common factor this instrument loads on. */
  factorKey?: string;
  annualDrift?: number;
  annualVol?: number;
}

export function generateBars({
  symbol,
  basePrice,
  sessions,
  factorKey,
  annualDrift,
  annualVol,
}: SeriesOptions): DemoBar[] {
  const rand: Rng = makeRng(`bars:${symbol}`);
  // Idiosyncratic parameters. Total volatility is the quadrature sum of the
  // factor loading and this, so these are deliberately lower than a standalone
  // single-stock vol would be.
  const idioDrift = annualDrift ?? -0.06 + rand() * 0.16;
  const idioVol = annualVol ?? 0.12 + rand() * 0.18;
  const beta = 0.62 + rand() * 0.86;
  const factor = factorKey ? marketFactor(factorKey, sessions) : null;
  const dt = 1 / 252;

  let price = basePrice;
  const closes: number[] = [];
  for (let index = 0; index < sessions; index += 1) {
    const systematic = factor ? beta * factor[index] : 0;
    const idiosyncratic =
      (idioDrift - 0.5 * idioVol * idioVol) * dt + idioVol * Math.sqrt(dt) * gaussian(rand);
    price *= Math.exp(systematic + idiosyncratic);
    closes.push(price);
  }

  // Rescale so the final close is the catalog price (+/- a small deterministic
  // offset so not every symbol sits exactly on a round number).
  const target = basePrice * (0.97 + rand() * 0.06);
  const scale = target / closes[closes.length - 1];
  const dates = sessionDates(sessions);
  const baseVolume = 250_000 + rand() * 4_500_000;

  return closes.map((rawClose, index) => {
    const close = rawClose * scale;
    const previous = index === 0 ? close : closes[index - 1] * scale;
    const open = previous * (1 + gaussian(rand) * 0.0025);
    const spread = Math.abs(gaussian(rand)) * 0.006 + 0.0015;
    const high = Math.max(open, close) * (1 + spread);
    const low = Math.min(open, close) * (1 - spread);
    // Volume rises with the size of the move - a flat volume series is the
    // giveaway that a chart is fabricated.
    const moveMagnitude = Math.abs(close / previous - 1);
    const volume = Math.round(baseVolume * (0.55 + rand() * 0.9) * (1 + moveMagnitude * 22));
    return {
      timestamp: dates[index],
      open: round(open, 2),
      high: round(high, 2),
      low: round(low, 2),
      close: round(close, 2),
      volume,
      source: "demo_synthetic",
    };
  });
}

// --- Indicators --------------------------------------------------------------

export function sma(values: readonly number[], period: number): (number | null)[] {
  const output: (number | null)[] = [];
  let running = 0;
  for (let index = 0; index < values.length; index += 1) {
    running += values[index];
    if (index >= period) running -= values[index - period];
    output.push(index >= period - 1 ? running / period : null);
  }
  return output;
}

export function ema(values: readonly number[], period: number): (number | null)[] {
  const output: (number | null)[] = [];
  const multiplier = 2 / (period + 1);
  let previous: number | null = null;
  let seed = 0;
  for (let index = 0; index < values.length; index += 1) {
    if (index < period - 1) {
      seed += values[index];
      output.push(null);
      continue;
    }
    if (previous === null) {
      seed += values[index];
      previous = seed / period;
    } else {
      previous = (values[index] - previous) * multiplier + previous;
    }
    output.push(previous);
  }
  return output;
}

/** Wilder's RSI. */
export function rsi(closes: readonly number[], period = 14): (number | null)[] {
  const output: (number | null)[] = [null];
  let avgGain = 0;
  let avgLoss = 0;
  for (let index = 1; index < closes.length; index += 1) {
    const change = closes[index] - closes[index - 1];
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);
    if (index <= period) {
      avgGain += gain / period;
      avgLoss += loss / period;
      output.push(index === period ? 100 - 100 / (1 + avgGain / (avgLoss || 1e-9)) : null);
      continue;
    }
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    output.push(100 - 100 / (1 + avgGain / (avgLoss || 1e-9)));
  }
  return output;
}

export function atr(bars: readonly DemoBar[], period = 14): (number | null)[] {
  const output: (number | null)[] = [];
  let previous: number | null = null;
  let seed = 0;
  for (let index = 0; index < bars.length; index += 1) {
    const bar = bars[index];
    const priorClose = index === 0 ? bar.close : bars[index - 1].close;
    const trueRange = Math.max(
      bar.high - bar.low,
      Math.abs(bar.high - priorClose),
      Math.abs(bar.low - priorClose),
    );
    if (index < period) {
      seed += trueRange;
      output.push(index === period - 1 ? seed / period : null);
      if (index === period - 1) previous = seed / period;
      continue;
    }
    previous = ((previous ?? trueRange) * (period - 1) + trueRange) / period;
    output.push(previous);
  }
  return output;
}

interface DirectionalIndex {
  adx: (number | null)[];
  plusDi: (number | null)[];
  minusDi: (number | null)[];
}

export function directionalIndex(bars: readonly DemoBar[], period = 14): DirectionalIndex {
  const plusDm: number[] = [0];
  const minusDm: number[] = [0];
  const trueRanges: number[] = [0];
  for (let index = 1; index < bars.length; index += 1) {
    const upMove = bars[index].high - bars[index - 1].high;
    const downMove = bars[index - 1].low - bars[index].low;
    plusDm.push(upMove > downMove && upMove > 0 ? upMove : 0);
    minusDm.push(downMove > upMove && downMove > 0 ? downMove : 0);
    trueRanges.push(
      Math.max(
        bars[index].high - bars[index].low,
        Math.abs(bars[index].high - bars[index - 1].close),
        Math.abs(bars[index].low - bars[index - 1].close),
      ),
    );
  }

  const smooth = (values: number[]): (number | null)[] => {
    const output: (number | null)[] = [];
    let running: number | null = null;
    let seed = 0;
    for (let index = 0; index < values.length; index += 1) {
      if (index <= period) {
        seed += values[index];
        if (index === period) {
          running = seed;
          output.push(running);
        } else {
          output.push(null);
        }
        continue;
      }
      running = (running ?? 0) - (running ?? 0) / period + values[index];
      output.push(running);
    }
    return output;
  };

  const smoothedPlus = smooth(plusDm);
  const smoothedMinus = smooth(minusDm);
  const smoothedTr = smooth(trueRanges);

  const plusDi: (number | null)[] = [];
  const minusDi: (number | null)[] = [];
  const dx: (number | null)[] = [];
  for (let index = 0; index < bars.length; index += 1) {
    const tr = smoothedTr[index];
    if (tr === null || tr === 0 || smoothedPlus[index] === null || smoothedMinus[index] === null) {
      plusDi.push(null);
      minusDi.push(null);
      dx.push(null);
      continue;
    }
    const plus = (100 * (smoothedPlus[index] as number)) / tr;
    const minus = (100 * (smoothedMinus[index] as number)) / tr;
    plusDi.push(plus);
    minusDi.push(minus);
    dx.push(plus + minus === 0 ? 0 : (100 * Math.abs(plus - minus)) / (plus + minus));
  }

  const adx: (number | null)[] = [];
  let runningAdx: number | null = null;
  let seedCount = 0;
  let seedSum = 0;
  for (let index = 0; index < dx.length; index += 1) {
    const value = dx[index];
    if (value === null) {
      adx.push(null);
      continue;
    }
    if (seedCount < period) {
      seedSum += value;
      seedCount += 1;
      if (seedCount === period) {
        runningAdx = seedSum / period;
        adx.push(runningAdx);
      } else {
        adx.push(null);
      }
      continue;
    }
    runningAdx = ((runningAdx ?? value) * (period - 1) + value) / period;
    adx.push(runningAdx);
  }

  return { adx, plusDi, minusDi };
}

/** Rolling annualized standard deviation of daily returns. */
export function rollingVolatility(closes: readonly number[], period = 20): (number | null)[] {
  const output: (number | null)[] = [];
  for (let index = 0; index < closes.length; index += 1) {
    if (index < period) {
      output.push(null);
      continue;
    }
    const window: number[] = [];
    for (let offset = index - period + 1; offset <= index; offset += 1) {
      window.push(closes[offset] / closes[offset - 1] - 1);
    }
    const average = window.reduce((total, value) => total + value, 0) / window.length;
    const variance =
      window.reduce((total, value) => total + (value - average) ** 2, 0) / (window.length - 1);
    output.push(Math.sqrt(variance) * Math.sqrt(252));
  }
  return output;
}

export type IndicatorRow = Record<string, number | null>;

/**
 * The full indicator panel, one row per bar. Keys match the labels the stock
 * detail page knows how to render (`INDICATOR_GUIDE` in that page).
 */
export function computeIndicators(bars: readonly DemoBar[]): IndicatorRow[] {
  const closes = bars.map((bar) => bar.close);
  const sma20 = sma(closes, 20);
  const sma50 = sma(closes, 50);
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const rsi14 = rsi(closes, 14);
  const atr14 = atr(bars, 14);
  const volatility = rollingVolatility(closes, 20);
  const { adx, plusDi, minusDi } = directionalIndex(bars, 14);

  const macdLine: (number | null)[] = closes.map((_, index) =>
    ema12[index] !== null && ema26[index] !== null
      ? (ema12[index] as number) - (ema26[index] as number)
      : null,
  );
  const macdDefined = macdLine.map((value) => value ?? 0);
  const macdSignalRaw = ema(macdDefined, 9);

  return bars.map((bar, index) => {
    const macd = macdLine[index];
    const signal = macd === null ? null : macdSignalRaw[index];
    const middle = sma20[index];
    let upper: number | null = null;
    let lower: number | null = null;
    if (middle !== null && index >= 19) {
      const window = closes.slice(index - 19, index + 1);
      const average = window.reduce((total, value) => total + value, 0) / window.length;
      const deviation = Math.sqrt(
        window.reduce((total, value) => total + (value - average) ** 2, 0) / window.length,
      );
      upper = middle + 2 * deviation;
      lower = middle - 2 * deviation;
    }
    const trend =
      sma20[index] !== null && sma50[index] !== null
        ? (sma20[index] as number) >= (sma50[index] as number)
          ? 1
          : -1
        : null;

    const clean = (value: number | null, decimals = 2): number | null =>
      value === null || !Number.isFinite(value) ? null : round(value, decimals);

    return {
      rsi_14: clean(rsi14[index]),
      macd: clean(macd, 3),
      macd_signal: clean(signal, 3),
      macd_hist: macd !== null && signal !== null ? clean(macd - signal, 3) : null,
      sma_20: clean(sma20[index]),
      sma_50: clean(sma50[index]),
      ema_12: clean(ema12[index]),
      bb_upper: clean(upper),
      bb_lower: clean(lower),
      atr_14: clean(atr14[index]),
      adx: clean(adx[index]),
      plus_di: clean(plusDi[index]),
      minus_di: clean(minusDi[index]),
      volatility_20d: clean(volatility[index], 4),
      supertrend_direction: trend,
      close: round(bar.close, 2),
    };
  });
}

/** Percent position of `value` inside [low, high], clamped to 0..1. */
export function positionInRange(value: number, low: number, high: number): number {
  if (high <= low) return 0.5;
  return clamp((value - low) / (high - low), 0, 1);
}
