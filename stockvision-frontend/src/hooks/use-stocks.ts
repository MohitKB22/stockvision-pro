"use client";

import { useQuery } from "@tanstack/react-query";

import { useMarket } from "@/context/market-context";
import { get } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { FeatureSnapshot, PriceBar, StockPublic } from "@/types";

export function useStocks(sector?: string) {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.stocks(market, sector),
    queryFn: () => get<StockPublic[]>("/stocks", { market, sector, limit: 500 }),
    staleTime: 5 * 60_000,
  });
}

export function useStock(symbol: string | undefined) {
  return useQuery({
    queryKey: queryKeys.stock(symbol ?? ""),
    queryFn: () => get<StockPublic>(`/stocks/${symbol}`),
    enabled: Boolean(symbol),
    staleTime: 10 * 60_000,
  });
}

export function usePrices(symbol: string | undefined, limit = 250) {
  return useQuery({
    queryKey: queryKeys.prices(symbol ?? "", limit),
    queryFn: () => get<PriceBar[]>(`/stocks/${symbol}/prices`, { limit }),
    enabled: Boolean(symbol),
    staleTime: 60_000,
  });
}

export function useFeatures(symbol: string | undefined, limit = 200) {
  return useQuery({
    queryKey: queryKeys.features(symbol ?? "", limit),
    queryFn: () => get<FeatureSnapshot[]>(`/stocks/${symbol}/features`, { limit }),
    enabled: Boolean(symbol),
    staleTime: 60_000,
  });
}

export function useStockSectors() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.stockSectors(market),
    queryFn: () => get<string[]>("/stocks/sectors", { market }),
    staleTime: Infinity,
  });
}
