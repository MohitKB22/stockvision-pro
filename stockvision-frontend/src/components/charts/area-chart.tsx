"use client";

import * as React from "react";
import {
  Area,
  AreaChart as RechartsAreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_STYLE, ChartFrame, ChartTooltipShell, GRID_STYLE } from "./primitives";

export interface AreaSeriesPoint {
  label: string;
  value: number;
}

/**
 * The workhorse time-series chart (portfolio value, index level, drawdown).
 *
 * `tone="auto"` derives the colour from the first-to-last direction of the series,
 * so a chart of a losing position is red without the caller having to compute
 * that — one less place for the colour to disagree with the number printed above.
 */
export function TimeSeriesChart({
  data,
  height = 240,
  tone = "auto",
  valueFormatter,
  labelFormatter,
  variant = "area",
  showGrid = true,
  showAxis = true,
  referenceValue,
}: {
  data: AreaSeriesPoint[];
  height?: number;
  tone?: "auto" | "gain" | "loss" | "primary";
  valueFormatter?: (value: number) => string;
  labelFormatter?: (label: string) => string;
  variant?: "area" | "line";
  showGrid?: boolean;
  showAxis?: boolean;
  referenceValue?: number;
}) {
  const gradientId = React.useId();

  const color = React.useMemo(() => {
    if (tone === "primary") return "hsl(var(--primary))";
    if (tone === "gain") return "hsl(var(--gain))";
    if (tone === "loss") return "hsl(var(--loss))";
    if (data.length < 2) return "hsl(var(--primary))";
    return data[data.length - 1].value >= data[0].value ? "hsl(var(--gain))" : "hsl(var(--loss))";
  }, [tone, data]);

  const format = valueFormatter ?? ((value: number) => value.toFixed(2));

  // Recharts renders nothing (not an error, just empty space) for an empty
  // dataset, which looks like a broken chart. Callers should gate on this, but
  // guarding here means it can never happen.
  if (!data.length) {
    return (
      <ChartFrame height={height}>
        <div className="flex h-full items-center justify-center text-xs text-ink-faint">
          No data for this period
        </div>
      </ChartFrame>
    );
  }

  const Chart = variant === "area" ? RechartsAreaChart : LineChart;

  return (
    <ChartFrame height={height}>
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          {showGrid ? <CartesianGrid {...GRID_STYLE} /> : null}
          {showAxis ? (
            <>
              <XAxis dataKey="label" {...AXIS_STYLE} minTickGap={32} />
              <YAxis
                {...AXIS_STYLE}
                width={56}
                domain={["auto", "auto"]}
                tickFormatter={(value: number) => format(value)}
              />
            </>
          ) : null}
          <Tooltip
            cursor={{ stroke: "hsl(var(--line-strong))", strokeWidth: 1 }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              return (
                <ChartTooltipShell
                  title={labelFormatter ? labelFormatter(String(label)) : String(label)}
                  rows={[{ label: "Value", value: format(Number(payload[0].value)), color }]}
                />
              );
            }}
          />
          {referenceValue !== undefined ? (
            <Line
              type="monotone"
              dataKey={() => referenceValue}
              stroke="hsl(var(--ink-faint))"
              strokeDasharray="4 4"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
          ) : null}
          {variant === "area" ? (
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              animationDuration={700}
              dot={false}
              activeDot={{ r: 3.5, strokeWidth: 2, stroke: "hsl(var(--canvas))" }}
            />
          ) : (
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={false}
              animationDuration={700}
              activeDot={{ r: 3.5, strokeWidth: 2, stroke: "hsl(var(--canvas))" }}
            />
          )}
        </Chart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
