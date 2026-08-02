"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { toneFor } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/charts/sparkline";
import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/misc";

/**
 * The KPI tile used across the dashboard, portfolio and admin pages.
 *
 * The direction arrow is not decorative: it is what makes gain/loss readable
 * without relying on colour alone, which matters for the ~8% of users with a
 * red/green colour-vision deficiency.
 */
export function StatCard({
  label,
  value,
  change,
  changeLabel,
  hint,
  sparkline,
  icon: Icon,
  tone,
  accent,
  onClick,
  className,
}: {
  label: string;
  value: string;
  change?: number | null;
  changeLabel?: string;
  hint?: string;
  sparkline?: number[];
  icon?: React.ElementType;
  tone?: "gain" | "loss" | "flat";
  accent?: "primary" | "accent" | "gain" | "loss" | "warn";
  onClick?: () => void;
  className?: string;
}) {
  const resolvedTone = tone ?? toneFor(change);
  const showChange = change !== undefined && change !== null && Number.isFinite(change);
  const Arrow = resolvedTone === "loss" ? ArrowDownRight : ArrowUpRight;

  const accentRing =
    accent === "accent"
      ? "border-accent/25 bg-accent/12 text-accent"
      : accent === "gain"
        ? "border-gain/25 bg-gain/12 text-gain"
        : accent === "loss"
          ? "border-loss/25 bg-loss/12 text-loss"
          : accent === "warn"
            ? "border-warn/25 bg-warn/12 text-warn"
            : "border-primary/25 bg-primary/12 text-primary";

  return (
    <Card
      interactive={Boolean(onClick)}
      onClick={onClick}
      className={cn("relative overflow-hidden p-5", className)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="stat-label truncate">{label}</p>
          <p className="stat-value mt-2 truncate">{value}</p>
        </div>
        {Icon ? (
          <span
            className={cn("grid size-8 shrink-0 place-items-center rounded-lg border", accentRing)}
          >
            <Icon className="size-4" aria-hidden />
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          {showChange ? (
            <span
              className={cn(
                "tabular inline-flex items-center gap-0.5 text-xs font-medium",
                resolvedTone === "gain"
                  ? "text-gain"
                  : resolvedTone === "loss"
                    ? "text-loss"
                    : "text-ink-muted",
              )}
            >
              {resolvedTone !== "flat" ? <Arrow className="size-3.5" aria-hidden /> : null}
              {changeLabel ?? `${(change * 100).toFixed(2)}%`}
            </span>
          ) : changeLabel ? (
            <span className="text-xs text-ink-muted">{changeLabel}</span>
          ) : null}
          {hint ? (
            <Tooltip content={hint}>
              <p className="mt-0.5 cursor-default truncate text-2xs text-ink-faint">{hint}</p>
            </Tooltip>
          ) : null}
        </div>

        {sparkline && sparkline.length > 1 ? (
          <Sparkline
            data={sparkline}
            width={84}
            height={26}
            tone={resolvedTone === "flat" ? "neutral" : resolvedTone}
          />
        ) : null}
      </div>
    </Card>
  );
}
