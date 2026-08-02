"use client";

import * as React from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { CHART_PALETTE } from "@/lib/constants";

import { ChartFrame, ChartTooltipShell } from "./primitives";

export interface DonutSlice {
  label: string;
  value: number;
  weight_pct: number;
}

/** Allocation donut with a centred total. Slices under 2% are merged into "Other"
 *  — a 0.3% sliver is unreadable and unlabellable, and a legend full of them
 *  buries the allocations that actually matter. */
export function DonutChart({
  data,
  height = 200,
  centerLabel,
  centerValue,
  valueFormatter,
}: {
  data: DonutSlice[];
  height?: number;
  centerLabel?: string;
  centerValue?: string;
  valueFormatter?: (value: number) => string;
}) {
  const slices = React.useMemo(() => {
    const significant = data.filter((slice) => slice.weight_pct >= 0.02);
    const rest = data.filter((slice) => slice.weight_pct < 0.02);
    if (!rest.length) return significant;
    return [
      ...significant,
      {
        label: "Other",
        value: rest.reduce((sum, slice) => sum + slice.value, 0),
        weight_pct: rest.reduce((sum, slice) => sum + slice.weight_pct, 0),
      },
    ];
  }, [data]);

  const format = valueFormatter ?? ((value: number) => value.toFixed(2));

  if (!slices.length) {
    return (
      <ChartFrame height={height}>
        <div className="flex h-full items-center justify-center text-xs text-ink-faint">
          Nothing allocated yet
        </div>
      </ChartFrame>
    );
  }

  return (
    <div className="relative">
      <ChartFrame height={height}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="label"
              innerRadius="62%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="hsl(var(--canvas))"
              strokeWidth={2}
              animationDuration={700}
            >
              {slices.map((slice, index) => (
                <Cell key={slice.label} fill={CHART_PALETTE[index % CHART_PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const slice = payload[0].payload as DonutSlice;
                return (
                  <ChartTooltipShell
                    title={slice.label}
                    rows={[
                      { label: "Value", value: format(slice.value) },
                      { label: "Weight", value: `${(slice.weight_pct * 100).toFixed(2)}%` },
                    ]}
                  />
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </ChartFrame>
      {centerValue ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="tabular text-lg font-semibold text-ink">{centerValue}</span>
          {centerLabel ? <span className="text-2xs text-ink-faint">{centerLabel}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

export function DonutLegend({
  data,
  valueFormatter,
}: {
  data: DonutSlice[];
  valueFormatter?: (value: number) => string;
}) {
  const format = valueFormatter ?? ((value: number) => value.toFixed(2));
  return (
    <ul className="space-y-1.5">
      {data.slice(0, 6).map((slice, index) => (
        <li key={slice.label} className="flex items-center justify-between gap-3 text-xs">
          <span className="flex min-w-0 items-center gap-2">
            <span
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: CHART_PALETTE[index % CHART_PALETTE.length] }}
              aria-hidden
            />
            <span className="truncate text-ink-muted">{slice.label}</span>
          </span>
          <span className="flex shrink-0 items-baseline gap-2">
            <span className="tabular text-ink">{(slice.weight_pct * 100).toFixed(1)}%</span>
            <span className="tabular text-2xs text-ink-faint">{format(slice.value)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
