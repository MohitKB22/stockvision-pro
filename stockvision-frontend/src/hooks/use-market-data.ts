"use client";

import { useQuery } from "@tanstack/react-query";

import { useMarket } from "@/context/market-context";
import { get } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type {
  HeatmapEntry,
  IndexQuote,
  MarketBreadth,
  MarketOverview,
  MoversResponse,
  SectorPerformance,
  StockQuote,
  WeekRangeResponse,
} from "@/types";

/**
 * Market data hooks.
 *
 * Every hook reads the active market from context rather than taking it as a
 * parameter, so a page cannot accidentally request US data while the switcher says
 * India. The market is part of every query key, so switching markets swaps caches
 * instantly instead of briefly showing the previous market's numbers.
 */

/** Quotes move; 30s of staleness with a 60s refetch is the balance between
 *  freshness and hammering the API for a page nobody is looking at. */
const LIVE = { staleTime: 30_000, refetchInterval: 60_000 } as const;

export function useMarketOverview(moverLimit = 6) {
  const { market } = useMarket();
  return useQuery({
    queryKey: [...queryKeys.overview(market), moverLimit],
    queryFn: () => get<MarketOverview>("/market/overview", { market, mover_limit: moverLimit }),
    ...LIVE,
  });
}

export function useIndices() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.indices(market),
    queryFn: () => get<IndexQuote[]>("/market/indices", { market }),
    ...LIVE,
  });
}

export function useIndexConstituents(indexSymbol: string | undefined) {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.indexConstituents(market, indexSymbol ?? ""),
    queryFn: () => get<StockQuote[]>(`/market/indices/${indexSymbol}/constituents`, { market }),
    enabled: Boolean(indexSymbol),
    ...LIVE,
  });
}

export function useMovers(limit = 10) {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.movers(market, limit),
    queryFn: () => get<MoversResponse>("/market/movers", { market, limit }),
    ...LIVE,
  });
}

export function useSectors() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.sectors(market),
    queryFn: () => get<SectorPerformance[]>("/market/sectors", { market }),
    ...LIVE,
  });
}

export function useHeatmap() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.heatmap(market),
    queryFn: () => get<HeatmapEntry[]>("/market/heatmap", { market }),
    ...LIVE,
  });
}

export function useBreadth() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.breadth(market),
    queryFn: () => get<MarketBreadth>("/market/breadth", { market }),
    ...LIVE,
  });
}

export function useWeekRange(limit = 10) {
  const { market } = useMarket();
  return useQuery({
    queryKey: [...queryKeys.weekRange(market), limit],
    queryFn: () => get<WeekRangeResponse>("/market/52-week", { market, limit }),
    staleTime: 5 * 60_000,
  });
}

/** Batch quotes — one request for N symbols. Disabled on an empty list so an
 *  unresolved dependency does not fire a pointless request. */
export function useQuotes(symbols: string[]) {
  return useQuery({
    queryKey: queryKeys.quotes(symbols),
    queryFn: () => get<StockQuote[]>("/market/quotes", { symbols: symbols.join(",") }),
    enabled: symbols.length > 0,
    ...LIVE,
  });
}

export function useQuote(symbol: string | undefined) {
  return useQuery({
    queryKey: queryKeys.quote(symbol ?? ""),
    queryFn: () => get<StockQuote>(`/market/quotes/${symbol}`),
    enabled: Boolean(symbol),
    ...LIVE,
  });
}
