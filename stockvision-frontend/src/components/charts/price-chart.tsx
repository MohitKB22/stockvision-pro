"use client";

import * as React from "react";
import {
  AreaSeries,
  CandlestickSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import type { PriceBar } from "@/types";

/**
 * Runtime narrowing for the series union.
 *
 * `seriesType()` is Lightweight Charts' own discriminator, which makes this a
 * genuine type guard rather than an assertion — the check that runs at runtime is
 * the same one the type system then relies on. The alternative (casting the data
 * to `any` at the setData call) silences the compiler without proving the shapes
 * actually match.
 */
function isCandlestickSeries(
  series: ISeriesApi<"Candlestick"> | ISeriesApi<"Area">,
): series is ISeriesApi<"Candlestick"> {
  return series.seriesType() === "Candlestick";
}

/**
 * Candlestick / area price chart, powered by TradingView's Lightweight Charts.
 *
 * This is the same rendering engine behind TradingView's own widgets, running
 * fully locally — deliberately chosen over an embedded TradingView iframe widget,
 * which requires an outbound connection to tradingview.com and renders an empty
 * box in any network-restricted or air-gapped deployment. Same visual language, no
 * external runtime dependency, and the data plotted is this platform's own.
 *
 * Imperative lifecycle notes:
 *   - The chart is created ONCE and disposed on unmount. Re-creating it on every
 *     data change leaks WebGL contexts; browsers cap those (~16) and the chart
 *     silently stops rendering after enough navigations.
 *   - Resize goes through a ResizeObserver rather than a window listener, so it
 *     responds to the sidebar collapsing, not just to window resizes.
 */
export function PriceChart({
  bars,
  height = 320,
  variant = "candlestick",
  currencySymbol = "₹",
}: {
  bars: PriceBar[];
  height?: number;
  variant?: "candlestick" | "area";
  currencySymbol?: string;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<ISeriesApi<"Candlestick"> | ISeriesApi<"Area"> | null>(null);

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: false,
      width: container.clientWidth,
      height,
      layout: {
        background: { color: "transparent" },
        textColor: "hsl(217, 15%, 52%)",
        fontFamily: "var(--font-sans)",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "hsla(220, 26%, 18%, 0.6)" },
      },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: { borderVisible: false, timeVisible: false, secondsVisible: false },
      crosshair: {
        mode: 1,
        vertLine: {
          color: "hsla(217, 91%, 60%, 0.5)",
          width: 1,
          style: 2,
          labelBackgroundColor: "hsl(217, 91%, 60%)",
        },
        horzLine: {
          color: "hsla(217, 91%, 60%, 0.5)",
          width: 1,
          style: 2,
          labelBackgroundColor: "hsl(217, 91%, 60%)",
        },
      },
      handleScale: { axisPressedMouseMove: { time: true, price: false } },
    });

    chartRef.current = chart;

    const observer = new ResizeObserver(([entry]) => {
      chart.applyOptions({ width: entry.contentRect.width });
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  // A series-type change requires REPLACING the series, not just its data.
  React.useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (seriesRef.current) {
      chart.removeSeries(seriesRef.current);
      seriesRef.current = null;
    }

    seriesRef.current =
      variant === "candlestick"
        ? chart.addSeries(CandlestickSeries, {
            upColor: "hsl(158, 74%, 45%)",
            downColor: "hsl(0, 84%, 63%)",
            borderVisible: false,
            wickUpColor: "hsla(158, 74%, 45%, 0.65)",
            wickDownColor: "hsla(0, 84%, 63%, 0.65)",
            priceFormat: { type: "price", precision: 2, minMove: 0.01 },
          })
        : chart.addSeries(AreaSeries, {
            lineColor: "hsl(217, 91%, 60%)",
            topColor: "hsla(217, 91%, 60%, 0.28)",
            bottomColor: "hsla(217, 91%, 60%, 0.01)",
            lineWidth: 2,
            priceFormat: { type: "price", precision: 2, minMove: 0.01 },
          });
  }, [variant]);

  React.useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart || !bars.length) return;

    // Lightweight Charts requires strictly ascending, de-duplicated timestamps and
    // throws on violation. The API returns ascending bars, but a defensive sort +
    // dedupe here means a future data source cannot crash the chart.
    const sorted = [...bars].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );

    const seen = new Set<number>();
    const unique: { time: UTCTimestamp; bar: PriceBar }[] = [];
    for (const bar of sorted) {
      const time = Math.floor(new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp;
      if (seen.has(time)) continue;
      seen.add(time);
      unique.push({ time, bar });
    }

    // Branch on the SERIES ref rather than on `variant`, so TypeScript narrows the
    // series type and each setData call receives its own correctly-typed shape.
    if (isCandlestickSeries(series)) {
      series.setData(
        unique.map(({ time, bar }) => ({
          time,
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
        })),
      );
    } else {
      series.setData(unique.map(({ time, bar }) => ({ time, value: bar.close })));
    }

    chart.timeScale().fitContent();
  }, [bars, variant]);

  if (!bars.length) {
    return (
      <div className="flex items-center justify-center text-xs text-ink-faint" style={{ height }}>
        No price history available
      </div>
    );
  }

  return (
    <div className="relative">
      <div ref={containerRef} style={{ height }} />
      <span className="pointer-events-none absolute left-1 top-1 text-2xs text-ink-faint">
        {currencySymbol}
      </span>
    </div>
  );
}
