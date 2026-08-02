"use client";

import * as React from "react";
import Link from "next/link";
import { ExternalLink, Info, Newspaper, TrendingDown, TrendingUp } from "lucide-react";

import { useMarketSentiment, useNews } from "@/hooks/use-platform";
import { useStocks } from "@/hooks/use-stocks";
import { formatPercent, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SentimentLabel } from "@/types";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Tooltip } from "@/components/ui/misc";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";

const SENTIMENT_STYLE: Record<
  SentimentLabel,
  { badge: "gain" | "loss" | "default"; label: string }
> = {
  positive: { badge: "gain", label: "Positive" },
  neutral: { badge: "default", label: "Neutral" },
  negative: { badge: "loss", label: "Negative" },
};

export default function NewsPage() {
  const [symbol, setSymbol] = React.useState("all");
  const [filter, setFilter] = React.useState<"all" | SentimentLabel>("all");

  const stocksQuery = useStocks();
  const newsQuery = useNews(symbol === "all" ? undefined : symbol, 60);
  const sentimentQuery = useMarketSentiment(7);

  const items = React.useMemo(() => {
    const all = newsQuery.data?.items ?? [];
    return filter === "all" ? all : all.filter((article) => article.sentiment_label === filter);
  }, [newsQuery.data, filter]);

  const summary = newsQuery.data?.summary;

  return (
    <div className="space-y-5">
      <PageHeader
        title="News Intelligence"
        description="Headlines scored by a finance-tuned sentiment engine"
        actions={
          <Select value={symbol} onValueChange={setSymbol}>
            <SelectTrigger className="w-[184px]">
              <SelectValue placeholder="All companies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All companies</SelectItem>
              {(stocksQuery.data ?? []).map((stock) => (
                <SelectItem key={stock.id} value={stock.symbol}>
                  {stock.symbol} — {stock.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      <section className="grid gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <div>
              <CardTitle>7-Day Sentiment</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">Across the whole market</p>
            </div>
          </CardHeader>
          <CardContent>
            {sentimentQuery.isLoading ? (
              <SkeletonText lines={4} />
            ) : sentimentQuery.data ? (
              <>
                <p
                  className={cn(
                    "tabular text-3xl font-semibold tracking-tight",
                    sentimentQuery.data.average_sentiment > 0.05
                      ? "text-gain"
                      : sentimentQuery.data.average_sentiment < -0.05
                        ? "text-loss"
                        : "text-ink",
                  )}
                >
                  {sentimentQuery.data.average_sentiment >= 0 ? "+" : ""}
                  {sentimentQuery.data.average_sentiment.toFixed(2)}
                </p>
                <p className="mt-1 text-2xs text-ink-faint">
                  Scale −1 to +1 · {sentimentQuery.data.article_count} articles
                </p>

                <div className="mt-4 space-y-2.5">
                  <SentimentBar
                    label="Positive"
                    count={sentimentQuery.data.positive}
                    total={sentimentQuery.data.article_count}
                    tone="gain"
                  />
                  <SentimentBar
                    label="Neutral"
                    count={sentimentQuery.data.neutral}
                    total={sentimentQuery.data.article_count}
                    tone="flat"
                  />
                  <SentimentBar
                    label="Negative"
                    count={sentimentQuery.data.negative}
                    total={sentimentQuery.data.article_count}
                    tone="loss"
                  />
                </div>

                <Tooltip content="A deterministic, finance-tuned lexicon model with negation and intensifier handling. Fast and fully inspectable; a transformer would be more accurate on subtle phrasing.">
                  <p className="mt-4 flex cursor-default items-center gap-1.5 border-t border-line pt-3 text-2xs text-ink-faint">
                    <Info className="size-3" aria-hidden />
                    Engine: {sentimentQuery.data.engine}
                  </p>
                </Tooltip>
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <div>
              <CardTitle>Headlines</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                {summary ? `${summary.article_count} articles in view` : "Loading…"}
              </p>
            </div>
            <Tabs value={filter} onValueChange={(value) => setFilter(value as typeof filter)}>
              <TabsList>
                <TabsTrigger value="all">All</TabsTrigger>
                <TabsTrigger value="positive">
                  <TrendingUp aria-hidden /> Positive
                </TabsTrigger>
                <TabsTrigger value="negative">
                  <TrendingDown aria-hidden /> Negative
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </CardHeader>
          <CardContent>
            {newsQuery.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton key={index} className="h-20 w-full rounded-xl" />
                ))}
              </div>
            ) : newsQuery.isError ? (
              <ErrorState error={newsQuery.error} onRetry={() => newsQuery.refetch()} />
            ) : !items.length ? (
              <EmptyState
                icon={Newspaper}
                title={filter === "all" ? "No news articles" : `No ${filter} articles`}
                description={
                  filter === "all"
                    ? "Seed the news corpus or ingest articles via the API to populate this feed."
                    : "Try a different sentiment filter."
                }
              />
            ) : (
              <ul className="space-y-2.5">
                {items.map((article) => {
                  const style = SENTIMENT_STYLE[article.sentiment_label];
                  return (
                    <li
                      key={article.id}
                      className="rounded-xl border border-line bg-elevated/40 p-3.5 transition-colors hover:border-line-strong"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={style.badge}>{style.label}</Badge>
                        {article.symbol ? (
                          <Link href={`/stocks/${article.symbol}`}>
                            <Badge variant="primary">{article.symbol}</Badge>
                          </Link>
                        ) : null}
                        <span className="text-2xs text-ink-faint">
                          {article.source} · {formatRelativeTime(article.published_at)}
                        </span>
                        {article.impact_score !== null ? (
                          <Tooltip content="Estimated impact — magnitude of sentiment, weighted by whether the headline quotes hard figures.">
                            <span className="tabular ml-auto cursor-default text-2xs text-ink-faint">
                              impact {(article.impact_score * 100).toFixed(0)}%
                            </span>
                          </Tooltip>
                        ) : null}
                      </div>

                      <p className="mt-2 text-sm font-medium leading-snug text-ink">
                        {article.headline}
                      </p>
                      {article.summary ? (
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-subtle">
                          {article.summary}
                        </p>
                      ) : null}

                      <div className="mt-2.5 flex flex-wrap items-center gap-3">
                        <span
                          className={cn(
                            "tabular text-2xs font-medium",
                            article.sentiment_label === "positive"
                              ? "text-gain"
                              : article.sentiment_label === "negative"
                                ? "text-loss"
                                : "text-ink-faint",
                          )}
                        >
                          sentiment {article.sentiment_score?.toFixed(2) ?? "—"}
                        </span>
                        {article.entities.slice(0, 3).map((entity) => (
                          <Badge key={entity} variant="outline">
                            {entity}
                          </Badge>
                        ))}
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-auto flex items-center gap-1 text-2xs text-primary transition-colors hover:underline"
                        >
                          Read source <ExternalLink className="size-3" aria-hidden />
                        </a>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function SentimentBar({
  label,
  count,
  total,
  tone,
}: {
  label: string;
  count: number;
  total: number;
  tone: "gain" | "loss" | "flat";
}) {
  const share = total ? count / total : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-2xs">
        <span className="text-ink-subtle">{label}</span>
        <span className="tabular text-ink-muted">
          {count} ({formatPercent(share, { signed: false, decimals: 0 })})
        </span>
      </div>
      <Progress
        value={share * 100}
        indicatorClassName={
          tone === "gain" ? "bg-gain" : tone === "loss" ? "bg-loss" : "bg-ink-faint"
        }
      />
    </div>
  );
}
