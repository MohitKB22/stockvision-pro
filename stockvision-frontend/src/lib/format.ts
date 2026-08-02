/**
 * Number, currency and date formatting.
 *
 * The Indian numbering system groups digits as 12,45,000 (lakh/crore), not
 * 1,245,000. Getting this wrong is immediately visible to an Indian user and
 * makes the product look foreign — so grouping is derived from the MARKET, not
 * from the browser locale (someone in London looking at NSE data should still see
 * lakhs).
 *
 * Every formatter is a pure function over an explicit locale/currency, so it can
 * be unit tested and reused server-side without touching `navigator`.
 */

export type DigitGrouping = "indian" | "western";

const LOCALE_BY_GROUPING: Record<DigitGrouping, string> = {
  indian: "en-IN",
  western: "en-US",
};

const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(key: string, factory: () => Intl.NumberFormat): Intl.NumberFormat {
  // Intl.NumberFormat construction is surprisingly expensive and these run inside
  // table cells rendered hundreds of times per view — caching turns a measurable
  // render cost into a map lookup.
  let formatter = formatterCache.get(key);
  if (!formatter) {
    formatter = factory();
    formatterCache.set(key, formatter);
  }
  return formatter;
}

export function formatNumber(
  value: number | null | undefined,
  options: { grouping?: DigitGrouping; decimals?: number; fallback?: string } = {},
): string {
  const { grouping = "indian", decimals = 2, fallback = "—" } = options;
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback;
  const locale = LOCALE_BY_GROUPING[grouping];
  return getFormatter(
    `n:${locale}:${decimals}`,
    () =>
      new Intl.NumberFormat(locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }),
  ).format(value);
}

export function formatCurrency(
  value: number | null | undefined,
  options: {
    symbol?: string;
    grouping?: DigitGrouping;
    decimals?: number;
    fallback?: string;
    signed?: boolean;
  } = {},
): string {
  const {
    symbol = "₹",
    grouping = "indian",
    decimals = 2,
    fallback = "—",
    signed = false,
  } = options;
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback;
  const sign = signed && value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${symbol}${formatNumber(Math.abs(value), { grouping, decimals })}`;
}

/**
 * Compact currency: ₹1.92L Cr / $3.46T.
 *
 * Uses lakh/crore scales for Indian grouping and K/M/B/T for western. A plain
 * `notation: "compact"` in en-IN produces inconsistent output across JS engines,
 * so the scale table is explicit.
 */
export function formatCompactCurrency(
  value: number | null | undefined,
  options: { symbol?: string; grouping?: DigitGrouping; fallback?: string } = {},
): string {
  const { symbol = "₹", grouping = "indian", fallback = "—" } = options;
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback;

  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  const scales =
    grouping === "indian"
      ? ([
          [1e7, "Cr"],
          [1e5, "L"],
          [1e3, "K"],
        ] as const)
      : ([
          [1e12, "T"],
          [1e9, "B"],
          [1e6, "M"],
          [1e3, "K"],
        ] as const);

  for (const [threshold, suffix] of scales) {
    if (abs >= threshold) return `${sign}${symbol}${(abs / threshold).toFixed(2)}${suffix}`;
  }
  return `${sign}${symbol}${abs.toFixed(2)}`;
}

export function formatCompactNumber(
  value: number | null | undefined,
  options: { grouping?: DigitGrouping; fallback?: string } = {},
): string {
  return formatCompactCurrency(value, { ...options, symbol: "" });
}

/** Percent from a RATIO (0.0521 -> "+5.21%"). Passing an already-multiplied value
 *  here was the single most common bug in this codebase's ancestor. */
export function formatPercent(
  value: number | null | undefined,
  options: { decimals?: number; signed?: boolean; fallback?: string } = {},
): string {
  const { decimals = 2, signed = true, fallback = "—" } = options;
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback;
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(decimals)}%`;
}

export function formatVolume(value: number | null | undefined, grouping: DigitGrouping = "indian") {
  return formatCompactNumber(value, { grouping, fallback: "—" });
}

const DATE_FORMATS = {
  short: { day: "2-digit", month: "short" },
  medium: { day: "2-digit", month: "short", year: "numeric" },
  time: { hour: "2-digit", minute: "2-digit" },
  datetime: { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" },
} satisfies Record<string, Intl.DateTimeFormatOptions>;

export function formatDate(
  value: string | Date | null | undefined,
  variant: keyof typeof DATE_FORMATS = "medium",
): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", DATE_FORMATS[variant]).format(date);
}

/** "4 hours ago". Falls back to an absolute date past a week, where relative
 *  phrasing stops being useful. */
export function formatRelativeTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";

  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (seconds < 3600) return formatter.format(-Math.floor(seconds / 60), "minute");
  if (seconds < 86400) return formatter.format(-Math.floor(seconds / 3600), "hour");
  if (seconds < 604800) return formatter.format(-Math.floor(seconds / 86400), "day");
  return formatDate(date, "medium");
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || !Number.isFinite(seconds)) return "—";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || !Number.isFinite(bytes)) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

/** Semantic direction for a value — the single place gain/loss colour is decided,
 *  so it can never drift between components. */
export function toneFor(value: number | null | undefined): "gain" | "loss" | "flat" {
  if (value === null || value === undefined || !Number.isFinite(value) || value === 0)
    return "flat";
  return value > 0 ? "gain" : "loss";
}

export function toneClass(value: number | null | undefined): string {
  const tone = toneFor(value);
  return tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink-muted";
}
