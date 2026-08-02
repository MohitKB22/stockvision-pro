"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";

import { SIGNAL_META } from "@/lib/constants";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SignalResponse } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Tooltip } from "@/components/ui/misc";
import { SkeletonTable } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/states";

/**
 * "Top AI Signals" panel.
 *
 * Each row shows the action, the model's confidence AND the risk score, because an
 * 88%-confidence BUY on a high-risk name is a materially different recommendation
 * from an 88%-confidence BUY on a low-risk one — showing confidence alone would
 * overstate the signal.
 */
export function SignalPanel({
  signals,
  isLoading,
  onGenerate,
  isGenerating,
  compact = false,
}: {
  signals: SignalResponse[];
  isLoading: boolean;
  onGenerate?: () => void;
  isGenerating?: boolean;
  compact?: boolean;
}) {
  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-1.5">
            <Sparkles className="size-3.5 text-accent" aria-hidden />
            Top AI Signals
          </CardTitle>
          <p className="mt-0.5 text-2xs text-ink-faint">
            Technical indicators blended with the trained model&apos;s probability
          </p>
        </div>
        {onGenerate ? (
          <Button variant="ghost" size="xs" onClick={onGenerate} loading={isGenerating}>
            Refresh
          </Button>
        ) : null}
      </CardHeader>

      <CardContent className="flex-1">
        {isLoading ? (
          <SkeletonTable rows={5} columns={4} />
        ) : !signals.length ? (
          <EmptyState
            icon={Sparkles}
            title="No signals generated yet"
            description="Generate signals to see BUY/SELL/HOLD calls with confidence and risk scoring."
            action={
              onGenerate ? (
                <Button variant="primary" size="sm" onClick={onGenerate} loading={isGenerating}>
                  Generate signals
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="space-y-1">
            {signals.map((signal) => {
              const meta = SIGNAL_META[signal.action];
              return (
                <li key={signal.id}>
                  <Link
                    href={`/stocks/${signal.stock_symbol}`}
                    className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-elevated"
                  >
                    <span
                      className={cn(
                        "grid size-8 shrink-0 place-items-center rounded-lg border text-2xs font-bold",
                        meta.tone === "gain"
                          ? "bg-gain/12 border-gain/30 text-gain"
                          : meta.tone === "loss"
                            ? "bg-loss/12 border-loss/30 text-loss"
                            : "border-line-strong bg-elevated text-ink-subtle",
                      )}
                      aria-hidden
                    >
                      {signal.stock_symbol.slice(0, 2)}
                    </span>

                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-ink">
                          {signal.stock_symbol}
                        </span>
                        <Badge
                          variant={
                            meta.tone === "gain"
                              ? "gain"
                              : meta.tone === "loss"
                                ? "loss"
                                : "default"
                          }
                        >
                          {meta.label}
                        </Badge>
                      </span>
                      {!compact ? (
                        <span className="mt-1 flex items-center gap-2">
                          <Progress
                            value={signal.confidence * 100}
                            className="h-1 w-16"
                            indicatorClassName={
                              meta.tone === "gain"
                                ? "bg-gain"
                                : meta.tone === "loss"
                                  ? "bg-loss"
                                  : "bg-ink-subtle"
                            }
                          />
                          <span className="tabular text-2xs text-ink-faint">
                            {formatPercent(signal.confidence, { signed: false, decimals: 0 })} conf
                          </span>
                        </span>
                      ) : null}
                    </span>

                    <Tooltip content={`Risk score ${signal.risk_score.toFixed(2)} of 1.00`}>
                      <span
                        className={cn(
                          "tabular shrink-0 rounded-md px-1.5 py-0.5 text-2xs font-medium",
                          signal.risk_score < 0.34
                            ? "bg-gain/12 text-gain"
                            : signal.risk_score < 0.67
                              ? "bg-warn/12 text-warn"
                              : "bg-loss/12 text-loss",
                        )}
                      >
                        {signal.risk_score < 0.34
                          ? "LOW"
                          : signal.risk_score < 0.67
                            ? "MED"
                            : "HIGH"}
                      </span>
                    </Tooltip>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
