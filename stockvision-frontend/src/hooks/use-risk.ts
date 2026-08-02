"use client";

import { useQuery } from "@tanstack/react-query";

import { get } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { CorrelationMatrix, MonteCarloResult, RiskMetrics, StressTestResult } from "@/types";

export function useRiskMetrics(portfolioId: string | undefined, lookbackDays = 252) {
  return useQuery({
    queryKey: queryKeys.risk(portfolioId ?? "", lookbackDays),
    queryFn: () =>
      get<RiskMetrics>(`/portfolios/${portfolioId}/risk`, { lookback_days: lookbackDays }),
    enabled: Boolean(portfolioId),
    // "No holdings" is a legitimate 422 the UI renders as an empty state.
    retry: false,
    staleTime: 60_000,
  });
}

export function useMonteCarlo(
  portfolioId: string | undefined,
  horizonDays = 252,
  nSimulations = 1000,
) {
  return useQuery({
    queryKey: queryKeys.monteCarlo(portfolioId ?? "", horizonDays, nSimulations),
    queryFn: () =>
      get<MonteCarloResult>(`/portfolios/${portfolioId}/risk/monte-carlo`, {
        horizon_days: horizonDays,
        n_simulations: nSimulations,
      }),
    enabled: Boolean(portfolioId),
    retry: false,
    // The simulation is seeded and therefore deterministic for a given portfolio —
    // refetching produces byte-identical output. Cache it longer.
    staleTime: 5 * 60_000,
  });
}

export function useCorrelation(portfolioId: string | undefined, lookbackDays = 252) {
  return useQuery({
    queryKey: queryKeys.correlation(portfolioId ?? "", lookbackDays),
    queryFn: () =>
      get<CorrelationMatrix>(`/portfolios/${portfolioId}/risk/correlation`, {
        lookback_days: lookbackDays,
      }),
    enabled: Boolean(portfolioId),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export function useStressTest(portfolioId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.stressTest(portfolioId ?? ""),
    queryFn: () => get<StressTestResult>(`/portfolios/${portfolioId}/risk/stress-test`),
    enabled: Boolean(portfolioId),
    retry: false,
    staleTime: 5 * 60_000,
  });
}
