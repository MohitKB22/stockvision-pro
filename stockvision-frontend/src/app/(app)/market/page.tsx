"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, Layers, TrendingDown, TrendingUp } from "lucide-react";

import { useMarket } from "@/context/market-context";
import {
  useBreadth,
  useHeatmap,
  useIndices,
  useMovers,
  useSectors,
  useWeekRange,
} from "@/hooks/use-market-data";
import { formatCompactCurrency, formatNumber, formatPercent, toneClass } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { MoverQuote, SectorPerformance, WeekRangeEntry } from "@/types";
import { SectorHeatmap } from "@/components/charts/heatmap";
import { Sparkline } from "@/components/charts/sparkline";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Progress } from "@/components/ui/misc";
import { SkeletonChart, SkeletonTable } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";

export default function MarketPage() {
  const router = useRouter();
  const { grouping, currencySymbol, definition } = useMarket();

  const indicesQuery = useIndices();
  const moversQuery = useMovers(15);
  const sectorsQuery = useSectors();
  const heatmapQuery = useHeatmap();
  const breadthQuery = useBreadth();
  const weekRangeQuery = useWeekRange(10);

  const moverColumns = React.useMemo<ColumnDef<MoverQuote>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Symbol",
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-ink">{row.original.symbol}</p>
            <p className="truncate text-2xs text-ink-faint">{row.original.name}</p>
          </div>
        ),
      },
      {
        accessorKey: "sector",
        header: "Sector",
        cell: ({ row }) => (
          <span className="text-xs text-ink-subtle">{row.original.sector ?? "—"}</span>
        ),
      },
      {
        accessorKey: "last_price",
        header: "LTP",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">
            {formatNumber(row.original.last_price, { grouping })}
          </span>
        ),
      },
      {
        accessorKey: "change",
        header: "Change",
        cell: ({ row }) => (
          <span className={cn("tabular text-xs", toneClass(row.original.change))}>
            {formatNumber(row.original.change, { grouping })}
          </span>
        ),
      },
      {
        accessorKey: "change_pct",
        header: "% Change",
        cell: ({ row }) => (
          <span className={cn("tabular text-xs font-medium", toneClass(row.original.change_pct))}>
            {formatPercent(row.original.change_pct)}
          </span>
        ),
      },
      {
        accessorKey: "turnover",
        header: "Turnover",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink-muted">
            {formatCompactCurrency(row.original.turnover, { symbol: currencySymbol, grouping })}
          </span>
        ),
      },
      {
        id: "trend",
        header: "Trend",
        enableSorting: false,
        cell: ({ row }) => (
          <Sparkline data={row.original.sparkline} width={64} height={22} fill={false} />
        ),
      },
    ],
    [grouping, currencySymbol],
  );

  const rangeColumns = React.useMemo<ColumnDef<WeekRangeEntry>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Symbol",
        cell: ({ row }) => (
          <span className="text-xs font-medium text-ink">{row.original.symbol}</span>
        ),
      },
      {
        accessorKey: "last_price",
        header: "LTP",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">
            {formatNumber(row.original.last_price, { grouping })}
          </span>
        ),
      },
      {
        id: "range",
        header: "52-Week Range",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="w-40">
            <div className="relative h-1.5 rounded-full bg-line">
              <div
                className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-2 ring-canvas"
                style={{
                  left: `${Math.min(Math.max(row.original.position_in_range, 0), 1) * 100}%`,
                }}
              />
            </div>
            <div className="tabular mt-1 flex justify-between text-2xs text-ink-faint">
              <span>{formatNumber(row.original.week_52_low, { grouping, decimals: 0 })}</span>
              <span>{formatNumber(row.original.week_52_high, { grouping, decimals: 0 })}</span>
            </div>
          </div>
        ),
      },
      {
        accessorKey: "pct_from_high",
        header: "From High",
        cell: ({ row }) => (
          <span className={cn("tabular text-xs", toneClass(row.original.pct_from_high))}>
            {formatPercent(row.original.pct_from_high)}
          </span>
        ),
      },
    ],
    [grouping],
  );

  const breadth = breadthQuery.data;
  const advancerShare = breadth && breadth.total ? breadth.advancers / breadth.total : 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Market Overview"
        description={`${definition?.name ?? ""} · ${definition?.exchange ?? ""} · computed from stored price history`}
      />

      {/* --- Indices --- */}
      <section aria-label="Indices">
        {indicesQuery.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonChart key={index} className="h-[132px]" />
            ))}
          </div>
        ) : indicesQuery.isError ? (
          <ErrorState error={indicesQuery.error} onRetry={() => indicesQuery.refetch()} />
        ) : !indicesQuery.data?.length ? (
          <Card>
            <CardContent className="pt-5">
              <EmptyState
                title="No indices available"
                description="Seed market data to populate indices."
              />
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {indicesQuery.data.map((index) => (
              <Card key={index.symbol} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-ink-muted">{index.name}</p>
                    <p className="tabular mt-1 text-lg font-semibold text-ink">
                      {formatNumber(index.level, { grouping })}
                    </p>
                  </div>
                  <Badge variant={index.change_pct >= 0 ? "gain" : "loss"}>
                    {formatPercent(index.change_pct)}
                  </Badge>
                </div>
                <div className="mt-2">
                  <Sparkline data={index.sparkline} width={220} height={34} className="w-full" />
                </div>
                <p className="mt-1 text-2xs text-ink-faint">
                  {index.is_synthetic ? "Synthesized from constituents" : "Index instrument"} ·{" "}
                  {index.constituent_count} members
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* --- Breadth --- */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Market Breadth</CardTitle>
            <p className="mt-0.5 text-2xs text-ink-faint">
              Advance/decline across the tracked universe
            </p>
          </div>
        </CardHeader>
        <CardContent>
          {breadthQuery.isLoading ? (
            <SkeletonTable rows={2} columns={5} />
          ) : !breadth || !breadth.total ? (
            <EmptyState
              title="No breadth data"
              description="Requires at least two sessions of prices."
            />
          ) : (
            <>
              <div className="mb-4 flex h-2 overflow-hidden rounded-full">
                <div
                  className="bg-gain"
                  style={{ width: `${(breadth.advancers / breadth.total) * 100}%` }}
                />
                <div
                  className="bg-line-strong"
                  style={{ width: `${(breadth.unchanged / breadth.total) * 100}%` }}
                />
                <div
                  className="bg-loss"
                  style={{ width: `${(breadth.decliners / breadth.total) * 100}%` }}
                />
              </div>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                <BreadthStat
                  label="Advancers"
                  value={String(breadth.advancers)}
                  tone="gain"
                  icon={ArrowUp}
                />
                <BreadthStat
                  label="Decliners"
                  value={String(breadth.decliners)}
                  tone="loss"
                  icon={ArrowDown}
                />
                <BreadthStat label="A/D Ratio" value={breadth.advance_decline_ratio.toFixed(2)} />
                <BreadthStat label="52W Highs" value={String(breadth.new_highs)} tone="gain" />
                <BreadthStat label="52W Lows" value={String(breadth.new_lows)} tone="loss" />
                <BreadthStat
                  label="Turnover"
                  value={formatCompactCurrency(breadth.total_turnover, {
                    symbol: currencySymbol,
                    grouping,
                  })}
                />
              </dl>
              <div className="mt-4">
                <div className="mb-1 flex justify-between text-2xs text-ink-faint">
                  <span>Participation</span>
                  <span className="tabular">
                    {formatPercent(advancerShare, { signed: false })} advancing
                  </span>
                </div>
                <Progress
                  value={advancerShare * 100}
                  indicatorClassName={advancerShare >= 0.5 ? "bg-gain" : "bg-loss"}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* --- Movers / sectors / heatmap / 52w --- */}
      <Tabs defaultValue="gainers">
        <TabsList className="flex-wrap">
          <TabsTrigger value="gainers">
            <TrendingUp aria-hidden /> Gainers
          </TabsTrigger>
          <TabsTrigger value="losers">
            <TrendingDown aria-hidden /> Losers
          </TabsTrigger>
          <TabsTrigger value="active">
            <Layers aria-hidden /> Most Active
          </TabsTrigger>
          <TabsTrigger value="sectors">Sectors</TabsTrigger>
          <TabsTrigger value="heatmap">Heatmap</TabsTrigger>
          <TabsTrigger value="range">52-Week</TabsTrigger>
        </TabsList>

        {(
          [
            ["gainers", "gainers", "No advancing stocks"],
            ["losers", "losers", "No declining stocks"],
            ["active", "most_active", "No trading activity"],
          ] as const
        ).map(([tab, key, empty]) => (
          <TabsContent key={tab} value={tab}>
            <Card>
              <CardContent className="pt-5">
                {moversQuery.isLoading ? (
                  <SkeletonTable />
                ) : (
                  <DataTable
                    columns={moverColumns}
                    data={moversQuery.data?.[key] ?? []}
                    emptyTitle={empty}
                    onRowClick={(row) => router.push(`/stocks/${row.symbol}`)}
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>
        ))}

        <TabsContent value="sectors">
          <Card>
            <CardContent className="pt-5">
              {sectorsQuery.isLoading ? (
                <SkeletonTable />
              ) : !sectorsQuery.data?.length ? (
                <EmptyState title="No sector data" />
              ) : (
                <SectorList sectors={sectorsQuery.data} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="heatmap">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Sector Heatmap</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  Tile area is proportional to market capitalisation; colour is session return
                </p>
              </div>
            </CardHeader>
            <CardContent>
              {heatmapQuery.isLoading ? (
                <SkeletonChart className="h-[400px]" />
              ) : (
                <SectorHeatmap
                  entries={heatmapQuery.data ?? []}
                  onSelect={(symbol) => router.push(`/stocks/${symbol}`)}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="range">
          <div className="grid gap-4 lg:grid-cols-2">
            {(
              [
                ["Near 52-Week High", "near_52_week_high"],
                ["Near 52-Week Low", "near_52_week_low"],
              ] as const
            ).map(([title, key]) => (
              <Card key={key}>
                <CardHeader>
                  <CardTitle>{title}</CardTitle>
                </CardHeader>
                <CardContent>
                  {weekRangeQuery.isLoading ? (
                    <SkeletonTable rows={5} columns={4} />
                  ) : (
                    <DataTable
                      columns={rangeColumns}
                      data={weekRangeQuery.data?.[key] ?? []}
                      emptyTitle="No data"
                      dense
                      onRowClick={(row) => router.push(`/stocks/${row.symbol}`)}
                    />
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function BreadthStat({
  label,
  value,
  tone,
  icon: Icon,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss";
  icon?: React.ElementType;
}) {
  return (
    <div>
      <dt className="stat-label">{label}</dt>
      <dd
        className={cn(
          "tabular mt-1 flex items-center gap-1 text-base font-semibold",
          tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink",
        )}
      >
        {Icon ? <Icon className="size-3.5" aria-hidden /> : null}
        {value}
      </dd>
    </div>
  );
}

function SectorList({ sectors }: { sectors: SectorPerformance[] }) {
  const { grouping, currencySymbol } = useMarket();
  const max = Math.max(...sectors.map((sector) => Math.abs(sector.change_pct)), 0.001);

  return (
    <ul className="space-y-2.5">
      {sectors.map((sector) => {
        const width = (Math.abs(sector.change_pct) / max) * 50;
        const positive = sector.change_pct >= 0;
        return (
          <li key={sector.sector}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
              <span className="truncate font-medium text-ink">{sector.sector}</span>
              <span className="flex shrink-0 items-baseline gap-3">
                <span className="text-2xs text-ink-faint">
                  {sector.advancers}↑ {sector.decliners}↓ ·{" "}
                  {formatCompactCurrency(sector.total_turnover, {
                    symbol: currencySymbol,
                    grouping,
                  })}
                </span>
                <span className={cn("tabular font-medium", toneClass(sector.change_pct))}>
                  {formatPercent(sector.change_pct)}
                </span>
              </span>
            </div>
            {/* Diverging bar anchored at the centre — a left-anchored bar makes a
                -2% sector look longer than a +1% one only by colour. */}
            <div className="relative h-2 rounded-full bg-elevated">
              <div className="absolute left-1/2 top-0 h-full w-px bg-line-strong" aria-hidden />
              <div
                className={cn(
                  "absolute top-0 h-full rounded-full transition-all duration-500 ease-smooth",
                  positive ? "left-1/2 bg-gain/70" : "right-1/2 bg-loss/70",
                )}
                style={{ width: `${width}%` }}
              />
            </div>
            <p className="mt-1 text-2xs text-ink-faint">
              Best{" "}
              <Link href={`/stocks/${sector.top_symbol}`} className="text-gain hover:underline">
                {sector.top_symbol}
              </Link>
              {" · "}
              Worst{" "}
              <Link href={`/stocks/${sector.bottom_symbol}`} className="text-loss hover:underline">
                {sector.bottom_symbol}
              </Link>
            </p>
          </li>
        );
      })}
    </ul>
  );
}
