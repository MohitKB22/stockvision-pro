"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { Bell, BellRing, Plus, Star, Trash2 } from "lucide-react";

import { useMarket } from "@/context/market-context";
import { useAddToWatchlist, useRemoveFromWatchlist, useWatchlist } from "@/hooks/use-platform";
import { useStocks } from "@/hooks/use-stocks";
import {
  formatCompactCurrency,
  formatNumber,
  formatPercent,
  formatVolume,
  toneClass,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { WatchlistItem } from "@/types";
import { Sparkline } from "@/components/charts/sparkline";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/misc";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonTable } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

export default function WatchlistPage() {
  const router = useRouter();
  const { grouping, currencySymbol } = useMarket();
  const watchlistQuery = useWatchlist();
  const watchlistId = watchlistQuery.data?.id;
  const removeSymbol = useRemoveFromWatchlist(watchlistId);

  const triggered = React.useMemo(
    () => (watchlistQuery.data?.items ?? []).filter((item) => item.alert_triggered),
    [watchlistQuery.data],
  );

  const columns = React.useMemo<ColumnDef<WatchlistItem>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Symbol",
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-2">
            {row.original.alert_triggered ? (
              <Tooltip content="Price alert triggered">
                <BellRing className="size-3.5 shrink-0 text-warn" aria-hidden />
              </Tooltip>
            ) : null}
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-ink">{row.original.symbol}</p>
              <p className="truncate text-2xs text-ink-faint">{row.original.name}</p>
            </div>
          </div>
        ),
      },
      {
        id: "last_price",
        header: "LTP",
        accessorFn: (row) => row.quote?.last_price ?? 0,
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">
            {row.original.quote ? formatNumber(row.original.quote.last_price, { grouping }) : "—"}
          </span>
        ),
      },
      {
        id: "change_pct",
        header: "% Change",
        accessorFn: (row) => row.quote?.change_pct ?? 0,
        cell: ({ row }) => (
          <span
            className={cn("tabular text-xs font-medium", toneClass(row.original.quote?.change_pct))}
          >
            {row.original.quote ? formatPercent(row.original.quote.change_pct) : "—"}
          </span>
        ),
      },
      {
        id: "volume",
        header: "Volume",
        accessorFn: (row) => row.quote?.volume ?? 0,
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink-muted">
            {row.original.quote ? formatVolume(row.original.quote.volume, grouping) : "—"}
          </span>
        ),
      },
      {
        id: "range",
        header: "52W Position",
        enableSorting: false,
        cell: ({ row }) => {
          const quote = row.original.quote;
          if (!quote) return <span className="text-2xs text-ink-faint">—</span>;
          const span = quote.week_52_high - quote.week_52_low;
          const position = span > 0 ? (quote.last_price - quote.week_52_low) / span : 0.5;
          return (
            <div className="w-24">
              <div className="relative h-1 rounded-full bg-line">
                <div
                  className="absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-2 ring-canvas"
                  style={{ left: `${Math.min(Math.max(position, 0), 1) * 100}%` }}
                />
              </div>
            </div>
          );
        },
      },
      {
        id: "alerts",
        header: "Alerts",
        enableSorting: false,
        cell: ({ row }) => {
          const { alert_above, alert_below } = row.original;
          if (!alert_above && !alert_below)
            return <span className="text-2xs text-ink-faint">None</span>;
          return (
            <div className="flex flex-col gap-0.5 text-2xs">
              {alert_above ? (
                <span className="tabular text-gain">
                  ↑ {formatNumber(alert_above, { grouping, decimals: 0 })}
                </span>
              ) : null}
              {alert_below ? (
                <span className="tabular text-loss">
                  ↓ {formatNumber(alert_below, { grouping, decimals: 0 })}
                </span>
              ) : null}
            </div>
          );
        },
      },
      {
        id: "trend",
        header: "Trend",
        enableSorting: false,
        cell: ({ row }) =>
          row.original.quote?.sparkline.length ? (
            <Sparkline data={row.original.quote.sparkline} width={72} height={24} fill={false} />
          ) : null,
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${row.original.symbol}`}
            onClick={(event) => {
              // Stop the row's navigation handler — clicking delete should not also
              // open the stock page behind the removal.
              event.stopPropagation();
              removeSymbol.mutate(row.original.symbol);
            }}
          >
            <Trash2 aria-hidden />
          </Button>
        ),
      },
    ],
    [grouping, removeSymbol],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Watchlist"
        description={
          watchlistQuery.data
            ? `${watchlistQuery.data.name} · ${watchlistQuery.data.item_count} symbols tracked`
            : "Tracked symbols with live quotes and price alerts"
        }
        actions={watchlistId ? <AddSymbolDialog watchlistId={watchlistId} /> : null}
      />

      {triggered.length ? (
        <div className="bg-warn/8 flex flex-wrap items-center gap-2 rounded-xl border border-warn/25 px-4 py-3">
          <Bell className="size-4 shrink-0 text-warn" aria-hidden />
          <p className="text-xs text-warn">
            {triggered.length} alert{triggered.length === 1 ? "" : "s"} triggered:
          </p>
          {triggered.map((item) => (
            <Badge key={item.id} variant="warn">
              {item.symbol} @ {formatNumber(item.quote?.last_price, { grouping })}
            </Badge>
          ))}
        </div>
      ) : null}

      <Card>
        <CardContent className="pt-5">
          {watchlistQuery.isLoading ? (
            <SkeletonTable rows={8} columns={7} />
          ) : watchlistQuery.isError ? (
            <ErrorState error={watchlistQuery.error} onRetry={() => watchlistQuery.refetch()} />
          ) : !watchlistQuery.data?.items.length ? (
            <EmptyState
              icon={Star}
              title="Your watchlist is empty"
              description="Add symbols to track live prices, 52-week position and set price alerts."
              action={watchlistId ? <AddSymbolDialog watchlistId={watchlistId} /> : undefined}
            />
          ) : (
            <DataTable
              columns={columns}
              data={watchlistQuery.data.items}
              onRowClick={(row) => router.push(`/stocks/${row.symbol}`)}
              pageSize={20}
            />
          )}
        </CardContent>
      </Card>

      {watchlistQuery.data?.items.length ? (
        <p className="text-2xs text-ink-faint">
          Combined market capitalisation of tracked symbols:{" "}
          {formatCompactCurrency(
            watchlistQuery.data.items.reduce((sum, item) => sum + (item.quote?.market_cap ?? 0), 0),
            { symbol: currencySymbol, grouping },
          )}
          .
        </p>
      ) : null}
    </div>
  );
}

function AddSymbolDialog({ watchlistId }: { watchlistId: string }) {
  const [open, setOpen] = React.useState(false);
  const [symbol, setSymbol] = React.useState("");
  const [above, setAbove] = React.useState("");
  const [below, setBelow] = React.useState("");

  const stocksQuery = useStocks();
  const addSymbol = useAddToWatchlist(watchlistId);
  const { currencySymbol } = useMarket();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!symbol) return;
    await addSymbol.mutateAsync({
      symbol,
      alert_above: above ? Number(above) : undefined,
      alert_below: below ? Number(below) : undefined,
    });
    setSymbol("");
    setAbove("");
    setBelow("");
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="primary" size="sm">
          <Plus aria-hidden /> Add symbol
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add to watchlist</DialogTitle>
          <DialogDescription>
            Price alerts are evaluated against the latest quote each time the watchlist loads.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label htmlFor="watch-symbol">Symbol</Label>
            <Select value={symbol} onValueChange={setSymbol}>
              <SelectTrigger id="watch-symbol" className="mt-1">
                <SelectValue placeholder="Select a stock" />
              </SelectTrigger>
              <SelectContent>
                {(stocksQuery.data ?? []).map((stock) => (
                  <SelectItem key={stock.id} value={stock.symbol}>
                    {stock.symbol} — {stock.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="alert-above">Alert above ({currencySymbol})</Label>
              <Input
                id="alert-above"
                type="number"
                step="any"
                min="0"
                className="mt-1"
                placeholder="Optional"
                value={above}
                onChange={(event) => setAbove(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="alert-below">Alert below ({currencySymbol})</Label>
              <Input
                id="alert-below"
                type="number"
                step="any"
                min="0"
                className="mt-1"
                placeholder="Optional"
                value={below}
                onChange={(event) => setBelow(event.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!symbol}
              loading={addSymbol.isPending}
            >
              Add to watchlist
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
