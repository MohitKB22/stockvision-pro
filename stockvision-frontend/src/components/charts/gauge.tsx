"use client";

import { clamp, cn } from "@/lib/utils";

/**
 * Radial gauge for a 0..1 score (prediction confidence, model accuracy).
 *
 * SVG rather than a chart library: it is one arc, and pulling in a charting
 * runtime for a single stroke-dasharray animation is not a trade worth making.
 */
export function Gauge({
  value,
  size = 84,
  strokeWidth = 7,
  label,
  tone = "auto",
  className,
}: {
  value: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  tone?: "auto" | "primary" | "gain" | "loss" | "warn";
  className?: string;
}) {
  const safeValue = clamp(value, 0, 1);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  // 75% of the circle, leaving a gap at the bottom — a full ring reads as a
  // loading spinner, an open arc reads as a measurement.
  const arc = circumference * 0.75;
  const offset = arc * (1 - safeValue);

  const color =
    tone === "primary"
      ? "hsl(var(--primary))"
      : tone === "gain"
        ? "hsl(var(--gain))"
        : tone === "loss"
          ? "hsl(var(--loss))"
          : tone === "warn"
            ? "hsl(var(--warn))"
            : safeValue >= 0.66
              ? "hsl(var(--gain))"
              : safeValue >= 0.4
                ? "hsl(var(--warn))"
                : "hsl(var(--loss))";

  return (
    <div
      className={cn("relative inline-grid place-items-center", className)}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        className="-rotate-[225deg]"
        role="img"
        aria-label={`${label ?? "Score"}: ${(safeValue * 100).toFixed(0)} percent`}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="hsl(var(--line))"
          strokeWidth={strokeWidth}
          strokeDasharray={`${arc} ${circumference}`}
          strokeLinecap="round"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${arc} ${circumference}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="tabular text-sm font-semibold text-ink">
          {(safeValue * 100).toFixed(0)}%
        </span>
        {label ? <span className="text-2xs text-ink-faint">{label}</span> : null}
      </div>
    </div>
  );
}
