"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Shared chart chrome.
 *
 * Recharts' default tooltip is a white box with black text — unusable on a dark
 * canvas — so every chart in the app uses `ChartTooltipShell` instead. One
 * implementation is what stops eight charts from each inventing their own
 * slightly different popover.
 */

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

export function ChartTooltipShell({
  title,
  rows,
  footer,
}: {
  title?: string;
  rows: TooltipRow[];
  footer?: React.ReactNode;
}) {
  return (
    <div className="glass-strong rounded-lg px-3 py-2 shadow-raised">
      {title ? (
        <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wider text-ink-faint">
          {title}
        </p>
      ) : null}
      <div className="space-y-1">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 text-xs">
            <span className="flex items-center gap-1.5 text-ink-subtle">
              {row.color ? (
                <span
                  className="size-2 rounded-full"
                  style={{ backgroundColor: row.color }}
                  aria-hidden
                />
              ) : null}
              {row.label}
            </span>
            <span className="tabular font-medium text-ink">{row.value}</span>
          </div>
        ))}
      </div>
      {footer ? (
        <div className="mt-1.5 border-t border-line pt-1.5 text-2xs text-ink-faint">{footer}</div>
      ) : null}
    </div>
  );
}

export const AXIS_STYLE = {
  stroke: "hsl(var(--ink-faint))",
  fontSize: 10,
  tickLine: false,
  axisLine: false,
} as const;

export const GRID_STYLE = {
  stroke: "hsl(var(--line))",
  strokeDasharray: "3 3",
  vertical: false,
} as const;

/**
 * A fixed-height chart frame.
 *
 * Recharts' ResponsiveContainer measures its parent; if the parent has no height
 * it renders at 0px and the chart silently disappears. Forcing an explicit height
 * here removes an entire category of "the chart is blank" bug.
 */
export function ChartFrame({
  height = 240,
  className,
  children,
}: {
  height?: number;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("w-full", className)} style={{ height }}>
      {children}
    </div>
  );
}
