"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Brain, Plus, Sparkles, Star } from "lucide-react";

import { useMarket } from "@/context/market-context";
import { useQuote } from "@/hooks/use-market-data";
import { useGenerateSignal, usePredict } from "@/hooks/use-ml";
import { useAddToWatchlist, useNews, useSettings, useWatchlist } from "@/hooks/use-platform";
import { useDefaultPortfolio } from "@/hooks/use-portfolio";
import { useFeatures, usePrices, useStock } from "@/hooks/use-stocks";
import { SIGNAL_META, TIMEFRAMES, type TimeframeValue } from "@/lib/constants";
import {
  formatCompactCurrency,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  formatVolume,
  toneClass,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { PriceChart } from "@/components/charts/price-chart";
import { PageHeader } from "@/components/layout/page-header";
import { NewOrderDialog } from "@/components/portfolio/new-order-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Tooltip } from "@/components/ui/misc";
import { Skeleton, SkeletonChart, SkeletonText } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";

/** Indicators surfaced in the technicals panel, with the reading rule for each. */
const INDICATOR_GUIDE: Record<
  string,
  { label: string; hint: string; format?: (value: number) => string }
> = {
  rsi_14: { label: "RSI (14)", hint: "Below 30 is oversold, above 70 overbought." },
  macd: { label: "MACD", hint: "Momentum: the 12/26 EMA difference." },
  macd_signal: { label: "MACD Signal", hint: "9-period EMA of MACD." },
  macd_hist: { label: "MACD Histogram", hint: "Positive means bullish momentum." },
  sma_20: { label: "SMA (20)", hint: "20-session simple moving average." },
  sma_50: { label: "SMA (50)", hint: "50-session simple moving average." },
  ema_12: { label: "EMA (12)", hint: "Fast exponential moving average." },
  bb_upper: { label: "Bollinger Upper", hint: "Two standard deviations above the 20-SMA." },
  bb_lower: { label: "Bollinger Lower", hint: "Two standard deviations below the 20-SMA." },
  atr_14: { label: "ATR (14)", hint: "Average True Range — absolute volatility." },
  adx: { label: "ADX", hint: "Above 25 signals a genuine trend; below 20 is chop." },
  plus_di: { label: "+DI", hint: "Positive directional indicator." },
  minus_di: { label: "−DI", hint: "Negative directional indicator." },
  volatility_20d: {
    label: "Volatility (20d)",
    hint: "Annualized rolling standard deviation of returns.",
    format: (value) => `${(value * 100).toFixed(1)}%`,
  },
  supertrend_direction: {
    label: "SuperTrend",
    hint: "+1 is an uptrend, −1 a downtrend.",
    format: (value) => (value > 0 ? "Bullish" : "Bearish"),
  },
};

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = (params?.symbol ?? "").toUpperCase();
  const { grouping, currencySymbol } = useMarket();

  const [timeframe, setTimeframe] = React.useState<TimeframeValue>("6M");
  const bars = TIMEFRAMES.find((frame) => frame.value === timeframe)?.bars ?? 126;

  const stockQuery = useStock(symbol);
  const quoteQuery = useQuote(symbol);
  const pricesQuery = usePrices(symbol, bars);
  const featuresQuery = useFeatures(symbol, 60);
  const newsQuery = useNews(symbol, 8);
  const watchlistQuery = useWatchlist();
  const portfolioQuery = useDefaultPortfolio();
  const settingsQuery = useSettings();

  const addToWatchlist = useAddToWatchlist(watchlistQuery.data?.id);
  const generateSignal = useGenerateSignal();
  const predict = usePredict();

  const quote = quoteQuery.data;
  const stock = stockQuery.data;
  const signal = generateSignal.data;

  const latestIndicators = React.useMemo(() => {
    const snapshots = featuresQuery.data ?? [];
    // Walk backwards for the most recent row where indicators have cleared their
    // warm-up windows — the very last row often still has NaNs for the
    // longest-window indicators.
    for (let index = snapshots.length - 1; index >= 0; index -= 1) {
      const values = snapshots[index].indicators;
      if (Object.values(values).some((value) => value !== null)) return values;
    }
    return null;
  }, [featuresQuery.data]);

  const onWatchlist = React.useMemo(
    () => (watchlistQuery.data?.items ?? []).some((item) => item.symbol === symbol),
    [watchlistQuery.data, symbol],
  );

  const chartVariant = settingsQuery.data?.chart_type === "candlestick" ? "candlestick" : "area";

  if (stockQuery.isError) {
    return (
      <div className="space-y-5">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/market">
            <ArrowLeft aria-hidden /> Back to market
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-5">
            <ErrorState error={stockQuery.error} />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Button variant="ghost" size="xs" asChild className="-ml-2">
        <Link href="/market">
          <ArrowLeft aria-hidden /> Market
        </Link>
      </Button>

      <PageHeader
        title={stock?.name ?? symbol}
        description={
          stock
            ? `${stock.symbol} · ${stock.exchange} · ${stock.sector ?? "Unclassified"}`
            : "Loading…"
        }
        actions={
          <>
            <Button
              variant={onWatchlist ? "secondary" : "outline"}
              size="sm"
              disabled={onWatchlist || !watchlistQuery.data?.id}
              loading={addToWatchlist.isPending}
              onClick={() => addToWatchlist.mutate({ symbol })}
            >
              <Star className={cn(onWatchlist && "fill-warn text-warn")} aria-hidden />
              {onWatchlist ? "On watchlist" : "Add to watchlist"}
            </Button>
            {portfolioQuery.data?.id ? (
              <NewOrderDialog
                portfolioId={portfolioQuery.data.id}
                defaultSymbol={symbol}
                trigger={
                  <Button variant="primary" size="sm">
                    <Plus aria-hidden /> Trade
                  </Button>
                }
              />
            ) : null}
          </>
        }
      />

      {/* --- Quote header --- */}
      <Card className="p-5">
        {quoteQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-72" />
          </div>
        ) : quote ? (
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="tabular text-3xl font-semibold tracking-tight text-ink">
                {currencySymbol}
                {formatNumber(quote.last_price, { grouping })}
              </p>
              <p className={cn("tabular mt-1 text-sm font-medium", toneClass(quote.change))}>
                {formatNumber(quote.change, { grouping })} ({formatPercent(quote.change_pct)})
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-4">
              <QuoteStat
                label="Prev Close"
                value={formatNumber(quote.previous_close, { grouping })}
              />
              <QuoteStat label="Volume" value={formatVolume(quote.volume, grouping)} />
              <QuoteStat
                label="Avg Vol (30d)"
                value={formatVolume(quote.avg_volume_30d, grouping)}
              />
              <QuoteStat
                label="Market Cap"
                value={formatCompactCurrency(quote.market_cap, {
                  symbol: currencySymbol,
                  grouping,
                })}
              />
              <QuoteStat label="52W High" value={formatNumber(quote.week_52_high, { grouping })} />
              <QuoteStat label="52W Low" value={formatNumber(quote.week_52_low, { grouping })} />
            </dl>
          </div>
        ) : (
          <EmptyState
            title="No quote available"
            description="This symbol has fewer than two price bars."
          />
        )}
      </Card>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Price Chart</CardTitle>
            <Tabs
              value={timeframe}
              onValueChange={(value) => setTimeframe(value as TimeframeValue)}
            >
              <TabsList>
                {TIMEFRAMES.map((frame) => (
                  <TabsTrigger key={frame.value} value={frame.value}>
                    {frame.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </CardHeader>
          <CardContent>
            {pricesQuery.isLoading ? (
              <SkeletonChart className="h-[340px]" />
            ) : (
              <PriceChart
                bars={pricesQuery.data ?? []}
                height={320}
                variant={chartVariant}
                currencySymbol={currencySymbol}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Sparkles className="size-3.5 text-accent" aria-hidden />
              AI Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            {signal ? (
              <>
                <p
                  className={cn(
                    "text-2xl font-bold tracking-tight",
                    SIGNAL_META[signal.action].tone === "gain"
                      ? "text-gain"
                      : SIGNAL_META[signal.action].tone === "loss"
                        ? "text-loss"
                        : "text-ink",
                  )}
                >
                  {SIGNAL_META[signal.action].label}
                </p>
                <p className="mt-2 text-xs leading-relaxed text-ink-subtle">{signal.explanation}</p>

                <div className="mt-4 space-y-3">
                  <div>
                    <div className="mb-1 flex justify-between text-2xs">
                      <span className="text-ink-subtle">Confidence</span>
                      <span className="tabular text-ink">
                        {formatPercent(signal.confidence, { signed: false })}
                      </span>
                    </div>
                    <Progress value={signal.confidence * 100} />
                  </div>
                  <div>
                    <div className="mb-1 flex justify-between text-2xs">
                      <span className="text-ink-subtle">Risk score</span>
                      <span className="tabular text-ink">{signal.risk_score.toFixed(2)}</span>
                    </div>
                    <Progress
                      value={signal.risk_score * 100}
                      indicatorClassName={
                        signal.risk_score > 0.66
                          ? "bg-loss"
                          : signal.risk_score > 0.33
                            ? "bg-warn"
                            : "bg-gain"
                      }
                    />
                  </div>
                </div>

                {Object.keys(signal.supporting_indicators ?? {}).length ? (
                  <div className="mt-4 border-t border-line pt-3">
                    <p className="stat-label mb-2">Contributing indicators</p>
                    <ul className="space-y-1">
                      {Object.entries(signal.supporting_indicators).map(([name, vote]) => (
                        <li key={name} className="flex items-center justify-between text-2xs">
                          <span className="text-ink-muted">
                            {INDICATOR_GUIDE[name]?.label ?? name}
                          </span>
                          <Badge variant={vote > 0 ? "gain" : vote < 0 ? "loss" : "default"}>
                            {vote > 0 ? "Bullish" : vote < 0 ? "Bearish" : "Neutral"}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            ) : (
              <EmptyState
                icon={Brain}
                title="No analysis yet"
                description="Generate a signal to blend technical indicators with the ML model's probability."
              />
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="primary"
                size="sm"
                loading={generateSignal.isPending}
                onClick={() => generateSignal.mutate(symbol)}
              >
                <Sparkles aria-hidden /> Generate signal
              </Button>
              <Button
                variant="outline"
                size="sm"
                loading={predict.isPending}
                onClick={() => predict.mutate({ symbol })}
              >
                <Brain aria-hidden /> Predict
              </Button>
            </div>

            {predict.data ? (
              <p className="mt-3 rounded-lg border border-line bg-elevated/50 px-3 py-2 text-2xs text-ink-muted">
                {predict.data.model_name} v{predict.data.model_version} estimates a{" "}
                <span className="tabular font-medium text-ink">
                  {formatPercent(predict.data.predicted_value, { signed: false })}
                </span>{" "}
                probability of a higher close, at{" "}
                {formatPercent(predict.data.confidence, { signed: false })} confidence.
              </p>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Technical Indicators</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                Latest fully-warmed values from the feature engine
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {featuresQuery.isLoading ? (
              <SkeletonText lines={8} />
            ) : featuresQuery.isError ? (
              <ErrorState error={featuresQuery.error} />
            ) : !latestIndicators ? (
              <EmptyState
                title="No indicators"
                description="Requires enough history to clear every warm-up window."
              />
            ) : (
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
                {Object.entries(INDICATOR_GUIDE).map(([key, guide]) => {
                  const value = latestIndicators[key];
                  if (value === null || value === undefined) return null;
                  return (
                    <Tooltip key={key} content={guide.hint}>
                      <div className="flex cursor-default items-baseline justify-between gap-2 border-b border-line/60 pb-1.5">
                        <dt className="truncate text-2xs text-ink-subtle">{guide.label}</dt>
                        <dd className="tabular shrink-0 text-xs font-medium text-ink">
                          {guide.format
                            ? guide.format(value)
                            : formatNumber(value, { grouping, decimals: 2 })}
                        </dd>
                      </div>
                    </Tooltip>
                  );
                })}
              </dl>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Related News</CardTitle>
          </CardHeader>
          <CardContent>
            {newsQuery.isLoading ? (
              <SkeletonText lines={8} />
            ) : !newsQuery.data?.items.length ? (
              <EmptyState title="No news for this company" />
            ) : (
              <ul className="space-y-3">
                {newsQuery.data.items.map((article) => (
                  <li
                    key={article.id}
                    className="border-b border-line/60 pb-3 last:border-0 last:pb-0"
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          article.sentiment_label === "positive"
                            ? "gain"
                            : article.sentiment_label === "negative"
                              ? "loss"
                              : "default"
                        }
                      >
                        {article.sentiment_label}
                      </Badge>
                      <span className="text-2xs text-ink-faint">
                        {article.source} · {formatRelativeTime(article.published_at)}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs leading-snug text-ink-muted">{article.headline}</p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function QuoteStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="stat-label">{label}</dt>
      <dd className="tabular mt-0.5 text-xs font-medium text-ink">{value}</dd>
    </div>
  );
}
