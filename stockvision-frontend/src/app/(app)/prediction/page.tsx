"use client";

import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Brain, CircleCheck, CircleX, Cpu, Sparkles, TrendingUp } from "lucide-react";

import { useMarket } from "@/context/market-context";
import {
  useForecast,
  useGenerateSignal,
  useModels,
  usePredict,
  usePredictionHistory,
  usePromoteModel,
  useTrainModel,
} from "@/hooks/use-ml";
import { useStocks } from "@/hooks/use-stocks";
import { MODEL_ALGORITHMS, MODEL_TASKS, SIGNAL_META } from "@/lib/constants";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ModelAlgorithm, ModelPublic, ModelTask, ShapContribution } from "@/types";
import { TimeSeriesChart } from "@/components/charts/area-chart";
import { Gauge } from "@/components/charts/gauge";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Input, Label } from "@/components/ui/input";
import { Progress, Tooltip } from "@/components/ui/misc";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonChart, SkeletonTable } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";

export default function PredictionPage() {
  const { grouping, currencySymbol } = useMarket();
  const stocksQuery = useStocks();
  const [selectedSymbol, setSelectedSymbol] = React.useState<string | null>(null);
  const [horizon, setHorizon] = React.useState("5");

  // DERIVED, not synchronised: the effective symbol is the user's explicit choice,
  // falling back to the first listed stock once the list loads. The alternative —
  // an effect that copies the first symbol into state — renders twice on load and
  // is what React 19's compiler flags as a cascading render.
  const symbol = selectedSymbol ?? stocksQuery.data?.[0]?.symbol ?? "";

  const forecastQuery = useForecast(symbol || undefined, Number(horizon));
  const historyQuery = usePredictionHistory(symbol || undefined);
  const modelsQuery = useModels();
  const predict = usePredict();
  const generateSignal = useGenerateSignal();

  const forecast = forecastQuery.data;
  const prediction = predict.data;
  const signal = generateSignal.data;

  const accuracy = React.useMemo(() => {
    const scored = (historyQuery.data ?? []).filter((entry) => entry.correct !== null);
    if (!scored.length) return null;
    return {
      rate: scored.filter((entry) => entry.correct).length / scored.length,
      count: scored.length,
    };
  }, [historyQuery.data]);

  const chartSeries = React.useMemo(() => {
    if (!forecast) return [];
    return [
      ...forecast.historical.map((point) => ({
        label: formatDate(point.timestamp, "short"),
        value: point.close,
      })),
      ...forecast.forecast.map((point) => ({ label: `+${point.day}d`, value: point.expected })),
    ];
  }, [forecast]);

  const modelColumns = React.useMemo<ColumnDef<ModelPublic>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Model",
        cell: ({ row }) => (
          <span className="text-xs font-medium text-ink">{row.original.name}</span>
        ),
      },
      {
        accessorKey: "version",
        header: "Ver",
        cell: ({ row }) => <span className="tabular text-xs">v{row.original.version}</span>,
      },
      {
        accessorKey: "algorithm",
        header: "Algorithm",
        cell: ({ row }) => <Badge variant="outline">{row.original.algorithm}</Badge>,
      },
      {
        accessorKey: "stage",
        header: "Stage",
        cell: ({ row }) => (
          <Badge
            variant={
              row.original.stage === "production"
                ? "gain"
                : row.original.stage === "staging"
                  ? "info"
                  : "default"
            }
          >
            {row.original.stage}
          </Badge>
        ),
      },
      {
        id: "accuracy",
        header: "Accuracy",
        accessorFn: (row) => row.metrics?.accuracy ?? 0,
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink">
            {row.original.metrics?.accuracy
              ? formatPercent(row.original.metrics.accuracy, { signed: false, decimals: 1 })
              : "—"}
          </span>
        ),
      },
      {
        id: "f1",
        header: "F1",
        accessorFn: (row) => row.metrics?.f1 ?? 0,
        cell: ({ row }) => (
          <span className="tabular text-xs text-ink-muted">
            {row.original.metrics?.f1?.toFixed(3) ?? "—"}
          </span>
        ),
      },
      {
        accessorKey: "trained_at",
        header: "Trained",
        cell: ({ row }) => (
          <span className="text-2xs text-ink-faint">
            {formatDate(row.original.trained_at, "datetime")}
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => <PromoteButton model={row.original} />,
      },
    ],
    [],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI Prediction"
        description="Price forecasts, model registry and SHAP feature attributions"
        actions={
          <>
            <Select value={symbol} onValueChange={setSelectedSymbol}>
              <SelectTrigger className="w-[188px]">
                <SelectValue placeholder="Select a symbol" />
              </SelectTrigger>
              <SelectContent>
                {(stocksQuery.data ?? []).map((stock) => (
                  <SelectItem key={stock.id} value={stock.symbol}>
                    {stock.symbol} — {stock.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="primary"
              size="sm"
              loading={predict.isPending}
              onClick={() => symbol && predict.mutate({ symbol })}
            >
              <Brain aria-hidden /> Predict
            </Button>
          </>
        }
      />

      <section className="grid gap-4 lg:grid-cols-3">
        {/* --- Recommendation --- */}
        <Card className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 bg-gradient-glow" aria-hidden />
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Sparkles className="size-3.5 text-accent" aria-hidden />
              AI Recommendation
            </CardTitle>
          </CardHeader>
          <CardContent className="relative">
            {signal ? (
              <>
                <p
                  className={cn(
                    "text-3xl font-bold tracking-tight",
                    SIGNAL_META[signal.action].tone === "gain"
                      ? "text-gain"
                      : SIGNAL_META[signal.action].tone === "loss"
                        ? "text-loss"
                        : "text-ink",
                  )}
                >
                  {SIGNAL_META[signal.action].label}
                </p>
                <p className="mt-1 text-xs text-ink-subtle">{signal.explanation}</p>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <p className="stat-label">Confidence</p>
                    <Progress value={signal.confidence * 100} className="mt-1.5" />
                    <p className="tabular mt-1 text-xs text-ink">
                      {formatPercent(signal.confidence, { signed: false })}
                    </p>
                  </div>
                  <div>
                    <p className="stat-label">Risk score</p>
                    <Progress
                      value={signal.risk_score * 100}
                      className="mt-1.5"
                      indicatorClassName={
                        signal.risk_score > 0.66
                          ? "bg-loss"
                          : signal.risk_score > 0.33
                            ? "bg-warn"
                            : "bg-gain"
                      }
                    />
                    <p className="tabular mt-1 text-xs text-ink">{signal.risk_score.toFixed(2)}</p>
                  </div>
                </div>
              </>
            ) : (
              <EmptyState
                icon={Sparkles}
                title="No signal generated"
                description="Generate a signal to blend technical indicators with the trained model's probability."
                action={
                  <Button
                    variant="primary"
                    size="sm"
                    loading={generateSignal.isPending}
                    onClick={() => symbol && generateSignal.mutate(symbol)}
                  >
                    Generate signal for {symbol || "…"}
                  </Button>
                }
              />
            )}
          </CardContent>
        </Card>

        {/* --- Prediction engine --- */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Prediction Engine</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                {forecast?.model_informed
                  ? "Forecast drift is informed by the trained classifier"
                  : "No trained model for this symbol — the projection is an unconditional random walk"}
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {forecastQuery.isLoading ? (
              <SkeletonChart />
            ) : forecastQuery.isError ? (
              <ErrorState error={forecastQuery.error} onRetry={() => forecastQuery.refetch()} />
            ) : forecast ? (
              <>
                <div className="grid gap-4 sm:grid-cols-4">
                  <div className="flex flex-col items-center">
                    <Gauge
                      value={prediction?.confidence ?? forecast.probability_up ?? 0.5}
                      label="Confidence"
                      tone={prediction ? "auto" : "primary"}
                    />
                  </div>
                  <MetricTile
                    label="Expected Return"
                    value={formatPercent(forecast.expected_return_pct)}
                    sub={`In ${forecast.horizon_days} sessions`}
                    tone={forecast.expected_return_pct >= 0 ? "gain" : "loss"}
                  />
                  <MetricTile
                    label="Probability (Bullish)"
                    value={
                      forecast.probability_up === null
                        ? "—"
                        : formatPercent(forecast.probability_up, { signed: false })
                    }
                    sub={forecast.model_informed ? "From the trained model" : "No model available"}
                  />
                  <MetricTile
                    label="Risk Level"
                    value={
                      forecast.annualized_volatility > 0.4
                        ? "High"
                        : forecast.annualized_volatility > 0.22
                          ? "Medium"
                          : "Low"
                    }
                    sub={`${formatPercent(forecast.annualized_volatility, { signed: false })} annualized vol`}
                    tone={
                      forecast.annualized_volatility > 0.4
                        ? "loss"
                        : forecast.annualized_volatility > 0.22
                          ? undefined
                          : "gain"
                    }
                  />
                </div>

                <div className="mt-5">
                  <div className="mb-1 flex items-baseline justify-between">
                    <p className="text-xs font-medium text-ink-muted">
                      Price Forecast ({forecast.horizon_days} sessions)
                    </p>
                    <Select value={horizon} onValueChange={setHorizon}>
                      <SelectTrigger className="h-7 w-[96px] text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {["5", "10", "21", "42"].map((days) => (
                          <SelectItem key={days} value={days}>
                            {days} days
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <TimeSeriesChart
                    data={chartSeries}
                    height={220}
                    tone={forecast.expected_return_pct >= 0 ? "gain" : "loss"}
                    valueFormatter={(value) => formatNumber(value, { grouping, decimals: 0 })}
                    referenceValue={forecast.last_price}
                  />
                  <p className="mt-2 text-2xs text-ink-faint">
                    Dashed line is the last traded price ({currencySymbol}
                    {formatNumber(forecast.last_price, { grouping })}). The 95% confidence band
                    widens with √t.
                  </p>
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <Tabs defaultValue="features">
        <TabsList className="flex-wrap">
          <TabsTrigger value="features">Feature Importance</TabsTrigger>
          <TabsTrigger value="history">Prediction History</TabsTrigger>
          <TabsTrigger value="registry">Model Registry</TabsTrigger>
          <TabsTrigger value="train">Train a Model</TabsTrigger>
        </TabsList>

        <TabsContent value="features">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>SHAP Feature Attributions</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  Signed contribution of each indicator to this specific prediction
                </p>
              </div>
            </CardHeader>
            <CardContent>
              {!prediction?.shap_contributions.length ? (
                <EmptyState
                  icon={Cpu}
                  title="No prediction to explain yet"
                  description="Run a prediction to see which indicators drove it, and in which direction."
                  action={
                    <Button
                      variant="primary"
                      size="sm"
                      loading={predict.isPending}
                      onClick={() => symbol && predict.mutate({ symbol })}
                    >
                      Run prediction
                    </Button>
                  }
                />
              ) : (
                <ShapChart contributions={prediction.shap_contributions} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Historical Predictions</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  Scored against what the price actually did next
                </p>
              </div>
              {accuracy ? (
                <Badge
                  variant={accuracy.rate >= 0.55 ? "gain" : accuracy.rate >= 0.45 ? "warn" : "loss"}
                >
                  {formatPercent(accuracy.rate, { signed: false, decimals: 1 })} over{" "}
                  {accuracy.count} verified
                </Badge>
              ) : null}
            </CardHeader>
            <CardContent>
              {historyQuery.isLoading ? (
                <SkeletonTable rows={6} columns={5} />
              ) : !historyQuery.data?.length ? (
                <EmptyState
                  title="No prediction history"
                  description="Predictions you run are recorded and scored here."
                />
              ) : (
                <ul className="space-y-1">
                  {historyQuery.data.slice(0, 20).map((entry) => (
                    <li
                      key={entry.id}
                      className="flex items-center gap-3 rounded-lg border border-line/60 px-3 py-2"
                    >
                      {entry.correct === null ? (
                        <Tooltip content="No subsequent session yet — deliberately not counted as correct">
                          <span className="size-4 shrink-0 rounded-full border border-dashed border-ink-faint" />
                        </Tooltip>
                      ) : entry.correct ? (
                        <CircleCheck className="size-4 shrink-0 text-gain" aria-hidden />
                      ) : (
                        <CircleX className="size-4 shrink-0 text-loss" aria-hidden />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs text-ink">
                          {entry.predicted_value >= 0.5 ? "Predicted UP" : "Predicted DOWN"}
                          <span className="tabular ml-2 text-ink-faint">
                            p={entry.predicted_value.toFixed(3)}
                          </span>
                        </span>
                        <span className="block text-2xs text-ink-faint">
                          {entry.model_name} v{entry.model_version} ·{" "}
                          {formatDate(entry.generated_at, "datetime")}
                        </span>
                      </span>
                      <span className="tabular shrink-0 text-2xs text-ink-muted">
                        {formatPercent(entry.confidence, { signed: false, decimals: 0 })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="registry">
          <Card>
            <CardContent className="pt-5">
              {modelsQuery.isLoading ? (
                <SkeletonTable rows={5} columns={8} />
              ) : (
                <DataTable
                  columns={modelColumns}
                  data={modelsQuery.data ?? []}
                  emptyTitle="No models trained"
                  emptyDescription="Train a model from the next tab to populate the registry."
                  dense
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="train">
          <TrainingPanel symbol={symbol} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function MetricTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "gain" | "loss";
}) {
  return (
    <div>
      <p className="stat-label">{label}</p>
      <p
        className={cn(
          "tabular mt-1 text-lg font-semibold",
          tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink",
        )}
      >
        {value}
      </p>
      {sub ? <p className="mt-0.5 text-2xs text-ink-faint">{sub}</p> : null}
    </div>
  );
}

/** Horizontal diverging bar chart of SHAP values — the standard way to read a
 *  single prediction's attributions, with positive and negative contributions on
 *  opposite sides of a shared zero line. */
function ShapChart({ contributions }: { contributions: ShapContribution[] }) {
  const sorted = [...contributions]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 12);
  const max = Math.max(...sorted.map((entry) => Math.abs(entry.contribution)), 1e-6);

  return (
    <ul className="space-y-2">
      {sorted.map((entry) => {
        const width = (Math.abs(entry.contribution) / max) * 46;
        const positive = entry.contribution >= 0;
        return (
          <li key={entry.feature}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-2xs">
              <span className="truncate font-medium text-ink-muted">{entry.feature}</span>
              <span className="flex shrink-0 gap-3">
                <span className="tabular text-ink-faint">value {entry.value.toFixed(3)}</span>
                <span className={cn("tabular font-medium", positive ? "text-gain" : "text-loss")}>
                  {entry.contribution >= 0 ? "+" : ""}
                  {entry.contribution.toFixed(4)}
                </span>
              </span>
            </div>
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
          </li>
        );
      })}
    </ul>
  );
}

function PromoteButton({ model }: { model: ModelPublic }) {
  const promote = usePromoteModel();
  if (model.stage === "production") return <span className="text-2xs text-ink-faint">Serving</span>;
  return (
    <Button
      variant="ghost"
      size="xs"
      loading={promote.isPending}
      onClick={() => promote.mutate(model.id)}
    >
      Promote
    </Button>
  );
}

function TrainingPanel({ symbol }: { symbol: string }) {
  const trainModel = useTrainModel();
  const [task, setTask] = React.useState<ModelTask>("trend_classification");
  const [algorithm, setAlgorithm] = React.useState<ModelAlgorithm>("xgboost");
  const [trials, setTrials] = React.useState("15");
  const [splits, setSplits] = React.useState("5");

  const selectedTask = MODEL_TASKS.find((entry) => entry.value === task);
  const result = trainModel.data;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Train a Model Version</CardTitle>
          <p className="mt-0.5 text-2xs text-ink-faint">
            Walk-forward cross-validation with Optuna hyperparameter search and SHAP importances
          </p>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="train-task">Task</Label>
            <Select value={task} onValueChange={(value) => setTask(value as ModelTask)}>
              <SelectTrigger id="train-task" className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_TASKS.map((entry) => (
                  <SelectItem key={entry.value} value={entry.value}>
                    {entry.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="train-algorithm">Algorithm</Label>
            <Select
              value={algorithm}
              onValueChange={(value) => setAlgorithm(value as ModelAlgorithm)}
            >
              <SelectTrigger id="train-algorithm" className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_ALGORITHMS.map((entry) => (
                  <SelectItem key={entry.value} value={entry.value}>
                    {entry.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="train-trials">Optuna trials</Label>
            <Input
              id="train-trials"
              type="number"
              min="1"
              max="200"
              className="mt-1"
              value={trials}
              onChange={(event) => setTrials(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="train-splits">Walk-forward splits</Label>
            <Input
              id="train-splits"
              type="number"
              min="2"
              max="20"
              className="mt-1"
              value={splits}
              onChange={(event) => setSplits(event.target.value)}
            />
          </div>
        </div>

        {selectedTask ? (
          <p className="mt-3 text-2xs text-ink-faint">{selectedTask.description}</p>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            disabled={!symbol}
            loading={trainModel.isPending}
            onClick={() =>
              trainModel.mutate({
                symbol,
                task,
                algorithm,
                n_optuna_trials: Number(trials),
                n_walk_forward_splits: Number(splits),
              })
            }
          >
            <TrendingUp aria-hidden /> Train on {symbol || "…"}
          </Button>
          <p className="text-2xs text-ink-faint">
            Training runs synchronously and takes several seconds — the request will not return
            until it finishes.
          </p>
        </div>

        {result ? (
          <div className="bg-gain/8 mt-5 rounded-xl border border-gain/25 p-4">
            <p className="text-xs font-medium text-gain">
              Trained {result.name} v{result.version}
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MetricTile
                label="Accuracy"
                value={formatPercent(result.metrics.accuracy ?? 0, { signed: false, decimals: 1 })}
              />
              <MetricTile label="F1" value={(result.metrics.f1 ?? 0).toFixed(3)} />
              <MetricTile label="ROC AUC" value={(result.metrics.roc_auc ?? 0).toFixed(3)} />
              <MetricTile label="Train samples" value={String(result.metrics.n_train_samples)} />
            </dl>
            {result.top_features.length ? (
              <div className="mt-4">
                <p className="stat-label mb-2">Top features by mean |SHAP|</p>
                <ul className="space-y-1.5">
                  {result.top_features.slice(0, 6).map((feature) => (
                    <li key={feature.feature} className="flex items-center gap-2 text-2xs">
                      <span className="w-28 truncate text-ink-muted">{feature.feature}</span>
                      <Progress
                        value={
                          (feature.mean_abs_shap / (result.top_features[0]?.mean_abs_shap || 1)) *
                          100
                        }
                        className="h-1 flex-1"
                      />
                      <span className="tabular w-14 text-right text-ink-faint">
                        {feature.mean_abs_shap.toFixed(4)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
