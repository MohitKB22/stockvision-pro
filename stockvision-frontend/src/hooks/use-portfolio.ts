"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useMarket } from "@/context/market-context";
import { ApiError, del, get, patch, post } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type {
  OperationResult,
  PerformancePoint,
  Portfolio,
  PortfolioSummary,
  Transaction,
} from "@/types";

export function usePortfolios() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.portfolios(market),
    queryFn: () => get<Portfolio[]>("/portfolios", { market }),
    staleTime: 60_000,
  });
}

/**
 * The portfolio the dashboard opens with.
 *
 * `retry: false` because a 404 here is the legitimate "no portfolio exists yet"
 * state that the UI renders as an onboarding prompt — retrying it twice with
 * backoff just delays that prompt by several seconds.
 */
export function useDefaultPortfolio() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.defaultPortfolio(market),
    queryFn: () => get<Portfolio>("/portfolios/default", { market }),
    retry: false,
    staleTime: 60_000,
  });
}

export function usePortfolioSummary(portfolioId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.portfolioSummary(portfolioId ?? ""),
    queryFn: () => get<PortfolioSummary>(`/portfolios/${portfolioId}/summary`),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function usePortfolioPerformance(portfolioId: string | undefined, days = 180) {
  return useQuery({
    queryKey: queryKeys.portfolioPerformance(portfolioId ?? "", days),
    queryFn: () => get<PerformancePoint[]>(`/portfolios/${portfolioId}/performance`, { days }),
    enabled: Boolean(portfolioId),
    staleTime: 60_000,
  });
}

export function useTransactions(portfolioId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.portfolioTransactions(portfolioId ?? ""),
    queryFn: () => get<Transaction[]>(`/portfolios/${portfolioId}/transactions`, { limit: 500 }),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
  });
}

export function useCreatePortfolio() {
  const queryClient = useQueryClient();
  const { market } = useMarket();
  return useMutation({
    mutationFn: (payload: { name: string; cash_balance?: number }) =>
      post<Portfolio>("/portfolios", { ...payload, market }),
    onSuccess: (portfolio) => {
      toast.success("Portfolio created", { description: portfolio.name });
      queryClient.invalidateQueries({ queryKey: queryKeys.portfolios(market) });
      queryClient.invalidateQueries({ queryKey: queryKeys.defaultPortfolio(market) });
    },
    onError: (error: ApiError) =>
      toast.error("Could not create portfolio", { description: error.message }),
  });
}

export function useUpdatePortfolio(portfolioId: string) {
  const queryClient = useQueryClient();
  const { market } = useMarket();
  return useMutation({
    mutationFn: (
      payload: Partial<
        Pick<Portfolio, "name" | "benchmark_symbol" | "cash_balance" | "is_default">
      >,
    ) => patch<Portfolio>(`/portfolios/${portfolioId}`, payload),
    onSuccess: () => {
      toast.success("Portfolio updated");
      queryClient.invalidateQueries({ queryKey: queryKeys.portfolios(market) });
      queryClient.invalidateQueries({ queryKey: queryKeys.portfolio(portfolioId) });
    },
    onError: (error: ApiError) => toast.error("Update failed", { description: error.message }),
  });
}

export function useDeletePortfolio() {
  const queryClient = useQueryClient();
  const { market } = useMarket();
  return useMutation({
    mutationFn: (portfolioId: string) => del<OperationResult>(`/portfolios/${portfolioId}`),
    onSuccess: () => {
      toast.success("Portfolio deleted");
      queryClient.invalidateQueries({ queryKey: queryKeys.portfolios(market) });
      queryClient.invalidateQueries({ queryKey: queryKeys.defaultPortfolio(market) });
    },
    onError: (error: ApiError) => toast.error("Delete failed", { description: error.message }),
  });
}

export function useSubmitOrder(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      symbol: string;
      side: "buy" | "sell";
      quantity: number;
      price: number;
      transaction_cost?: number;
      notes?: string;
    }) => post<OperationResult>(`/portfolios/${portfolioId}/orders`, payload),
    onSuccess: (result) => {
      toast.success(result.message);
      // Every derived view of this portfolio is now stale. Invalidating the whole
      // subtree is correct and cheap — the alternative (listing each dependent
      // key) is exactly where invalidation bugs come from.
      queryClient.invalidateQueries({ queryKey: queryKeys.portfolio(portfolioId) });
    },
    onError: (error: ApiError) => toast.error("Order rejected", { description: error.message }),
  });
}
