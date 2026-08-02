"use client";

import { createContext, useContext, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { usePersistentState } from "@/hooks/use-persistent-state";
import { get } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { DigitGrouping, MarketCode, MarketDefinition } from "@/types";

interface MarketContextValue {
  market: MarketCode;
  setMarket: (market: MarketCode) => void;
  definition: MarketDefinition | undefined;
  definitions: MarketDefinition[];
  currencySymbol: string;
  grouping: DigitGrouping;
  isLoading: boolean;
}

const MarketContext = createContext<MarketContextValue | null>(null);

const STORAGE_KEY = "stockvision.market";

function isMarketCode(value: string): value is MarketCode {
  return value === "IN" || value === "US";
}

/**
 * Market selection, shared app-wide.
 *
 * The definitions (currency symbol, digit grouping, index list) come from
 * GET /markets rather than being duplicated in the frontend — that duplication is
 * exactly how a UI ends up rendering ₹ against US prices after someone edits one
 * side and not the other.
 *
 * Selection persists via `usePersistentState`, which is built on
 * `useSyncExternalStore`: the stored value is read during render on the client,
 * the server renders the default (no hydration mismatch), and the market stays in
 * sync across browser tabs.
 */
export function MarketProvider({ children }: { children: React.ReactNode }) {
  const [market, setMarket] = usePersistentState<MarketCode>(STORAGE_KEY, "IN", isMarketCode);

  const { data: definitions = [], isLoading } = useQuery({
    queryKey: queryKeys.markets,
    queryFn: () => get<MarketDefinition[]>("/markets"),
    // Market definitions are code-level configuration on the server and cannot
    // change within a deploy — refetching them is pure waste.
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const value = useMemo<MarketContextValue>(() => {
    const definition = definitions.find((d) => d.code === market);
    return {
      market,
      setMarket,
      definition,
      definitions,
      currencySymbol: definition?.currency_symbol ?? (market === "IN" ? "₹" : "$"),
      grouping: definition?.digit_grouping ?? (market === "IN" ? "indian" : "western"),
      isLoading,
    };
  }, [market, setMarket, definitions, isLoading]);

  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>;
}

export function useMarket(): MarketContextValue {
  const context = useContext(MarketContext);
  if (!context) throw new Error("useMarket must be used inside <MarketProvider>");
  return context;
}
