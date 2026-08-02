"use client";

import { Globe } from "lucide-react";

import { useMarket } from "@/context/market-context";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { MarketCode } from "@/types";

/**
 * Market selector.
 *
 * Options come from the API's market registry, so adding a third market
 * server-side makes it appear here with no frontend change. The literal fallback
 * exists only for the first paint before /markets resolves.
 */
export function MarketSwitcher({ compact = false }: { compact?: boolean }) {
  const { market, setMarket, definitions } = useMarket();

  const options = definitions.length
    ? definitions
    : [
        { code: "IN" as MarketCode, name: "India", currency_symbol: "₹", exchange: "NSE" },
        {
          code: "US" as MarketCode,
          name: "United States",
          currency_symbol: "$",
          exchange: "NASDAQ",
        },
      ];

  return (
    <Select value={market} onValueChange={(value) => setMarket(value as MarketCode)}>
      <SelectTrigger
        className={compact ? "h-8 w-[104px] text-xs" : "h-9 w-[168px]"}
        aria-label="Select market"
      >
        <span className="flex items-center gap-2 truncate">
          <Globe className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
          <SelectValue />
        </span>
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.code} value={option.code}>
            <span className="flex items-center gap-2">
              <span className="font-medium">{option.code}</span>
              <span className="text-ink-faint">
                {compact ? option.currency_symbol : `${option.name} · ${option.exchange}`}
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
