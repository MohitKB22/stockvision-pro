"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError, get, post } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type {
  ForecastResponse,
  ModelAlgorithm,
  ModelPublic,
  ModelTask,
  PredictionHistoryEntry,
  PredictionResponse,
  SignalResponse,
  TrainModelResponse,
} from "@/types";

export function useModels() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: () => get<ModelPublic[]>("/models", { limit: 100 }),
    staleTime: 60_000,
  });
}

export function useForecast(symbol: string | undefined, horizonDays = 5) {
  return useQuery({
    queryKey: queryKeys.forecast(symbol ?? "", horizonDays),
    queryFn: () =>
      get<ForecastResponse>(`/predictions/${symbol}/forecast`, { horizon_days: horizonDays }),
    enabled: Boolean(symbol),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function usePredictionHistory(symbol: string | undefined) {
  return useQuery({
    queryKey: queryKeys.predictionHistory(symbol ?? ""),
    queryFn: () => get<PredictionHistoryEntry[]>(`/predictions/${symbol}/history`, { limit: 100 }),
    enabled: Boolean(symbol),
    retry: false,
    staleTime: 60_000,
  });
}

export function useRecentSignals(limit = 12) {
  return useQuery({
    queryKey: queryKeys.recentSignals(limit),
    queryFn: () => get<SignalResponse[]>("/signals/recent", { limit }),
    staleTime: 60_000,
  });
}

export function usePredict() {
  return useMutation({
    mutationFn: (payload: { symbol: string; task?: ModelTask }) =>
      post<PredictionResponse>("/predictions", {
        symbol: payload.symbol,
        task: payload.task ?? "trend_classification",
      }),
    onError: (error: ApiError) => {
      // "No model trained yet" is an expected first-run state, not a failure — it
      // gets a neutral prompt to train one, not a red error toast.
      if (error.code === "model_not_trained") {
        toast.info("No trained model yet", { description: error.message });
        return;
      }
      toast.error("Prediction failed", { description: error.message });
    },
  });
}

export function useGenerateSignal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => post<SignalResponse>(`/signals/${symbol}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ml", "signals"] }),
    onError: (error: ApiError) =>
      toast.error("Signal generation failed", { description: error.message }),
  });
}

/** Bulk signal generation — one request for a whole panel of symbols. */
export function useGenerateSignalsBulk() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (symbols: string[]) => post<SignalResponse[]>("/signals", { symbols }),
    onSuccess: (signals) => {
      toast.success(`Generated ${signals.length} signal${signals.length === 1 ? "" : "s"}`);
      queryClient.invalidateQueries({ queryKey: ["ml", "signals"] });
    },
    onError: (error: ApiError) =>
      toast.error("Signal generation failed", { description: error.message }),
  });
}

export function useTrainModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      symbol: string;
      task: ModelTask;
      algorithm: ModelAlgorithm;
      n_optuna_trials: number;
      n_walk_forward_splits: number;
    }) => post<TrainModelResponse>("/models/train", payload),
    onSuccess: (result) => {
      toast.success(`Trained ${result.name} v${result.version}`, {
        description: `Accuracy ${((result.metrics.accuracy ?? 0) * 100).toFixed(1)}% · F1 ${(result.metrics.f1 ?? 0).toFixed(3)}`,
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.models });
      queryClient.invalidateQueries({ queryKey: ["ml"] });
    },
    onError: (error: ApiError) => toast.error("Training failed", { description: error.message }),
  });
}

export function usePromoteModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (modelId: string) => post<ModelPublic>(`/models/${modelId}/promote`),
    onSuccess: (model) => {
      toast.success(`${model.name} v${model.version} promoted to production`);
      queryClient.invalidateQueries({ queryKey: queryKeys.models });
    },
    onError: (error: ApiError) => toast.error("Promotion failed", { description: error.message }),
  });
}
