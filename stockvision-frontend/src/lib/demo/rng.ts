/**
 * Deterministic pseudo-randomness for demo mode.
 *
 * Every number the demo backend serves is derived from a seeded generator rather
 * than `Math.random()`. That matters for three reasons:
 *
 *   1. React Query refetches. A price that changes on every poll makes the UI
 *      look broken, not live.
 *   2. Screenshots and recordings stay reproducible across reloads.
 *   3. The same seed produces the same history the Python seeder would - the
 *      demo is a faithful stand-in for the real backend, not a different app.
 *
 * `mulberry32` is used rather than a hand-rolled LCG: it is 32-bit, has a full
 * period, and passes the randomness tests that matter here (no visible banding
 * in a price series).
 */

/** FNV-1a. Stable across engines, unlike `String.prototype.hashCode` folklore. */
export function hashSeed(text: string): number {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export type Rng = () => number;

export function makeRng(seed: number | string): Rng {
  let state = (typeof seed === "string" ? hashSeed(seed) : seed) >>> 0;
  return function next(): number {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Box-Muller. Returns a standard normal draw. */
export function gaussian(rand: Rng): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = rand();
  while (v === 0) v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export function uniform(rand: Rng, min: number, max: number): number {
  return min + rand() * (max - min);
}

export function intBetween(rand: Rng, min: number, max: number): number {
  return Math.floor(uniform(rand, min, max + 1));
}

export function pick<T>(rand: Rng, items: readonly T[]): T {
  return items[Math.min(items.length - 1, Math.floor(rand() * items.length))];
}

export function round(value: number, decimals = 2): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

export function mean(values: readonly number[]): number {
  return values.length ? sum(values) / values.length : 0;
}

export function stdev(values: readonly number[]): number {
  if (values.length < 2) return 0;
  const average = mean(values);
  const variance = sum(values.map((value) => (value - average) ** 2)) / (values.length - 1);
  return Math.sqrt(variance);
}

/** Linear-interpolated percentile. `p` is a fraction: 0.05 is the 5th percentile. */
export function percentile(values: readonly number[], p: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const position = clamp(p, 0, 1) * (sorted.length - 1);
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

export function correlation(a: readonly number[], b: readonly number[]): number {
  const length = Math.min(a.length, b.length);
  if (length < 3) return 0;
  const left = a.slice(a.length - length);
  const right = b.slice(b.length - length);
  const meanLeft = mean(left);
  const meanRight = mean(right);
  let covariance = 0;
  let varianceLeft = 0;
  let varianceRight = 0;
  for (let index = 0; index < length; index += 1) {
    const dl = left[index] - meanLeft;
    const dr = right[index] - meanRight;
    covariance += dl * dr;
    varianceLeft += dl * dl;
    varianceRight += dr * dr;
  }
  const denominator = Math.sqrt(varianceLeft * varianceRight);
  return denominator === 0 ? 0 : covariance / denominator;
}

/** Simple returns from a close series. */
export function toReturns(series: readonly number[]): number[] {
  const returns: number[] = [];
  for (let index = 1; index < series.length; index += 1) {
    const previous = series[index - 1];
    if (previous > 0) returns.push(series[index] / previous - 1);
  }
  return returns;
}
