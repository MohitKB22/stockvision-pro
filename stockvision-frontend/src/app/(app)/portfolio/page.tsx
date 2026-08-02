"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus, Wallet } from "lucide-react";

import { useMarket } from "@/context/market-context";
import {
  useDefaultPortfolio,
  usePortfolioPerformance,
  usePortfolioSummary,
  usePortfolios,
  useTransactions,
} from "@/hooks/use-portfolio";
import { TIMEFRAMES, type TimeframeValue } from "@/lib/constants";
import {
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  toneClass,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Holding, Transaction } from "@/types";
import { TimeSeriesChart } from "@/components/charts/area-chart";
import { DonutChart, DonutLegend } from "@/components/charts/donut-chart";
import { StatCard } from "@/components/dashboard/stat-card";
import { PageHeader } from "@/components/layout/page-header";
import { CreatePortfolioDialog } from "@/components/portfolio/create-portfolio-dialog";
import { NewOrderDialog } from "@/components/portfolio/new-order-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonChart, SkeletonStatCard, SkeletonTable } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";

export default function PortfolioPage() {
  const router = useRouter();
  const { currencySymbol, grouping } = useMarket();
  const [selectedId, setSelectedId] = React.useState<string | undefined>();
  const [timeframe, setTimeframe] = React.useState<TimeframeValue>("6M");

  const portfoliosQuery = usePortfolios();
  const defaultQuery = useDefaultPortfolio();

  // Resolve the active portfolio: explicit selection wins, otherwise the
  // server-designated default, otherwise the first available.
  const portfolioId = selectedId ?? defaultQuery.data?.id ?? portfoliosQuery.data?.[0]?.id;

  const summaryQuery = usePortfolioSummary(portfolioId);
  const performanceQuery = usePortfolioPerformance(
    portfolioId,
    TIMEFRAMES.find((frame) => frame.value === timeframe)?.bars ?? 126,
  );
  const transactionsQuery = useTransactions(portfolioId);

  const summary = summaryQuery.data;

  const money = React.useCallback(
    (value: number | null | undefined, signed = false) =>
      formatCurrency(value, { symbol: currencySymbol, grouping, signed }),
    [currencySymbol, grouping],
  );

  const holdingColumns = React.useMemo<ColumnDef<Holding>[]>(
    () => [
      {
        accessorKey: "symbol",
        header: "Stock",
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-ink">{row.original.symbol}</p>
            <p className="truncate text-2xs text-ink-faint">
              {row.original.sector ?? "Unclassified"}
            </p>
          </div>
        ),
      },
      {
        accessorKey: "quantity",
        header: "Qty",
        cell: ({ row }) => (
          <span className="tabular text-xs">
            {formatNumber(row.original.quantity, { grouping, decimals: 0 })}
          </span>
        ),
      },
      {
        accessorKey: "average_cost",
        header: "Avg Cost",
        cell: ({ row }) => (
          <span className="tabular text-xs">
            {formatNumber(row.original.average_cost, { grouping })}
          </span>
        ),
      },
      {
        accessorKey: "current_price",
        header: "LTP",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">
            {formatNumber(row.original.current_price, { grouping })}
          </span>
        ),
      },
      {
        accessorKey: "market_value",
        header: "Value",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">
            {formatNumber(row.original.market_value, { grouping })}
          </span>
        ),
      },
      {
        accessorKey: "unrealized_pnl",
        header: "P&L",
        cell: ({ row }) => (
          <span
            className={cn("tabular text-xs font-medium", toneClass(row.original.unrealized_pnl))}
          >
            {money(row.original.unrealized_pnl, true)}
          </span>
        ),
      },
      {
        accessorKey: "unrealized_pnl_pct",
        header: "P&L %",
        cell: ({ row }) => (
          <span className={cn("tabular text-xs", toneClass(row.original.unrealized_pnl_pct))}>
            {formatPercent(row.original.unrealized_pnl_pct)}
          </span>
        ),
      },
      {
        accessorKey: "weight_pct",
        header: "Weight",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <div className="h-1 w-12 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${row.original.weight_pct * 100}%` }}
              />
            </div>
            <span className="tabular text-2xs text-ink-muted">
              {formatPercent(row.original.weight_pct, { signed: false, decimals: 1 })}
            </span>
          </div>
        ),
      },
    ],
    [grouping, money],
  );

  const transactionColumns = React.useMemo<ColumnDef<Transaction>[]>(
    () => [
      {
        accessorKey: "executed_at",
        header: "Date",
        cell: ({ row }) => (
          <span className="text-xs text-ink-muted">
            {formatDate(row.original.executed_at, "medium")}
          </span>
        ),
      },
      {
        accessorKey: "symbol",
        header: "Symbol",
        cell: ({ row }) => (
          <span className="text-xs font-medium text-ink">{row.original.symbol}</span>
        ),
      },
      {
        accessorKey: "side",
        header: "Side",
        cell: ({ row }) => (
          <Badge variant={row.original.side === "buy" ? "gain" : "loss"}>{row.original.side}</Badge>
        ),
      },
      {
        accessorKey: "quantity",
        header: "Qty",
        cell: ({ row }) => (
          <span className="tabular text-xs">
            {formatNumber(row.original.quantity, { grouping, decimals: 0 })}
          </span>
        ),
      },
      {
        accessorKey: "price",
        header: "Price",
        cell: ({ row }) => (
          <span className="tabular text-xs">{formatNumber(row.original.price, { grouping })}</span>
        ),
      },
      {
        accessorKey: "value",
        header: "Value",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">{money(row.original.value)}</span>
        ),
      },
      {
        id: "costs",
        header: "Costs",
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink-faint">
            {money(row.original.transaction_cost + row.original.slippage)}
          </span>
        ),
      },
      {
        accessorKey: "is_simulated",
        header: "Type",
        cell: ({ row }) => (
          <Badge variant="outline">{row.original.is_simulated ? "Paper" : "Live"}</Badge>
        ),
      },
    ],
    [grouping, money],
  );

  const performanceSeries = React.useMemo(
    () =>
      (performanceQuery.data ?? []).map((point) => ({
        label: formatDate(point.timestamp, "short"),
        value: point.value,
      })),
    [performanceQuery.data],
  );

  if (!portfoliosQuery.isLoading && !portfoliosQuery.data?.length) {
    return (
      <div className="space-y-5">
        <PageHeader
          title="Portfolio"
          description="Holdings, allocation, transactions and performance"
        />
        <Card>
          <CardContent className="pt-6">
            <EmptyState
              icon={Wallet}
              title="No portfolios yet"
              description="Create a portfolio to start recording trades and tracking performance."
              action={
                <CreatePortfolioDialog
                  trigger={
                    <Button variant="primary">
                      <Plus aria-hidden /> Create portfolio
                    </Button>
                  }
                />
              }
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Portfolio"
        description={
          summary ? `${summary.name} · benchmark ${summary.benchmark_symbol}` : "Loading portfolio…"
        }
        actions={
          <>
            {(portfoliosQuery.data?.length ?? 0) > 1 ? (
              <Select value={portfolioId} onValueChange={setSelectedId}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Select portfolio" />
                </SelectTrigger>
                <SelectContent>
                  {portfoliosQuery.data?.map((portfolio) => (
                    <SelectItem key={portfolio.id} value={portfolio.id}>
                      {portfolio.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            <CreatePortfolioDialog
              trigger={
                <Button variant="outline" size="sm">
                  <Plus aria-hidden /> New portfolio
                </Button>
              }
            />
            {portfolioId ? (
              <NewOrderDialog
                portfolioId={portfolioId}
                trigger={
                  <Button variant="primary" size="sm">
                    <Plus aria-hidden /> Add transaction
                  </Button>
                }
              />
            ) : null}
          </>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryQuery.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => <SkeletonStatCard key={index} />)
        ) : summary ? (
          <>
            <StatCard
              label="Total Value"
              value={money(summary.total_value)}
              change={summary.total_unrealized_pnl_pct}
              hint={`Invested ${money(summary.total_cost_basis)}`}
              icon={Wallet}
              accent="primary"
            />
            <StatCard
              label="Unrealized P&L"
              value={money(summary.total_unrealized_pnl, true)}
              change={summary.total_unrealized_pnl_pct}
              hint={`${summary.holding_count} open positions`}
              accent={summary.total_unrealized_pnl >= 0 ? "gain" : "loss"}
            />
            <StatCard
              label="Realized P&L"
              value={money(summary.total_realized_pnl, true)}
              tone={summary.total_realized_pnl >= 0 ? "gain" : "loss"}
              changeLabel="Booked on closed quantity"
              accent={summary.total_realized_pnl >= 0 ? "gain" : "loss"}
            />
            <StatCard
              label="Day Change"
              value={money(summary.day_change, true)}
              change={summary.day_change_pct}
              hint="Versus previous close"
              accent={summary.day_change >= 0 ? "gain" : "loss"}
            />
          </>
        ) : (
          <div className="sm:col-span-2 xl:col-span-4">
            <ErrorState error={summaryQuery.error} onRetry={() => summaryQuery.refetch()} />
          </div>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Performance</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                Current positions valued against historical closes
              </p>
            </div>
            <Tabs
              value={timeframe}
              onValueChange={(value) => setTimeframe(value as TimeframeValue)}
            >
              <TabsList>
                {TIMEFRAMES.slice(1, 6).map((frame) => (
                  <TabsTrigger key={frame.value} value={frame.value}>
                    {frame.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </CardHeader>
          <CardContent>
            {performanceQuery.isLoading ? (
              <SkeletonChart />
            ) : !performanceSeries.length ? (
              <EmptyState
                title="No performance history"
                description="Holdings need price history to chart."
              />
            ) : (
              <TimeSeriesChart
                data={performanceSeries}
                height={260}
                valueFormatter={(value) =>
                  formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                }
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Allocation</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="sector">
              <TabsList className="w-full">
                <TabsTrigger value="sector" className="flex-1">
                  Sector
                </TabsTrigger>
                <TabsTrigger value="asset" className="flex-1">
                  Asset Class
                </TabsTrigger>
              </TabsList>
              {(
                [
                  ["sector", summary?.sector_exposure],
                  ["asset", summary?.asset_allocation],
                ] as const
              ).map(([tab, slices]) => (
                <TabsContent key={tab} value={tab}>
                  {slices?.length ? (
                    <>
                      <DonutChart
                        data={slices}
                        height={168}
                        valueFormatter={(value) =>
                          formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                        }
                      />
                      <div className="mt-3">
                        <DonutLegend
                          data={slices}
                          valueFormatter={(value) =>
                            formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                          }
                        />
                      </div>
                    </>
                  ) : (
                    <EmptyState title="No allocation data" />
                  )}
                </TabsContent>
              ))}
            </Tabs>
          </CardContent>
        </Card>
      </section>

      <Tabs defaultValue="holdings">
        <TabsList>
          <TabsTrigger value="holdings">Holdings</TabsTrigger>
          <TabsTrigger value="transactions">Transactions</TabsTrigger>
        </TabsList>

        <TabsContent value="holdings">
          <Card>
            <CardContent className="pt-5">
              {summaryQuery.isLoading ? (
                <SkeletonTable rows={6} columns={8} />
              ) : (
                <DataTable
                  columns={holdingColumns}
                  data={summary?.holdings ?? []}
                  emptyTitle="No holdings"
                  emptyDescription="Record a buy transaction to open a position."
                  onRowClick={(row) => router.push(`/stocks/${row.symbol}`)}
                  pageSize={15}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="transactions">
          <Card>
            <CardContent className="pt-5">
              {transactionsQuery.isLoading ? (
                <SkeletonTable rows={8} columns={8} />
              ) : (
                <DataTable
                  columns={transactionColumns}
                  data={transactionsQuery.data ?? []}
                  emptyTitle="No transactions"
                  emptyDescription="Every buy and sell you record appears here as an immutable ledger."
                  pageSize={15}
                  dense
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
