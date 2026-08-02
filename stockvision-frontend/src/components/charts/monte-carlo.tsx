"use client";

import * as React from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MonteCarloResult } from "@/types";

import { AXIS_STYLE, ChartFrame, ChartTooltipShell, GRID_STYLE } from "./primitives";

/**
 * Monte Carlo fan chart.
 *
 * Renders the percentile BANDS (5-95 and 25-75) rather than a spaghetti plot of
 * every path. A thousand overplotted lines convey density poorly and cost a
 * thousand SVG paths; two stacked bands plus the median convey the same
 * distribution far more legibly.
 *
 * Recharts has no native band primitive, so each band is drawn as a stacked pair:
 * an invisible baseline Area up to the lower bound, then a visible Area of height
 * (upper - lower) stacked on top.
 */
export function MonteCarloFan({
  result,
  height = 300,
  valueFormatter,
}: {
  result: MonteCarloResult;
  height?: number;
  valueFormatter?: (value: number) => string;
}) {
  const format = valueFormatter ?? ((value: number) => value.toFixed(0));

  const data = React.useMemo(() => {
    const { p5 = [], p25 = [], p50 = [], p75 = [], p95 = [] } = result.percentiles ?? {};
    return p50.map((median, index) => ({
      day: index,
      p5: p5[index] ?? median,
      innerBase: p25[index] ?? median,
      innerBand: (p75[index] ?? median) - (p25[index] ?? median),
      outerBand: (p95[index] ?? median) - (p5[index] ?? median),
      median,
    }));
  }, [result]);

  if (!data.length) {
    return (
      <ChartFrame height={height}>
        <div className="flex h-full items-center justify-center text-xs text-ink-faint">
          Not enough return history to run a simulation
        </div>
      </ChartFrame>
    );
  }

  return (
    <ChartFrame height={height}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID_STYLE} />
          <XAxis
            dataKey="day"
            {...AXIS_STYLE}
            tickFormatter={(day: number) => (day === 0 ? "Today" : `D${day}`)}
            minTickGap={40}
          />
          <YAxis {...AXIS_STYLE} width={64} domain={["auto", "auto"]} tickFormatter={format} />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const point = payload[0].payload as (typeof data)[number];
              return (
                <ChartTooltipShell
                  title={label === 0 ? "Today" : `Day ${label}`}
                  rows={[
                    {
                      label: "95th percentile",
                      value: format(point.p5 + point.outerBand),
                      color: "hsl(var(--gain))",
                    },
                    { label: "Median", value: format(point.median), color: "hsl(var(--primary))" },
                    { label: "5th percentile", value: format(point.p5), color: "hsl(var(--loss))" },
                  ]}
                />
              );
            }}
          />
          <Area
            dataKey="p5"
            stackId="outer"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
          />
          <Area
            dataKey="outerBand"
            stackId="outer"
            stroke="none"
            fill="hsl(var(--primary))"
            fillOpacity={0.12}
            animationDuration={700}
          />
          <Area
            dataKey="innerBase"
            stackId="inner"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
          />
          <Area
            dataKey="innerBand"
            stackId="inner"
            stroke="none"
            fill="hsl(var(--primary))"
            fillOpacity={0.22}
            animationDuration={700}
          />
          <Line
            dataKey="median"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={false}
            animationDuration={700}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** Return-distribution histogram with the VaR tail highlighted. */
export function ReturnHistogram({
  returns,
  varThreshold,
  height = 220,
  bins = 40,
}: {
  returns: number[];
  varThreshold: number;
  height?: number;
  bins?: number;
}) {
  const data = React.useMemo(() => {
    if (returns.length < 2) return [];
    const min = Math.min(...returns);
    const max = Math.max(...returns);
    const width = (max - min) / bins || 1;
    const counts = new Array(bins).fill(0);
    for (const value of returns) {
      counts[Math.min(Math.floor((value - min) / width), bins - 1)] += 1;
    }
    return counts.map((count, index) => ({
      bucket: min + index * width,
      count,
      // Colour the tail beyond VaR differently — the point of the chart is showing
      // which part of the distribution the risk number actually describes.
      inTail: min + index * width <= -varThreshold,
    }));
  }, [returns, bins, varThreshold]);

  if (!data.length) {
    return (
      <ChartFrame height={height}>
        <div className="flex h-full items-center justify-center text-xs text-ink-faint">
          Not enough observations
        </div>
      </ChartFrame>
    );
  }

  const maxCount = Math.max(...data.map((d) => d.count));

  return (
    <ChartFrame height={height}>
      <div className="flex h-full items-end gap-px">
        {data.map((bucket, index) => (
          <div
            key={index}
            className="flex-1 rounded-t-sm transition-all duration-500 ease-smooth"
            style={{
              height: `${(bucket.count / maxCount) * 100}%`,
              backgroundColor: bucket.inTail
                ? "hsl(var(--loss) / 0.75)"
                : "hsl(var(--primary) / 0.45)",
              minHeight: bucket.count > 0 ? 2 : 0,
            }}
            title={`${(bucket.bucket * 100).toFixed(2)}% — ${bucket.count} sessions`}
          />
        ))}
      </div>
    </ChartFrame>
  );
}
