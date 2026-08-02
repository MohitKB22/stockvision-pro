"use client";

import Link from "next/link";

import { useMarket } from "@/context/market-context";
import { formatNumber, formatPercent, toneClass } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { WatchlistItem } from "@/types";
import { Sparkline } from "@/components/charts/sparkline";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Horizontal watchlist strip along the bottom of the dashboard.
 *
 * Overflow scrolls rather than wrapping, with a fade on the trailing edge so it
 * reads as "there is more" instead of a hard clip. Scroll snapping keeps it usable
 * with a thumb on mobile.
 */
export function TickerStrip({ items, isLoading }: { items: WatchlistItem[]; isLoading: boolean }) {
  const { grouping } = useMarket();

  if (isLoading) {
    return (
      <div className="flex gap-3 overflow-hidden">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-[68px] w-40 shrink-0 rounded-xl" />
        ))}
      </div>
    );
  }

  if (!items.length) return null;

  return (
    <div className="scrollbar-none mask-fade-r flex snap-x gap-3 overflow-x-auto pb-1">
      {items.map((item) => {
        const quote = item.quote;
        return (
          <Link
            key={item.id}
            href={`/stocks/${item.symbol}`}
            className="glass group flex w-[172px] shrink-0 snap-start items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 ease-smooth hover:border-primary/40"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-semibold text-ink">{item.symbol}</span>
              <span className="tabular block truncate text-sm text-ink-muted">
                {quote ? formatNumber(quote.last_price, { grouping }) : "—"}
              </span>
              <span className={cn("tabular block text-2xs", toneClass(quote?.change_pct))}>
                {quote ? formatPercent(quote.change_pct) : "—"}
              </span>
            </span>
            {quote?.sparkline?.length ? (
              <Sparkline data={quote.sparkline} width={48} height={30} fill={false} />
            ) : null}
          </Link>
        );
      })}
    </div>
  );
}
