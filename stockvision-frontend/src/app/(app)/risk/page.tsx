"use client";

import * as React from "react";
import { Activity, AlertTriangle, ShieldAlert, TrendingDown } from "lucide-react";

import { useMarket } from "@/context/market-context";
import { useDefaultPortfolio, usePortfolios } from "@/hooks/use-portfolio";
import { useCorrelation, useMonteCarlo, useRiskMetrics, useStressTest } from "@/hooks/use-risk";
import {
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatPercent,
  toneClass,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { TimeSeriesChart } from "@/components/charts/area-chart";
import { CorrelationMatrix } from "@/components/charts/correlation-matrix";
import { MonteCarloFan, ReturnHistogram } from "@/components/charts/monte-carlo";
import { StatCard } from "@/components/dashboard/stat-card";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/misc";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonChart, SkeletonStatCard, SkeletonTable } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState } from "@/components/ui/states";

const LOOKBACKS = [
  { value: "126", label: "6 months" },
  { value: "252", label: "1 year" },
  { value: "504", label: "2 years" },
  { value: "756", label: "3 years" },
];

const HORIZONS = [
  { value: "63", label: "3 months" },
  { value: "126", label: "6 months" },
  { value: "252", label: "1 year" },
  { value: "504", label: "2 years" },
];

export default function RiskPage() {
  const { currencySymbol, grouping } = useMarket();
  const [lookback, setLookback] = React.useState("252");
  const [horizon, setHorizon] = React.useState("252");
  const [simulations, setSimulations] = React.useState("1000");
  const [selectedId, setSelectedId] = React.useState<string | undefined>();

  const portfoliosQuery = usePortfolios();
  const defaultQuery = useDefaultPortfolio();
  const portfolioId = selectedId ?? defaultQuery.data?.id ?? portfoliosQuery.data?.[0]?.id;

  const lookbackDays = Number(lookback);
  const metricsQuery = useRiskMetrics(portfolioId, lookbackDays);
  const monteCarloQuery = useMonteCarlo(portfolioId, Number(horizon), Number(simulations));
  const correlationQuery = useCorrelation(portfolioId, lookbackDays);
  const stressQuery = useStressTest(portfolioId);

  const metrics = metricsQuery.data;

  const money = React.useCallback(
    (value: number | null | undefined, signed = false) =>
      formatCurrency(value, { symbol: currencySymbol, grouping, signed }),
    [currencySymbol, grouping],
  );

  const drawdownSeries = React.useMemo(
    () =>
      (metrics?.drawdown_series ?? []).map((point) => ({
        label: formatDate(point.timestamp, "short"),
        value: point.drawdown * 100,
      })),
    [metrics],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Risk Analytics"
        description={
          metrics
            ? `${metrics.observations} daily observations · benchmark ${metrics.benchmark_symbol}`
            : "Value at Risk, Monte Carlo, correlation and stress testing"
        }
        actions={
          <>
            {(portfoliosQuery.data?.length ?? 0) > 1 ? (
              <Select value={portfolioId} onValueChange={setSelectedId}>
                <SelectTrigger className="w-[184px]">
                  <SelectValue placeholder="Portfolio" />
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
            <Select value={lookback} onValueChange={setLookback}>
              <SelectTrigger className="w-[136px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LOOKBACKS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        }
      />

      {/* --- Headline risk metrics --- */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {metricsQuery.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => <SkeletonStatCard key={index} />)
        ) : metricsQuery.isError ? (
          <div className="sm:col-span-2 xl:col-span-4">
            <Card>
              <CardContent className="pt-5">
                <ErrorState error={metricsQuery.error} onRetry={() => metricsQuery.refetch()} />
              </CardContent>
            </Card>
          </div>
        ) : metrics ? (
          <>
            <StatCard
              label="Sharpe Ratio"
              value={metrics.sharpe_ratio.toFixed(2)}
              changeLabel={qualify(metrics.sharpe_ratio, [0, 1, 2])}
              tone={
                metrics.sharpe_ratio >= 1 ? "gain" : metrics.sharpe_ratio >= 0 ? "flat" : "loss"
              }
              hint="Excess return per unit of total volatility"
              icon={Activity}
              accent={metrics.sharpe_ratio >= 1 ? "gain" : "warn"}
            />
            <StatCard
              label="Sortino Ratio"
              value={metrics.sortino_ratio.toFixed(2)}
              changeLabel={qualify(metrics.sortino_ratio, [0, 1.5, 2.5])}
              tone={metrics.sortino_ratio >= 1.5 ? "gain" : "flat"}
              hint="Like Sharpe, but penalises only downside deviation"
              icon={Activity}
              accent={metrics.sortino_ratio >= 1.5 ? "gain" : "warn"}
            />
            <StatCard
              label="Value at Risk (95%)"
              value={money(metrics.value_at_risk_amount)}
              changeLabel={`${formatPercent(metrics.value_at_risk_95_historical, { signed: false })} of portfolio`}
              tone="loss"
              hint="Historical method — the empirical 5th-percentile daily loss"
              icon={ShieldAlert}
              accent="warn"
            />
            <StatCard
              label="Max Drawdown"
              value={formatPercent(metrics.max_drawdown)}
              changeLabel="Worst peak-to-trough decline"
              tone="loss"
              hint={`Over the last ${metrics.lookback_days} sessions`}
              icon={TrendingDown}
              accent="loss"
            />
          </>
        ) : null}
      </section>

      {metrics ? (
        <>
          <section className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <div>
                  <CardTitle>Monte Carlo Simulation</CardTitle>
                  <p className="mt-0.5 text-2xs text-ink-faint">
                    Geometric Brownian Motion · seeded, so the same portfolio always produces the
                    same projection
                  </p>
                </div>
                <div className="flex gap-2">
                  <Select value={horizon} onValueChange={setHorizon}>
                    <SelectTrigger className="h-8 w-[120px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HORIZONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={simulations} onValueChange={setSimulations}>
                    <SelectTrigger className="h-8 w-[112px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["500", "1000", "5000", "10000"].map((count) => (
                        <SelectItem key={count} value={count}>
                          {Number(count).toLocaleString()} runs
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </CardHeader>
              <CardContent>
                {monteCarloQuery.isLoading ? (
                  <SkeletonChart />
                ) : monteCarloQuery.isError ? (
                  <ErrorState
                    error={monteCarloQuery.error}
                    onRetry={() => monteCarloQuery.refetch()}
                  />
                ) : monteCarloQuery.data ? (
                  <>
                    <MonteCarloFan
                      result={monteCarloQuery.data}
                      height={280}
                      valueFormatter={(value) =>
                        formatCompactCurrency(value, { symbol: currencySymbol, grouping })
                      }
                    />
                    <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                      <MiniStat
                        label="Expected value"
                        value={money(monteCarloQuery.data.terminal.mean)}
                      />
                      <MiniStat
                        label="Expected return"
                        value={formatPercent(monteCarloQuery.data.terminal.expected_return_pct)}
                        tone={
                          monteCarloQuery.data.terminal.expected_return_pct >= 0 ? "gain" : "loss"
                        }
                      />
                      <MiniStat
                        label="5th percentile"
                        value={money(monteCarloQuery.data.terminal.p5)}
                        tone="loss"
                      />
                      <MiniStat
                        label="P(loss)"
                        value={formatPercent(monteCarloQuery.data.terminal.probability_of_loss, {
                          signed: false,
                        })}
                        tone={
                          monteCarloQuery.data.terminal.probability_of_loss > 0.4 ? "loss" : "flat"
                        }
                      />
                    </dl>
                  </>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Value at Risk</CardTitle>
                  <p className="mt-0.5 text-2xs text-ink-faint">
                    Three independent estimation methods
                  </p>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <ReturnHistogram
                  returns={metrics.return_distribution}
                  varThreshold={metrics.value_at_risk_95_historical}
                  height={132}
                />
                <p className="text-2xs text-ink-faint">
                  Red bars are sessions worse than the 95% VaR threshold.
                </p>
                <dl className="space-y-2.5">
                  <VarRow
                    label="Historical"
                    value={metrics.value_at_risk_95_historical}
                    amount={money(metrics.value_at_risk_95_historical * metrics.portfolio_value)}
                    hint="Empirical loss quantile — no distributional assumption."
                  />
                  <VarRow
                    label="Parametric"
                    value={metrics.value_at_risk_95_parametric}
                    amount={money(metrics.value_at_risk_95_parametric * metrics.portfolio_value)}
                    hint="Closed-form, assumes normally distributed returns."
                  />
                  <VarRow
                    label="Monte Carlo"
                    value={metrics.value_at_risk_95_monte_carlo}
                    amount={money(metrics.value_at_risk_95_monte_carlo * metrics.portfolio_value)}
                    hint="Simulated from a fitted normal distribution."
                  />
                  <VarRow
                    label="Expected Shortfall"
                    value={metrics.expected_shortfall_95}
                    amount={money(metrics.expected_shortfall_95 * metrics.portfolio_value)}
                    hint="Average loss GIVEN the loss already exceeds VaR."
                    emphasis
                  />
                </dl>
              </CardContent>
            </Card>
          </section>

          <Tabs defaultValue="drawdown">
            <TabsList className="flex-wrap">
              <TabsTrigger value="drawdown">Drawdown</TabsTrigger>
              <TabsTrigger value="correlation">Correlation Matrix</TabsTrigger>
              <TabsTrigger value="stress">Stress Testing</TabsTrigger>
              <TabsTrigger value="metrics">All Metrics</TabsTrigger>
            </TabsList>

            <TabsContent value="drawdown">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Underwater Chart</CardTitle>
                    <p className="mt-0.5 text-2xs text-ink-faint">
                      Percentage below the running peak — shows how long recoveries took, not just
                      how deep declines went
                    </p>
                  </div>
                </CardHeader>
                <CardContent>
                  <TimeSeriesChart
                    data={drawdownSeries}
                    height={260}
                    tone="loss"
                    valueFormatter={(value) => `${value.toFixed(1)}%`}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="correlation">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Holding Correlation</CardTitle>
                    <p className="mt-0.5 text-2xs text-ink-faint">
                      Pairwise Pearson correlation of daily returns, aligned by date
                    </p>
                  </div>
                  {correlationQuery.data?.average_correlation !== null &&
                  correlationQuery.data?.average_correlation !== undefined ? (
                    <Badge
                      variant={correlationQuery.data.average_correlation > 0.6 ? "warn" : "gain"}
                    >
                      Avg {correlationQuery.data.average_correlation.toFixed(2)}
                    </Badge>
                  ) : null}
                </CardHeader>
                <CardContent>
                  {correlationQuery.isLoading ? (
                    <SkeletonTable rows={6} columns={6} />
                  ) : correlationQuery.isError ? (
                    <ErrorState error={correlationQuery.error} />
                  ) : (
                    <>
                      <CorrelationMatrix
                        labels={correlationQuery.data?.labels ?? []}
                        matrix={correlationQuery.data?.matrix ?? []}
                      />
                      {(correlationQuery.data?.average_correlation ?? 0) > 0.6 ? (
                        <p className="bg-warn/8 mt-4 flex items-start gap-2 rounded-lg border border-warn/25 px-3 py-2 text-2xs text-warn">
                          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
                          High average correlation means these positions tend to fall together — the
                          diversification benefit is smaller than the position count suggests.
                        </p>
                      ) : null}
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="stress">
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Scenario Analysis</CardTitle>
                    <p className="mt-0.5 text-2xs text-ink-faint">
                      Historical shock magnitudes scaled by this portfolio&apos;s beta
                    </p>
                  </div>
                </CardHeader>
                <CardContent>
                  {stressQuery.isLoading ? (
                    <SkeletonTable rows={5} columns={5} />
                  ) : stressQuery.isError ? (
                    <ErrorState error={stressQuery.error} />
                  ) : (
                    <div className="space-y-2">
                      {(stressQuery.data?.scenarios ?? []).map((scenario) => (
                        <div
                          key={scenario.scenario}
                          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-elevated/40 px-3 py-2.5"
                        >
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-ink">{scenario.scenario}</p>
                            <p className="mt-0.5 text-2xs text-ink-faint">
                              Market shock {formatPercent(scenario.market_shock_pct)} · volatility ×
                              {(
                                scenario.stressed_annual_volatility /
                                (metrics.annualized_volatility || 1)
                              ).toFixed(1)}
                              {scenario.beta_assumed
                                ? " · beta assumed 1.0"
                                : ` · beta ${scenario.beta_used.toFixed(2)}`}
                            </p>
                          </div>
                          <div className="text-right">
                            <p
                              className={cn(
                                "tabular text-sm font-semibold",
                                toneClass(scenario.portfolio_impact_value),
                              )}
                            >
                              {money(scenario.portfolio_impact_value, true)}
                            </p>
                            <p
                              className={cn(
                                "tabular text-2xs",
                                toneClass(scenario.portfolio_impact_pct),
                              )}
                            >
                              {formatPercent(scenario.portfolio_impact_pct)} →{" "}
                              {money(scenario.resulting_value)}
                            </p>
                          </div>
                        </div>
                      ))}
                      {stressQuery.data?.scenarios.some((s) => s.beta_assumed) ? (
                        <p className="pt-2 text-2xs text-ink-faint">
                          No benchmark beta was computable for this portfolio, so a beta of 1.0 was
                          assumed — impacts are index-equivalent rather than portfolio-specific.
                        </p>
                      ) : null}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="metrics">
              <Card>
                <CardContent className="pt-5">
                  <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                    <MetricRow
                      label="Annualized Return"
                      value={formatPercent(metrics.annualized_return)}
                      tone={metrics.annualized_return >= 0 ? "gain" : "loss"}
                    />
                    <MetricRow
                      label="Annualized Volatility"
                      value={formatPercent(metrics.annualized_volatility, { signed: false })}
                    />
                    <MetricRow label="Sharpe Ratio" value={metrics.sharpe_ratio.toFixed(3)} />
                    <MetricRow label="Sortino Ratio" value={metrics.sortino_ratio.toFixed(3)} />
                    <MetricRow
                      label="Max Drawdown"
                      value={formatPercent(metrics.max_drawdown)}
                      tone="loss"
                    />
                    <MetricRow
                      label="Beta"
                      value={metrics.beta === null ? "Not computable" : metrics.beta.toFixed(3)}
                    />
                    <MetricRow
                      label="Alpha (annualized)"
                      value={
                        metrics.alpha === null ? "Not computable" : formatPercent(metrics.alpha)
                      }
                      tone={(metrics.alpha ?? 0) >= 0 ? "gain" : "loss"}
                    />
                    <MetricRow label="Observations" value={String(metrics.observations)} />
                    <MetricRow label="Portfolio Value" value={money(metrics.portfolio_value)} />
                  </dl>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      ) : null}
    </div>
  );
}

function qualify(value: number, [poor, good, great]: [number, number, number]): string {
  if (value >= great) return "Excellent";
  if (value >= good) return "Good";
  if (value >= poor) return "Acceptable";
  return "Poor";
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss" | "flat";
}) {
  return (
    <div>
      <dt className="stat-label">{label}</dt>
      <dd
        className={cn(
          "tabular mt-1 text-sm font-semibold",
          tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function MetricRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss";
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-2">
      <dt className="text-xs text-ink-subtle">{label}</dt>
      <dd
        className={cn(
          "tabular text-xs font-medium",
          tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function VarRow({
  label,
  value,
  amount,
  hint,
  emphasis,
}: {
  label: string;
  value: number;
  amount: string;
  hint: string;
  emphasis?: boolean;
}) {
  return (
    <Tooltip content={hint}>
      <div
        className={cn(
          "flex cursor-default items-baseline justify-between gap-3 rounded-lg px-2 py-1.5",
          emphasis && "bg-loss/8",
        )}
      >
        <dt className={cn("text-xs", emphasis ? "font-medium text-loss" : "text-ink-subtle")}>
          {label}
        </dt>
        <dd className="text-right">
          <span className="tabular block text-xs font-medium text-ink">{amount}</span>
          <span className="tabular block text-2xs text-ink-faint">
            {formatPercent(value, { signed: false })}
          </span>
        </dd>
      </div>
    </Tooltip>
  );
}
