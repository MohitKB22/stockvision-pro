"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A hand-rolled SVG sparkline.
 *
 * Deliberately NOT a Recharts chart: these render 40+ at a time (every watchlist
 * row, every mover, every index tile). Recharts mounts a ResponsiveContainer with
 * a ResizeObserver per instance, and at that count it is a measurable
 * scroll-jank source. This is a single path element with no observers, no state
 * and no layout effects.
 */
export function Sparkline({
  data,
  className,
  width = 96,
  height = 28,
  strokeWidth = 1.5,
  tone,
  fill = true,
}: {
  data: number[];
  className?: string;
  width?: number;
  height?: number;
  strokeWidth?: number;
  tone?: "gain" | "loss" | "neutral";
  fill?: boolean;
}) {
  const gradientId = React.useId();

  const { linePath, areaPath, resolvedTone } = React.useMemo(() => {
    if (!data || data.length < 2) {
      return { linePath: "", areaPath: "", resolvedTone: "neutral" as const };
    }
    const min = Math.min(...data);
    const max = Math.max(...data);
    // A flat series has zero span; dividing by it yields NaN coordinates and an
    // invisible path. Fall back to a mid-height line.
    const span = max - min || 1;
    const stepX = width / (data.length - 1);

    const points = data.map((value, index) => {
      const x = index * stepX;
      const y = height - ((value - min) / span) * (height - strokeWidth * 2) - strokeWidth;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });

    const direction = data[data.length - 1] >= data[0] ? "gain" : "loss";
    return {
      linePath: `M ${points.join(" L ")}`,
      areaPath: `M ${points.join(" L ")} L ${width},${height} L 0,${height} Z`,
      resolvedTone: (tone ?? direction) as "gain" | "loss" | "neutral",
    };
  }, [data, width, height, strokeWidth, tone]);

  if (!linePath) {
    return (
      <div
        className={cn("rounded bg-elevated/50", className)}
        style={{ width, height }}
        aria-hidden
      />
    );
  }

  const color =
    resolvedTone === "gain"
      ? "hsl(var(--gain))"
      : resolvedTone === "loss"
        ? "hsl(var(--loss))"
        : "hsl(var(--ink-subtle))";

  return (
    <svg
      className={cn("overflow-visible", className)}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Trend ${resolvedTone === "gain" ? "upward" : resolvedTone === "loss" ? "downward" : "flat"}`}
    >
      {fill ? (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.25} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={areaPath} fill={`url(#${gradientId})`} />
        </>
      ) : null}
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
