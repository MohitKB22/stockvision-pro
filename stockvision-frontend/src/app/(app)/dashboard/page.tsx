"use client";

import * as React from "react";
import Link from "next/link";
import { Activity, ArrowRight, Percent, Target, Wallet } from "lucide-react";

import { useMarket } from "@/context/market-context";
import { useMarketOverview } from "@/hooks/use-market-data";
import { useGenerateSignalsBulk, useModels, useRecentSignals } from "@/hooks/use-ml";
import { useNews, useWatchlist } from "@/hooks/use-platform";
import {
  useDefaultPortfolio,
  usePortfolioPerformance,
  usePortfolioSummary,
} from "@/hooks/use-portfolio";
import { CHART_PALETTE, TIMEFRAMES, type TimeframeValue } from "@/lib/constants";
import {
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  toneClass,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { TimeSeriesChart } from "@/components/charts/area-chart";
import { DonutChart, DonutLegend } from "@/components/charts/donut-chart";
import { Sparkline } from "@/components/charts/sparkline";
import { SignalPanel } from "@/components/dashboard/signal-panel";
import { StatCard } from "@/components/dashboard/stat-card";
import { TickerStrip } from "@/components/dashboard/ticker-strip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonChart, SkeletonStatCard, SkeletonText } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";

/**
 * Dashboard.
 *
 * Every number on this page comes from an API call — portfolio value and P&L from
 * the portfolio service, index levels and movers computed from stored price
 * history, signals from the ML engine, news from the sentiment pipeline. There are
 * no placeholder cards and no hardcoded figures.
 */
export default function DashboardPage() {
  const { currencySymbol, grouping, definition } = useMarket();
  const [timeframe, setTimeframe] = React.useState<TimeframeValue>("6M");
  const [activeIndex, setActiveIndex] = React.useState<string | null>(null);

  const portfolioQuery = useDefaultPortfolio();
  const portfolioId = portfolioQuery.data?.id;

  const summaryQuery = usePortfolioSummary(portfolioId);
  const performanceQuery = usePortfolioPerformance(
    portfolioId,
    TIMEFRAMES.find((t) => t.value === timeframe)?.bars ?? 126,
  );
  const overviewQuery = useMarketOverview(5);
  const signalsQuery = useRecentSignals(6);
  const modelsQuery = useModels();
  const newsQuery = useNews(undefined, 5);
  const watchlistQuery = useWatchlist();
  const generateSignals = useGenerateSignalsBulk();

  const summary = summaryQuery.data;
  const overview = overviewQuery.data;

  const selectedIndex = React.useMemo(() => {
    if (!overview?.indices.length) return undefined;
    return overview.indices.find((index) => index.symbol === activeIndex) ?? overview.indices[0];
  }, [overview, activeIndex]);

  /**
   * AI accuracy across the model registry.
   *
   * Averaged over the accuracy metric of every registered version. Shown as "—"
   * rather than a fabricated number when nothing has been trained — a dashboard
   * that claims 92% accuracy with zero models is the exact failure mode this
   * rewrite set out to remove.
   */
  const aiAccuracy = React.useMemo(() => {
    const scored = (modelsQuery.data ?? []).filter((m) => typeof m.metrics?.accuracy === "number");
    if (!scored.length) return null;
    return scored.reduce((sum, m) => sum + (m.metrics.accuracy ?? 0), 0) / scored.length;
  }, [modelsQuery.data]);

  const performanceSeries = React.useMemo(
    () =>
      (performanceQuery.data ?? []).map((point) => ({
        label: formatDate(point.timestamp, "short"),
        value: point.value,
      })),
    [performanceQuery.data],
  );

  const money = React.useCallback(
    (value: number | null | undefined, signed = false) =>
      formatCurrency(value, { symbol: currencySymbol, grouping, signed }),
    [currencySymbol, grouping],
  );

  const handleGenerateSignals = React.useCallback(() => {
    const watched = (watchlistQuery.data?.items ?? []).slice(0, 8).map((item) => item.symbol);
    const fallback = (overview?.most_active ?? []).slice(0, 6).map((mover) => mover.symbol);
    const target = watched.length ? watched : fallback;
    if (target.length) generateSignals.mutate(target);
  }, [watchlistQuery.data, overview, generateSignals]);

  // No portfolio yet — an onboarding prompt, not an error.
  if (portfolioQuery.isError && !portfolioQuery.isLoading) {
    return (
      <Card className="mt-8">
        <CardContent className="pt-6">
          <EmptyState
            icon={Wallet}
            title="No portfolio yet"
            description={`Create a ${definition?.name ?? ""} portfolio to see holdings, P&L, allocation and risk analytics on this dashboard.`}
            action={
              <Button variant="primary" asChild>
                <Link href="/portfolio">Create a portfolio</Link>
              </Button>
            }
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {/* --- KPI row --- */}
      <section aria-label="Key metrics" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryQuery.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => <SkeletonStatCard key={index} />)
        ) : summary ? (
          <>
            <StatCard
              label="Portfolio Value"
              value={money(summary.total_value)}
              change={summary.total_unrealized_pnl_pct}
              hint={`${summary.holding_count} holdings · ${money(summary.cash_balance)} cash`}
              icon={Wallet}
              accent="primary"
              sparkline={performanceSeries.slice(-30).map((point) => point.value)}
            />
            <StatCard
              label="Today's P&L"
              value={money(summary.day_change, true)}
              change={summary.day_change_pct}
              hint="Change since previous close"
              icon={Activity}
              accent={summary.day_change >= 0 ? "gain" : "loss"}
            />
            <StatCard
              label="Total Return"
              value={money(summary.total_unrealized_pnl + summary.total_realized_pnl, true)}
              change={summary.total_unrealized_pnl_pct}
              hint={`Realized ${money(summary.total_realized_pnl, true)}`}
              icon={Percent}
              accent={summary.total_unrealized_pnl >= 0 ? "gain" : "loss"}
            />
            <StatCard
              label="AI Model Accuracy"
              value={
                aiAccuracy === null
                  ? "—"
                  : formatPercent(aiAccuracy, { signed: false, decimals: 1 })
              }
              changeLabel={
                aiAccuracy === null
                  ? "No models trained yet"
                  : `Mean across ${modelsQuery.data?.length ?? 0} versions`
              }
              tone="flat"
              hint="Walk-forward validation accuracy from the model registry"
              icon={Target}
              accent="accent"
            />
          </>
        ) : (
          <div className="sm:col-span-2 xl:col-span-4">
            <ErrorState error={summaryQuery.error} onRetry={() => summaryQuery.refetch()} />
          </div>
        )}
      </section>

      {/* --- Market overview + signals --- */}
      <section className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Market Overview</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                {selectedIndex?.is_synthetic
                  ? "Level synthesized from index constituents"
                  : "Index level from stored history"}
              </p>
            </div>
            <Button variant="ghost" size="xs" asChild>
              <Link href="/market">
                View all <ArrowRight aria-hidden />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {overviewQuery.isLoading ? (
              <SkeletonChart />
            ) : overviewQuery.isError ? (
              <ErrorState error={overviewQuery.error} onRetry={() => overviewQuery.refetch()} />
            ) : !overview?.indices.length ? (
              <EmptyState
                title="No index data"
                description="Seed market data to populate this view."
              />
            ) : (
              <>
                <div className="scrollbar-none -mx-1 mb-4 flex gap-2 overflow-x-auto px-1">
                  {overview.indices.map((index) => {
                    const active = index.symbol === (selectedIndex?.symbol ?? "");
                    return (
                      <button
                        key={index.symbol}
                        type="button"
                        onClick={() => setActiveIndex(index.symbol)}
                        className={cn(
                          "shrink-0 rounded-xl border px-3 py-2 text-left transition-all duration-200 ease-smooth",
                          active
                            ? "border-primary/45 bg-primary/10"
                            : "border-line bg-elevated/50 hover:border-line-strong",
                        )}
                        aria-pressed={active}
                      >
                        <span className="block text-2xs font-medium text-ink-subtle">
                          {index.name}
                        </span>
                        <span className="tabular block text-sm font-semibold text-ink">
                          {formatNumber(index.level, { grouping })}
                        </span>
                        <span className={cn("tabular block text-2xs", toneClass(index.change_pct))}>
                          {formatPercent(index.change_pct)}
                        </span>
                      </button>
                    );
                  })}
                </div>

                {selectedIndex ? (
                  <>
                    <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="tabular text-2xl font-semibold tracking-tight text-ink">
                        {formatNumber(selectedIndex.level, { grouping })}
                      </span>
                      <span
                        className={cn(
                          "tabular text-sm font-medium",
                          toneClass(selectedIndex.change),
                        )}
                      >
                        {formatNumber(selectedIndex.change, { grouping })} (
                        {formatPercent(selectedIndex.change_pct)})
                      </span>
                      <Badge variant="outline">
                        {selectedIndex.constituent_count} constituents
                      </Badge>
                    </div>
                    <TimeSeriesChart
                      data={selectedIndex.sparkline.map((value, index) => ({
                        label: `T-${selectedIndex.sparkline.length - index}`,
                        value,
                      }))}
                      height={200}
                      valueFormatter={(value) => formatNumber(value, { grouping, decimals: 0 })}
                    />
                  </>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>

        <SignalPanel
          signals={signalsQuery.data ?? []}
          isLoading={signalsQuery.isLoading}
          onGenerate={handleGenerateSignals}
          isGenerating={generateSignals.isPending}
        />
      </section>

      {/* --- Allocation, performance, news --- */}
      <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Portfolio Allocation</CardTitle>
          </CardHeader>
          <CardContent>
            {summaryQuery.isLoading ? (
              <SkeletonChart />
            ) : !summary?.sector_exposure.length ? (
              <EmptyState title="No holdings" description="Record a trade to see allocation." />
            ) : (
              <>
                <DonutChart
                  data={summary.sector_exposure}
                  height={172}
                  centerValue={formatCompactCurrency(summary.total_market_value, {
                    symbol: currencySymbol,
                    grouping,
                  })}
                  centerLabel="Invested"
                  valueFormatter={(value) =>
                    formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                  }
                />
                <div className="mt-4">
                  <DonutLegend
                    data={summary.sector_exposure}
                    valueFormatter={(value) =>
                      formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                    }
                  />
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Portfolio Performance</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                Current positions valued against historical closes
              </p>
            </div>
            <Tabs
              value={timeframe}
              onValueChange={(value) => setTimeframe(value as TimeframeValue)}
            >
              <TabsList>
                {TIMEFRAMES.slice(1, 5).map((frame) => (
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
                description="Add holdings with price history."
              />
            ) : (
              <TimeSeriesChart
                data={performanceSeries}
                height={210}
                valueFormatter={(value) =>
                  formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                }
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Market News</CardTitle>
            <Button variant="ghost" size="xs" asChild>
              <Link href="/news">
                All <ArrowRight aria-hidden />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {newsQuery.isLoading ? (
              <SkeletonText lines={8} />
            ) : !newsQuery.data?.items.length ? (
              <EmptyState title="No news yet" />
            ) : (
              <ul className="space-y-3">
                {newsQuery.data.items.slice(0, 4).map((article) => (
                  <li key={article.id}>
                    <p className="line-clamp-2 text-xs leading-snug text-ink-muted">
                      {article.headline}
                    </p>
                    <p className="mt-1 flex items-center gap-2 text-2xs text-ink-faint">
                      <span
                        className={cn(
                          "size-1.5 rounded-full",
                          article.sentiment_label === "positive"
                            ? "bg-gain"
                            : article.sentiment_label === "negative"
                              ? "bg-loss"
                              : "bg-ink-faint",
                        )}
                        aria-hidden
                      />
                      {article.source} · {formatRelativeTime(article.published_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      {/* --- Movers --- */}
      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Activity className="size-3.5 text-gain" aria-hidden />
              Top Gainers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MoverList movers={overview?.gainers ?? []} isLoading={overviewQuery.isLoading} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Activity className="size-3.5 rotate-180 text-loss" aria-hidden />
              Top Losers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MoverList movers={overview?.losers ?? []} isLoading={overviewQuery.isLoading} />
          </CardContent>
        </Card>
      </section>

      {/* --- Watchlist strip --- */}
      <section aria-label="Watchlist">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-ink-muted">
            Watchlist ({watchlistQuery.data?.item_count ?? 0})
          </h3>
          <Button variant="ghost" size="xs" asChild>
            <Link href="/watchlist">
              Manage <ArrowRight aria-hidden />
            </Link>
          </Button>
        </div>
        <TickerStrip
          items={watchlistQuery.data?.items ?? []}
          isLoading={watchlistQuery.isLoading}
        />
      </section>
    </div>
  );
}

function MoverList({
  movers,
  isLoading,
}: {
  movers: {
    symbol: string;
    name: string;
    last_price: number;
    change_pct: number;
    sparkline: number[];
  }[];
  isLoading: boolean;
}) {
  const { grouping } = useMarket();

  if (isLoading) return <SkeletonText lines={5} />;
  if (!movers.length) {
    return <EmptyState title="No movers" description="Requires two sessions of price data." />;
  }

  return (
    <ul className="space-y-0.5">
      {movers.map((mover, index) => (
        <li key={mover.symbol}>
          <Link
            href={`/stocks/${mover.symbol}`}
            className="flex items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-elevated"
          >
            <span
              className="size-1.5 shrink-0 rounded-full"
              style={{ backgroundColor: CHART_PALETTE[index % CHART_PALETTE.length] }}
              aria-hidden
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-ink">{mover.symbol}</span>
              <span className="block truncate text-2xs text-ink-faint">{mover.name}</span>
            </span>
            <Sparkline data={mover.sparkline} width={52} height={22} fill={false} />
            <span className="shrink-0 text-right">
              <span className="tabular block text-xs text-ink">
                {formatNumber(mover.last_price, { grouping })}
              </span>
              <span className={cn("tabular block text-2xs", toneClass(mover.change_pct))}>
                {formatPercent(mover.change_pct)}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
