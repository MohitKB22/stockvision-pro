"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Search, TrendingUp } from "lucide-react";

import { useMarket } from "@/context/market-context";
import { get } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/navigation";
import { queryKeys } from "@/lib/query-keys";
import type { StockPublic } from "@/types";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

/**
 * Global command palette (⌘K / Ctrl+K).
 *
 * Symbol results come from the API's search endpoint behind a debounce, so typing
 * does not fire a request per keystroke. Navigation entries come from the same
 * NAV_ITEMS the sidebar uses, so the two can never disagree.
 */
export function SearchCommand() {
  const router = useRouter();
  const { market } = useMarket();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((previous) => !previous);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 220);
    return () => clearTimeout(timer);
  }, [query]);

  const { data: symbols = [] } = useQuery({
    queryKey: queryKeys.stockSearch(debounced, market),
    queryFn: () => get<StockPublic[]>("/stocks/search", { q: debounced, market, limit: 8 }),
    enabled: open && debounced.length > 0,
    staleTime: 60_000,
  });

  const go = React.useCallback(
    (href: string) => {
      setOpen(false);
      setQuery("");
      router.push(href);
    },
    [router],
  );

  const groupHeadingClass =
    "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-ink-faint";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-9 items-center gap-2 rounded-lg border border-line bg-elevated/60 px-3 text-xs text-ink-faint transition-colors hover:border-line-strong hover:text-ink-subtle md:w-64 lg:w-80"
        aria-label="Search stocks and pages"
      >
        <Search className="size-3.5 shrink-0" aria-hidden />
        <span className="hidden flex-1 text-left md:block">Search stocks, pages…</span>
        <kbd className="hidden rounded border border-line px-1 py-0.5 font-mono text-2xs md:block">
          ⌘K
        </kbd>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl p-0" hideClose>
          <DialogTitle className="sr-only">Search</DialogTitle>
          {/* shouldFilter={false}: results are already filtered server-side.
              cmdk's built-in filter would additionally filter the API response and
              hide valid matches whose name does not literally contain the query. */}
          <Command className="overflow-hidden rounded-2xl" shouldFilter={false} loop>
            <div className="flex items-center gap-2 border-b border-line px-4">
              <Search className="size-4 shrink-0 text-ink-faint" aria-hidden />
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder="Search stocks or jump to a page…"
                className="h-12 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
              />
            </div>
            <Command.List className="max-h-[340px] overflow-y-auto p-2">
              <Command.Empty className="py-8 text-center text-xs text-ink-faint">
                {debounced ? "No matches found." : "Start typing to search."}
              </Command.Empty>

              {symbols.length ? (
                <Command.Group heading="Symbols" className={groupHeadingClass}>
                  {symbols.map((stock) => (
                    <Command.Item
                      key={stock.id}
                      value={stock.symbol}
                      onSelect={() => go(`/stocks/${stock.symbol}`)}
                      className="data-[selected=true]:bg-primary/12 flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm text-ink-muted data-[selected=true]:text-ink"
                    >
                      <TrendingUp className="size-4 shrink-0 text-primary" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium text-ink">{stock.symbol}</span>
                        <span className="block truncate text-2xs text-ink-faint">{stock.name}</span>
                      </span>
                      <span className="shrink-0 text-2xs text-ink-faint">{stock.exchange}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              ) : null}

              <Command.Group heading="Pages" className={groupHeadingClass}>
                {NAV_ITEMS.filter(
                  (item) =>
                    !debounced || item.label.toLowerCase().includes(debounced.toLowerCase()),
                ).map((item) => {
                  const Icon = item.icon;
                  return (
                    <Command.Item
                      key={item.href}
                      value={item.href}
                      onSelect={() => go(item.href)}
                      className="data-[selected=true]:bg-primary/12 flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm text-ink-muted data-[selected=true]:text-ink"
                    >
                      <Icon className="size-4 shrink-0 text-ink-subtle" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block">{item.label}</span>
                        <span className="block truncate text-2xs text-ink-faint">
                          {item.description}
                        </span>
                      </span>
                    </Command.Item>
                  );
                })}
              </Command.Group>
            </Command.List>
          </Command>
        </DialogContent>
      </Dialog>
    </>
  );
}
